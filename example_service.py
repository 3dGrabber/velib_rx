#!/usr/bin/python3
from datetime import timedelta
from typing import Tuple

import rx

from velib_rx.dbus import DBus
from velib_rx.messages import VeProperty


# run this and test it in dbus-spy

def main():
    dbus = DBus.new_tcp_connection('192.168.178.137')
    service_name = 'com.victronenergy.example'

    def always(_):
        return True

    dbus.publish_ve_property(service_name, '/ProductName', 'Example Product')
    dbus.publish_ve_property(service_name, '/YouCannotEditMe', 'try it')
    dbus.publish_ve_property(service_name, '/EnterNumberBetween0and10', 5, accept_change=lambda n: 0 <= float(n) <= 10)
    dbus.publish_ve_property(service_name, '/EnterSalutation', 'Hello', accept_change=always)
    dbus.publish_ve_property(service_name, '/EnterYourName', '', accept_change=always)
    dbus.publish_ve_property(service_name, '/Greetings', 'please enter a name and a salutation')

    def update_counter(i):
        dbus.publish_ve_property(service_name, '/Counter', i)

    rx.interval(timedelta(seconds=1)).subscribe(update_counter)

    def greeter(s_n: Tuple[VeProperty, VeProperty]):
        s, n = s_n; salutation = s.text; name = n.text

        greeting = f'{salutation} {name}' if salutation and name else 'please enter a name and a salutation'
        dbus.publish_ve_property(service_name, '/Greetings', greeting)

    salutation = dbus.observe_ve_property(service_name, '/EnterSalutation')
    name = dbus.observe_ve_property(service_name, '/EnterYourName')
    rx.combine_latest(salutation, name).subscribe(greeter)

    dbus.run_forever()


main()

