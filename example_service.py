#!/usr/bin/python3
from datetime import timedelta

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
    dbus.publish_ve_property(service_name, '/Greetings', '')

    def update_counter(i):
        dbus.publish_ve_property(service_name, '/Counter', i)

    rx.interval(timedelta(seconds=1)).subscribe(update_counter)

    def greeter(salutation: VeProperty, name: VeProperty):
        greeting = salutation.text + ' ' + name.text if salutation.text and name.text else ''
        dbus.publish_ve_property(service_name, '/Greetings', greeting)

    salutation = dbus.observe_ve_property(service_name, '/EnterSalutation')
    name = dbus.observe_ve_property(service_name, '/EnterYourName')
    rx.combine_latest(salutation, name).subscribe(lambda t: greeter(*t))

    dbus.run_forever()


main()

