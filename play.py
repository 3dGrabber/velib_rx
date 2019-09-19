#!/usr/bin/python3

from datetime import timedelta, datetime
from velib_rx.dbus import DBus
import pickle

file_name = 'recorded.dat'


def main():

    f = open(file_name, 'rb')
    events = pickle.load(f)
    f.close()

    dbus = DBus.new_tcp_connection('192.168.178.137')

    duration = events[-1].timestamp - events[0].timestamp + timedelta(seconds=2)

    for e in events:
        due_time = e.timestamp - events[0].timestamp

        def publish(p=e.value):  # avoid closure trap
            print(p)
            dbus.publish_ve_property(p.service_name, p.object_path, p.value, p.text)

        dbus.schedule(publish, due_time)

    print('playing ' + file_name + ' for ' + str(duration.total_seconds()))
    dbus.run_for_timespan(duration)
    print('done')

main()



