import zmq
import gettext
import logging
import os
from gi.repository import GObject
from sugar3 import profile

class ActivityCollab(GObject.GObject):

    def __init__(self):
        GObject.GObject.__init__(self)

        self._participants = []
        self._leader_key = None
        self._leader_port = None
        self._leader_ips = []

    def set_leader_ips(self, ips):
        self._leader_ips = ips

    def get_leader_ips(self, ips):
        return self._leader_ips

    leader_ips = GObject.property(type=object, getter=get_leader_ips,
        setter=set_leader_ips)

    def set_leader_port(self, port):
        self._leader_port = port

    def get_leader_port(self, port):
        return self._leader_port

    leader_port = GObject.property(type=object, getter=get_leader_port,
        setter=set_leader_port)

    def set_leader_key(self, key):
        self._leader_key = key

    def get_leader_key(self, key):
        return self._leader_key

    leader_key = GObject.property(type=object, getter=get_leader_key,
        setter=set_leader_key)

