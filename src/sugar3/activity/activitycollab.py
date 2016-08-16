import zmq
import gettext
import logging
import json
import os
from gi.repository import GObject
from sugar3 import profile
from jarabe.model import neighborhood

ONLINE = 1
OFFLINE = 0
AWAY = -1

class ActivityCollab(GObject.GObject):
    __gsignals__ = {
        'received-text': (GObject.SignalFlags.RUN_FIRST, None, ([str])),
    }

    def __init__(self):
        GObject.GObject.__init__(self)

        self._participants = {}
        self._leader_key = None
        self._leader_pub_port = None
        self._leader_rep_port = None
        self._leader_ips = []
        print "I am in ActivityCollab"
        self._rep_socket, self._rep_port = self.get_socket_port_pair(zmq.REP)
        self._pub_socket, self._pub_port = self.get_socket_port_pair(zmq.PUB)

        self._sub_sockets = None
        self._req_socket = None
        self.is_leader = False
        self.my_key = profile.get_profile().privkey_hash

        self._buddy_discover = None
        avahi_discover, avahi_publisher = neighborhood.go_avahi()
        self._buddy_discover = avahi_discover
        self._buddy_discover.connect('buddy-removed', self.remove_participant)
        self._buddy_discover.connect('buddy-added', self.chk_participant_prop)

        my_dict = {'ips': None,
                   'pub_port': self._pub_port,
                   'rep_port': self._rep_port,
                   'presence': ONLINE }
        self.add_participant(self.my_key, my_dict)

        zmq_fd = self._rep_socket.getsockopt(zmq.FD)
        GObject.io_add_watch(zmq_fd,
                         GObject.IO_IN|GObject.IO_ERR|GObject.IO_HUP,
                         self.zmq_callback, self._rep_socket)

    def zmq_callback(self, queue, condition, socket):
        while socket.getsockopt(zmq.EVENTS) & zmq.POLLIN:
            observed = socket.recv()
            print ("Received request here %s" % observed)
            self._pub_socket.send(observed)
            received_req = json.loads(observed)
            self.broadcast_msg(observed)
            if received_req['type'] == 'buddy-new':
                msg = {}
                msg['type'] = 'participants'
                msg['buddy_key'] = self.my_key
                msg['participants'] = self._participants 
                txt = json.dumps(msg)
                socket.send(txt)
                buddy_key = received_req.pop('buddy_key')
                buddy = self._buddy_discover.get_buddy_by_key(buddy_key)
                received_req.pop('type')
                received_req['ips'] = buddy.props.ips
                received_req['presence'] = ONLINE
                self.add_participant(buddy_key, received_req)
            elif received_req['type'] == 'text':
                self.emit('received-text',observed)

        return True

    def broadcast_msg(self, txt):
        self._pub_socket.send(txt)

    def add_participant(self, key, buddy_dict):
        buddy_rcv = self._buddy_discover.get_buddy_by_key(key)
        self._participants[key] = { 'ips': buddy_dict['ips'],
                                    'pub_port': buddy_dict['pub_port'],
                                    'rep_port': buddy_dict['rep_port'],
                                    'presence': buddy_dict['presence'] }
        print "participants are: %s" % self._participants

    def remove_participant(self, discovery, buddy):
        buddy_dict = self._participants.get(buddy.props.key,None)
        if buddy_dict is None:
            return
        buddy_dict['presence'] = AWAY
        self._participants[buddy.props.key] = buddy_dict
        if self._leader_key == buddy.props.key:
            print "Leader went offline!!"

            for key, value in self._participants.items():
                if value['presence'] == ONLINE:
                    self._leader_key = key
                    self._leader_pub_port = value['pub_port']
                    self._leader_rep_port = value['rep_port']
                    if self._leader_key == self.my_key:
                        self.is_leader = True
            print "New leader is"+str(self._leader_key)
        print "participants now are" + str(self._participants)

    def chk_participant_prop(self, discovery, buddy):
        buddy_dict = self._participants.get(buddy.props.key,None)
        if buddy_dict is None:
            return
        buddy_dict['ips'] = buddy.props.ips
        #TODO: ONLINE or OFFLINE
        buddy_dict['presence'] = ONLINE
        self._participants[buddy.props.key] = buddy_dict
        print "participants are: %s" % self._participants               

    def start_listening(self):
        leader_dict = {'ips': self._leader_ips,
                        'pub_port': self._leader_pub_port,
                        'rep_port': self._leader_rep_port,
                        'presence': ONLINE }

        context = zmq.Context()
        self._req_socket = context.socket(zmq.REQ)
        req_msg = {'type': 'buddy-new',
                   'pub_port': self._pub_port,
                   'rep_port': self._rep_port,
                   'buddy_key': self.my_key,
                   'presence': ONLINE}
        txt = json.dumps(req_msg)
        self._sub_sockets = context.socket(zmq.SUB)
        for ip in self._leader_ips:
            self._sub_sockets.connect("tcp://"+str(ip)+":"+str(self._leader_pub_port))
            self._sub_sockets.setsockopt(zmq.SUBSCRIBE, "")
            zmq_fd = self._sub_sockets.getsockopt(zmq.FD)
            print "Started listening now!"
            GObject.io_add_watch(zmq_fd,
                         GObject.IO_IN|GObject.IO_ERR|GObject.IO_HUP,
                         self.received_update, self._sub_sockets)

        self.send_msg_req(txt)

    def received_update(self, queue, condition, socket):
        print ('Received update')
        while socket.getsockopt(zmq.EVENTS) & zmq.POLLIN:
            msg_rcv = socket.recv()
            print ("Received update is %s" % msg_rcv)
            update = json.loads(msg_rcv)

            if update.get('buddy_key',None) and update['buddy_key'] == self.my_key:
                continue
            else:
                if update['type'] == 'buddy-new':
                    typ = update.pop('type')
                    buddy_rcv = self._buddy_discover.get_buddy_by_key(update['buddy_key'])
                    if buddy_rcv is None:
                        update['ips'] = None
                        self.add_participant(update['buddy_key'], update)
                        continue
                    update['ips'] = buddy_rcv.props.ips
                    buddy_key = update.pop('buddy_key')
                    self.add_participant(buddy_key, update)
                elif update['type'] == 'text':
                    self.emit('received-text', json.dumps(update))


        return True

    def received_reply(self, queue, condition, socket):
        print ('Received reply')
        while socket.getsockopt(zmq.EVENTS) & zmq.POLLIN:
            msg_rcv = socket.recv()
            print ("Received reply is %s" % msg_rcv)
            update = json.loads(msg_rcv)
            if update['buddy_key'] is not self.my_key:
                if update['type'] == 'participants':
                    typ = update.pop('type')
                    participants_rcv = update['participants']
                    print ("type here %s" % str((participants_rcv)))

                    for key, value in participants_rcv.items():
                        print ("leader key is %s and key is %s" % (self._leader_key, key))
                        if not key == self._leader_key:
                            self.add_participant(key, value)
        return True

    def send_msg_req(self, txt):
        for ip in self._leader_ips:
            self._req_socket.connect("tcp://"+str(ip)+":"+str(self._leader_rep_port))
            #multiple socket needed!!
            self._req_socket.send(txt)

            zmq_fd = self._req_socket.getsockopt(zmq.FD)
            GObject.io_add_watch(zmq_fd,
                         GObject.IO_IN|GObject.IO_ERR|GObject.IO_HUP,
                         self.received_reply, self._req_socket)

    def get_socket_port_pair(self, socket_typ):
        context = zmq.Context()
        socket = context.socket(    socket_typ)
        port = socket.bind_to_random_port("tcp://*",
                                            min_port=6000,
                                            max_port=7000,
                                            max_tries=10)
        print ("socket is %s" % socket)
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

