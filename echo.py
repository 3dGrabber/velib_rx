#!/usr/bin/python3

"""
A simple echo service that mirrors another dbus service
"""


from velib_rx.dbus import DBus
from velib_rx.messages import VeProperty

dbus = DBus.new_tcp_connection('192.168.178.137')


def echo(p: VeProperty):
    print(p)
    dbus.publish_ve_property(p.service_name.replace('meteo', 'echo'),
                             p.object_path,
                             p.value,
                             p.text)


dbus.observe_ve_property(service_name='com.victronenergy.meteo.*').subscribe(echo)

dbus.run_forever()


