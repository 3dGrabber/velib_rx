from typing import List, Any, Callable
from rx.core.typing import T_out

from velib_rx.type_variables import T
from velib_rx.utils import Record, MutableRecord, matches


# noinspection PyShadowingBuiltins
class Signal(Record):

    def __init__(self,
                 service_name: str,
                 service_aliases: List[str],
                 id: str,
                 object_path: str,
                 interface: str,
                 member: str,
                 data: Any) -> None:

        super().__init__()

        self.service_name = service_name
        self.service_aliases = service_aliases
        self.id = id
        self.object_path = object_path
        self.interface = interface
        self.member = member
        self.data = data


# noinspection PyShadowingBuiltins
class UnresolvedSignal(Record):

    def __init__(self,
                 service_names: List[str],
                 id: str,
                 object_path: str,
                 interface: str,
                 member: str,
                 data: Any) -> None:

        super().__init__()

        self.service_names = service_names
        self.id = id
        self.object_path = object_path
        self.interface = interface
        self.member = member
        self.data = data

    def resolve(self, service_name='*', object_path='*', interface='*', member='*'):

        if not matches(self.object_path, object_path):
            return None

        if not matches(self.member, member):
            return None

        if not matches(self.interface, interface):
            return None

        # TODO: match by id
        for n in self.service_names:
            if matches(n, service_name):
                return Signal(service_name=n,
                              service_aliases=self.service_names,
                              id=self.id,
                              object_path=self.object_path,
                              interface=self.interface,
                              member=self.member,
                              data=self.data)

        return None


def _create_match_rule(message_type: str, service_name: str, object_path: str, interface: str, member: str) -> str:

    # [1]
    # the daemon cannot filter service name prefixes. so if there is a glob,
    # we need to let all services through and filter here on the process.
    # This could be made a bit more efficient:
    # track nameownerchanged and install/remove specific match rules accordingly.
    # probably not worth the effort

    filter_rule = "type='%s'" % message_type

    if not service_name.endswith('*'):             # [1]
        filter_rule += ",%s='%s'" % ('sender', service_name)

    if object_path.endswith('*'):
        prefix = object_path[:-1]
        if prefix:
            filter_rule += ",%s='%s'" % ('path_namespace', prefix)
    else:
        filter_rule += ",%s='%s'" % ('path', object_path)

    if not interface.endswith('*'):
        filter_rule += ",%s='%s'" % ('interface', interface)

    if not member.endswith('*'):
        filter_rule += ",%s='%s'" % ('member', member)

    return filter_rule


class ExportedVeProperty(MutableRecord):

    def __init__(self, service_name: str,
                 object_path: str,
                 value: T,
                 text: str = None,
                 accept_value_change: Callable[[Any], bool] = lambda _: False) -> None:

        super().__init__()

        self.service_name = service_name
        self.object_path = object_path
        self.value = value
        self.text = text or str(value)
        self.accept_value_change = accept_value_change

    def to_ve_property(self):
        return VeProperty(self.service_name, self.object_path, self.value, self.text)


class VeProperty(Record):

    def __init__(self,
                 service_name: str,
                 object_path: str,
                 value: T_out,
                 text: str = None) -> None:

        super().__init__()

        self.service_name = service_name
        self.object_path = object_path
        self.value = value
        self.text = text or str(value)

    def export(self, accept_value_change: Callable[[Any], bool] = lambda _: False):
        return ExportedVeProperty(self.service_name, self.object_path, self.value, self.text, accept_value_change)

    @staticmethod
    def parse(signal: Signal) -> 'VeProperty':

        data = signal.data[0]

        return VeProperty(
            service_name=signal.service_name,
            object_path=signal.object_path,
            value=data['Value'][1],
            text=data['Text'][1]
        )