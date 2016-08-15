import zmq
import gettext
import logging
import os
from gi.repository import GObject
from sugar3 import profile
from jarabe.model import neighborhood

class ActivityCollab(GObject.GObject):

    def __init__(self):
        GObject.GObject.__init__(self)

        self._participants = {}
        self._leader_key = None
        self._leader_pub_port = None
        self._leader_rep_port = None
        self._leader_ips = []
        print "I am in ActivityCollab"
        self._pub_socket, self._pub_port = self.get_socket_port_pair(zmq.PUB)
        self._rep_socket, self._rep_port = self.get_socket_port_pair(zmq.REP)

        zmq_fd = self._rep_socket.getsockopt(zmq.FD)
        GObject.io_add_watch(zmq_fd,
                         GObject.IO_IN|GObject.IO_ERR|GObject.IO_HUP,
                         self.zmq_callback, self._rep_socket)

    def zmq_callback(self, queue, condition, socket):
        print ('Yeah receivied something via zmq :) ')

        while socket.getsockopt(zmq.EVENTS) & zmq.POLLIN:
            observed = socket.recv()
            received_dict = json.loads(observed)
            print ("Received %s" % received_dict.get('icon-color'))
            received_dict.pop('type')
            invite = ZMQActivityInvite(received_dict, socket)
            self._invites_received.append(invite)
            self.emit('invite-added',invite)
        return True

    def get_socket_port_pair(self, socket_typ):
        context = zmq.Context()
        socket = context.socket(socket_typ)
        port = socket.bind_to_random_port("tcp://*",
                                            min_port=6000,
                                            max_port=7000,
                                            max_tries=10)
        return socket, port

    def get_pub_port(self):
        return self._pub_port

    pub_port = GObject.property(type=object, getter=get_pub_port)

    def get_rep_port(self):
        return self._rep_port

    rep_port = GObject.property(type=object, getter=get_rep_port)

    def set_leader_ips(self, ips):
        self._leader_ips = ips

    def get_leader_ips(self):
        return self._leader_ips

    leader_ips = GObject.property(type=object, getter=get_leader_ips,
        setter=set_leader_ips)

    def set_leader_pub_port(self, port):
        self._leader_pub_port = port

    def get_leader_pub_port(self):
        return self._leader_pub_port

    leader_pub_port = GObject.property(type=object, getter=get_leader_pub_port,
        setter=set_leader_pub_port)

    def set_leader_rep_port(self, port):
        self._leader_rep_port = port

    def get_leader_rep_port(self):
        return self._leader_rep_port

    leader_rep_port = GObject.property(type=object, getter=get_leader_rep_port,
        setter=set_leader_rep_port)

    def set_leader_key(self, key):
        self._leader_key = key

    def get_leader_key(self):
        return self._leader_key

    leader_key = GObject.property(type=object, getter=get_leader_key,
        setter=set_leader_key)

