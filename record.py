#!/usr/bin/python3

from datetime import timedelta
import rx.operators as op
from velib_rx.dbus import DBus
import pickle

# this will record all propertyChanged of the matching service(s)
# it will not yet record properties for which no propertyChanged has been fired
# see TODO in observe_ve_property

service = 'com.victronenergy.meteo.*'
t_seconds = 30
events = []

dbus = DBus.new_tcp_connection('192.168.178.137')
properties = dbus.observe_ve_property(service_name=service)

properties.pipe(
    op.do_action(print),
    op.timestamp()
).subscribe(events.append)

print(f'recording {service} for {t_seconds} seconds')
dbus.run_for_timespan(timedelta(seconds=t_seconds))

file_name = 'recorded.dat'
with open(file_name, 'ab') as f:
    pickle.dump(events, f, protocol=0)

print(f'done, wrote {file_name}')


