import asyncio
from asyncio import AbstractEventLoop

from datetime import timedelta
from typing import Iterable, Any, Optional, List, Tuple, Set, Union, Callable, Dict

import rx
from rx import operators as op
from rx.core.abc import Disposable as DisposableBase
from rx.core.typing import Observable, Observer, Scheduler
from rx.disposable import Disposable
from rx.scheduler.eventloop import AsyncIOThreadSafeScheduler
from rx.subject import Subject

from dbussy import Connection, Message, DBUS as DBUS_CONSTANTS

from velib_rx.convert import convert_python_value_to_dbus
from velib_rx.messages import UnresolvedSignal, _create_match_rule, VeProperty, ExportedVeProperty
from velib_rx.type_variables import T
from velib_rx.utils import matches


class DBus(DisposableBase):

    _own_service_names: Set[str]
    _ve_properties: Dict[Tuple[str, str], ExportedVeProperty]
    _disposables: List[Disposable]
    _incoming_messages: Observable[Message]

    @staticmethod
    def new_session_bus_connection(loop=asyncio.get_event_loop(), private=False) -> 'DBus':
        c = Connection.bus_get(DBUS_CONSTANTS.BUS_SESSION, private)
        return DBus(c, loop)

    @staticmethod
    def new_system_bus_connection(private=False, loop=asyncio.get_event_loop()) -> 'DBus':
        c = Connection.bus_get(DBUS_CONSTANTS.BUS_SYSTEM, private)
        return DBus(c, loop)

    @staticmethod
    def new_tcp_connection(endpoint: str, port=55555, private=False, loop=asyncio.get_event_loop()) -> 'DBus':
        c = Connection.open(f'tcp:host={endpoint},port={port}', private)
        c.bus_register()  # dbus hello
        return DBus(c, loop)

    def __init__(self, connection: Connection, event_loop: AbstractEventLoop = asyncio.get_event_loop()) -> None:
        """
        DO NOT USE DIRECTLY
        use one of the new_XXX static methods
        """
        super().__init__()

        connection.attach_asyncio(event_loop)

        self._connection = connection
        self._event_loop = event_loop
        self._scheduler = AsyncIOThreadSafeScheduler(event_loop)
        self._disposables = []
        self._own_service_names = set([]) # TODO: make BehaviorSubject?
        self._ve_properties = {}          # TODO: make BehaviorSubject?

        # If you are confused by publish/refcount, just ignore them.
        # It's an optimization technique with no influence on business logic.
        # The code would run perfectly fine without them

        incoming_msgs = self._observe_messages(connection).pipe(op.publish())

        self._signals = self._init_signals(incoming_msgs)
        self._method_calls = self._init_method_calls(incoming_msgs)

        self._init_bus_item_calls(self._method_calls)

        # TODO: this could be made async...
        # TODO: there is a small chance that a nameownerchanged is fired while we populate the list...
        self._service_name_of_id = {self._get_id_of_service(sn): sn for sn in self._get_service_names()}

        self.observe_service_added, self.observe_service_removed, self.observe_online_services = \
            self._init_remote_services()  # depends on self._signals

        self._disposables.append(incoming_msgs.connect(self._scheduler))  # use scheduler (asyncio) to dispatch

    @property
    def scheduler(self):
        return self._scheduler

    def _init_bus_item_calls(self, method_calls):

        def bus_item(msg: Message):
            return msg.interface == 'com.victronenergy.BusItem'

        bus_item_calls = method_calls.pipe(
            op.filter(bus_item),
            op.publish(),
            op.ref_count()
        )

        def is_set_value(msg: Message):
            return msg.member == 'SetValue'

        def is_get_value(msg: Message):
            return msg.member == 'GetValue'

        def is_get_text(msg: Message):
            return msg.member == 'GetText'

        # TODO: simplify, mb merge with getvalue
        def on_get_text_called(msg: Message):

            object_path = msg.path

            reply = None

            if object_path == '/':
                # tree export
                prop_dict = {
                    path: prop.text
                    for ((_service_name, path), prop)
                    in self._ve_properties.items()
                }
                reply = msg.new_method_return()
                reply.append_objects('v', ('a{ss}', prop_dict))
                print(prop_dict)
            else:
                text = next((
                    convert_python_value_to_dbus(prop.text)
                    for ((_service_name, path), prop)
                    in self._ve_properties.items()
                    if path == object_path
                ), None)

                if text is not None:
                    reply = msg.new_method_return()
                    reply.append_objects(*text)
                else:
                    reply = msg.new_error(DBUS_CONSTANTS.ERROR_UNKNOWN_OBJECT, object_path)

            self._connection.send(reply)

        # TODO: simplify, mb merge with gettext
        def on_get_value_called(msg: Message):

            object_path = msg.path

            reply = None

            if object_path == '/':
                # tree export
                prop_dict = {
                    path: convert_python_value_to_dbus(prop.value)
                    for ((_service_name, path), prop)
                    in self._ve_properties.items()
                }
                reply = msg.new_method_return()
                reply.append_objects('v', ('a{sv}', prop_dict))

                print(prop_dict)
            else:
                value = next((
                    convert_python_value_to_dbus(prop.value)
                    for ((_service_name, path), prop)
                    in self._ve_properties.items()
                    if path == object_path
                ), None)

                if value is not None:
                    reply = msg.new_method_return()
                    reply.append_objects(*value)
                else:
                    reply = msg.new_error(DBUS_CONSTANTS.ERROR_UNKNOWN_OBJECT, object_path)

            self._connection.send(reply)

        def on_set_value_called(msg: Message):

            object_path = msg.path
            reply = None

            prop = next((
                    prop
                    for ((_service_name, path), prop)
                    in self._ve_properties.items()
                    if path == object_path
                ), None)

            if prop is None:
                reply = msg.new_error(DBUS_CONSTANTS.ERROR_UNKNOWN_OBJECT, object_path)
            else:

                # noinspection PyBroadException,PyBroadException
                try:
                    new_value = list(msg.objects)[0][1]  # TODO: respect data type

                    if prop.accept_value_change(new_value):
                        reply = msg.new_method_return()
                        reply.append_objects('i', 0)

                        def update():
                            self.publish_ve_property(
                                prop.service_name,
                                prop.object_path,
                                new_value,
                                str(new_value),    # TODO: render text of new value
                                accept_change=prop.accept_value_change
                            )

                        self.schedule(update)  # do this after we replied
                    else:
                        reply = msg.new_method_return()
                        reply.append_objects('i', 2)  # TODO: constants?
                        #reply = msg.new_error(DBUS_CONSTANTS.ERROR_INVALID_ARGS, object_path)

                except Exception as e:
                    reply = msg.new_error(DBUS_CONSTANTS.ERROR_FAILED, str(e))

            self._connection.send(reply)

        s_set_value = bus_item_calls.pipe(op.filter(is_set_value)).subscribe(on_set_value_called, on_error=self._on_error)
        s_get_value = bus_item_calls.pipe(op.filter(is_get_value)).subscribe(on_get_value_called, on_error=self._on_error)
        s_get_text = bus_item_calls.pipe(op.filter(is_get_text)).subscribe(on_get_text_called, on_error=self._on_error)

        self._disposables.append(s_set_value)
        self._disposables.append(s_get_value)
        self._disposables.append(s_get_text)

    def _on_error(self, err):
        print (err)
        self._event_loop.close()

    @staticmethod
    def _init_method_calls(incoming_msgs):

        def _is_method_call(msg: Message) -> bool:
            return msg.type == DBUS_CONSTANTS.MESSAGE_TYPE_METHOD_CALL

        return incoming_msgs.pipe(
            op.filter(_is_method_call),
            op.publish(),
            op.ref_count()
        )

    def _init_signals(self, incoming_msgs):

        def _is_signal(msg: Message) -> bool:
            return msg.type == DBUS_CONSTANTS.MESSAGE_TYPE_SIGNAL

        def _parse_signal(msg: Message) -> UnresolvedSignal:
            id_ = msg.sender
            service_names = self._get_service_names_of_id(id_)
            return UnresolvedSignal(service_names, id_, str(msg.path), msg.interface, msg.member, list(msg.objects))

        return incoming_msgs.pipe(
            op.filter(_is_signal),
            op.map(_parse_signal),
            op.publish(),
            op.ref_count()
        )

    @property
    def current_services(self) -> List[str]:
        # noinspection PyTypeChecker
        return self._service_name_of_id.values()

    def _on_scheduler(self, observable: rx.core.Observable) -> rx.core.Observable:
        return observable.pipe(op.observe_on(self._scheduler))

    def _init_remote_services(self) -> Tuple[Observable[str], Observable[str], Observable[List[str]]]:

        service_added = Subject()
        service_removed = Subject()
        service_list = Subject()

        def on_name_owner_changed(s: UnresolvedSignal):

            (name, old_id, new_id) = s.data

            if name.startswith(':'):
                return

            old_id = old_id or ''
            new_id = new_id or ''
            name = name or ''

            old_id = old_id.strip()
            new_id = new_id.strip()
            name = name.strip()

            if old_id == new_id:  # this happens, why?
                return

            added = not old_id and new_id
            removed = old_id and not new_id
            changed = old_id and new_id

            # 'changed' is dispatched as 'removed' followed by 'added'

            if removed or changed:
                del self._service_name_of_id[old_id]
                service_removed.on_next(name)

            if added or changed:
                self._service_name_of_id[new_id] = name
                service_added.on_next(name)

        name_owner_changed = self._observe_daemon_signal('NameOwnerChanged')\
                                 .subscribe(on_name_owner_changed, on_error=self._on_error, scheduler=self._scheduler)

        self._disposables.append(name_owner_changed)
        self._disposables.append(service_added)
        self._disposables.append(service_removed)
        self._disposables.append(service_list)

        # TODO: explain, scheduler ???
        # TODO: behaviorSubject? replay?
        def prepend_current(scheduler: Scheduler = None) -> Observable[str]:
            return service_added.pipe(op.start_with(*self.current_services))

        def prepend_current_list(scheduler: Scheduler = None) -> Observable[List[str]]:
            return service_added.pipe(op.start_with(self.current_services))

        service_added_with_current = rx.defer(prepend_current)
        service_list_with_current = rx.defer(prepend_current_list)

        return service_added_with_current, service_removed, service_list_with_current

    # for convenience
    def schedule_periodic(self, action: Callable[[], Optional[Disposable]], period: timedelta = None) -> Disposable:

        def _action(_, __):  # the arity of this func is VERY IMPORTANT
            return action()

        return self._scheduler.schedule_periodic(period, _action)

    # for convenience
    def schedule(self, action: Callable[[], Optional[Disposable]], due_time: timedelta = None) -> Disposable:

        def _action(_, __):  # the arity of this func is VERY IMPORTANT
            return action()

        if due_time is None:
            return self._scheduler.schedule(_action)
        else:
            return self._scheduler.schedule_relative(due_time, _action)

    def _observe_messages(self, connection: Connection):

        def subscribe(observer: Observer[Message], scheduler_: Scheduler = None):

            def dispatch_msg(_, message, _data):
                self.schedule(lambda: observer.on_next(message))
                return DBUS_CONSTANTS.HANDLER_RESULT_HANDLED

            connection.add_filter(dispatch_msg, None)

            def dispose():
                connection.remove_filter(dispatch_msg, None)  # remove filter again from connection
                observer.on_completed()  # signal observer that there will be no further msgs

            return Disposable(dispose)

        return rx.create(subscribe)

    def _get_service_names_of_id(self, id_: str) -> List[str]:
        return [name for (i, name) in self._service_name_of_id.items() if i == id_]

    def observe_signal(self, service_name='*', object_path='*', interface='*', member='*'):

        match_rule = _create_match_rule('signal', service_name, object_path, interface, member)

        @op.map
        def resolve_signal(s: UnresolvedSignal) -> bool:
            return s.resolve(service_name, object_path, interface, member)

        @op.filter
        def not_none(i):
            return i is not None

        def subscribe(observer: Observer[Message], scheduler=None):

            scheduler = scheduler or self._scheduler
            subs = self._signals.pipe(resolve_signal, not_none).subscribe(observer, scheduler=scheduler)
            self._connection.bus_add_match(match_rule)

            def dispose():
                self._connection.bus_remove_match(match_rule)
                subs.dispose()

            return Disposable(dispose)

        return rx.create(subscribe)

    def observe_ve_property(self, service_name='*', object_path='*') -> rx.Observable:
        # TODO: constants, generics?
        prop = self.observe_signal(service_name, object_path, 'com.victronenergy.BusItem', 'PropertiesChanged')

        # TODO: behaviorSubject? replay?
        # prepend own exported properties, so the subscriber does't have to wait for first property changed
        own = [
            p.to_ve_property()
            for ((sn, path), p)
            in self._ve_properties.items()
            if matches(sn, service_name) and matches(path, object_path)
        ]

        # TODO: request tree export and prepend matching, maybe this will obsolete the above

        return prop.pipe(op.map(VeProperty.parse), op.start_with(*own))  # TODO all ve_prop observable, publish

    def _observe_daemon_signal(self, signal_name: str) -> rx.Observable:
        return self.observe_signal(DBUS_CONSTANTS.SERVICE_DBUS,
                                   DBUS_CONSTANTS.PATH_DBUS,
                                   DBUS_CONSTANTS.INTERFACE_DBUS,
                                   signal_name)

    # noinspection PyTypeChecker
    def _get_service_names_and_ids(self) -> List[str]:
        return next(self._call_daemon_method('ListNames', None))

    def _get_service_names(self) -> List[str]:
        return [name for name in self._get_service_names_and_ids() if not name.startswith(':')]

    def _get_service_ids(self) -> List[str]:
        return [name for name in self._get_service_names_and_ids() if name.startswith(':')]

    def _get_id_of_service(self, service_name: str) -> str:
        reply = self._call_daemon_method('GetNameOwner', 's', service_name)
        return next(reply, None)

    def dispose(self):

        while self._own_service_names:
            service_name = self._own_service_names.pop()
            self._release_name(service_name)

        while self._disposables:
            self._disposables.pop().dispose()

        self._connection.close()

    # TODO: infer signature?
    def broadcast_signal(self,
                         service_name: str,
                         object_path: str,
                         interface: str,
                         member: str,
                         signature: str = None,
                         *args) -> None:

        if service_name not in self._own_service_names:
            self._request_name(service_name)
            self._own_service_names.add(service_name)

        msg = Message.new_signal(object_path, interface, member)

        msg.append_objects(signature, *args)

        self._connection.send(msg)



    # TODO: unpublish?
    def publish_ve_property(self,
                            service_name: str,
                            object_path: str,
                            value: T,
                            text: Union[str, Callable[[Any], str]] = str,
                            unit: Optional[str] = None,
                            accept_change: Callable[[Any], bool] = lambda _: False  # default: never accept, read-only
                            ):

        if not isinstance(text, str):
            text = text(value)

        if unit:
            text += unit

        if not self._update_property(service_name, object_path, value, text, accept_change):
            return

        dbus_property = {
            'Text':  convert_python_value_to_dbus(text),
            'Value': convert_python_value_to_dbus(value)
        }

        self.broadcast_signal(service_name,
                              object_path,
                              'com.victronenergy.BusItem',
                              'PropertiesChanged',
                              'a{sv}',
                              dbus_property)

    def _update_property(self, service_name, object_path, value, text, accept_change):

        key = service_name, object_path

        if key not in self._ve_properties:
            self._ve_properties[key] = ExportedVeProperty(service_name, object_path, value, text, accept_change)
            return True

        ve_property = self._ve_properties[key]
        ve_property.accept_value_change = accept_change  # update in any case

        if ve_property.value == value and ve_property.text == text:
            return False  # don't send PropertiesChanged when nothing changed

        ve_property.value = value
        ve_property.text = text

        return True

    def _call_service_method(self,
                             bus_name: str,
                             object_path: str,
                             interface: str,
                             method_name: str,
                             signature: Optional[str],
                             *args: Any) -> Iterable[Any]:

        message = Message.new_method_call(destination=bus_name,
                                          path=object_path,
                                          iface=interface,
                                          method=method_name)

        if signature is not None:
            message.append_objects(signature, *args)

        reply: Message = self._connection.send_with_reply_and_block(message)

        DBusException.raise_if_error_reply(reply)

        return reply.objects

    async def _call_service_method_async(self,
                                         bus_name: str,
                                         object_path: str,
                                         interface: str,
                                         method_name: str,
                                         signature: Optional[str],
                                         *args: Any) -> Iterable[Any]:

        message = Message.new_method_call(destination=bus_name,
                                          path=object_path,
                                          iface=interface,
                                          method=method_name)

        if signature is not None:
            message.append_objects(signature, *args)

        reply: Message = await self._connection.send_await_reply(message)

        DBusException.raise_if_error_reply(reply)

        return reply.objects

    def _call_daemon_method(self, method_name: str, signature: Optional[str], *args: Any) -> Iterable[Any]:

        return self._call_service_method(DBUS_CONSTANTS.SERVICE_DBUS,
                                         DBUS_CONSTANTS.PATH_DBUS,
                                         DBUS_CONSTANTS.INTERFACE_DBUS,
                                         method_name,
                                         signature,
                                         *args)

    async def _call_daemon_method_async(self, method_name: str, signature: Optional[str], *args: Any) -> Iterable[Any]:

        return await self._call_service_method_async(DBUS_CONSTANTS.SERVICE_DBUS,
                                                     DBUS_CONSTANTS.PATH_DBUS,
                                                     DBUS_CONSTANTS.INTERFACE_DBUS,
                                                     method_name,
                                                     signature,
                                                     *args)

    def _request_name(self, bus_name: str) -> None:
        self._connection.bus_request_name(bus_name, DBUS_CONSTANTS.NAME_FLAG_DO_NOT_QUEUE)

    def _release_name(self, bus_name: str) -> None:
        self._connection.bus_release_name(bus_name)

    def run_forever(self):
        self._event_loop.run_forever()

    def run_for_timespan(self, timespan: timedelta):
        self._event_loop.run_until_complete(asyncio.sleep(timespan.total_seconds()))


class DBusException(Exception):

    def __init__(self, message):
        super(Exception, self).__init__(message)

    @classmethod
    def raise_if_error_reply(cls, reply: Message):
        if reply.type == DBUS_CONSTANTS.MESSAGE_TYPE_ERROR:
            raise DBusException(reply.error_name)

        return reply
