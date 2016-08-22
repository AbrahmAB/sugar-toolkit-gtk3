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
        'send-update': (GObject.SignalFlags.RUN_FIRST, None,([str, str])),
    }

    def __init__(self):
        GObject.GObject.__init__(self)

        self._participants = {}
        self._leader_key = None
        self._leader_nick  = None
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

        self.my_dict = {'ips': None,
                   'pub_port': self._pub_port,
                   'rep_port': self._rep_port,
                   'presence': ONLINE,
                   'color': profile.get_color().to_string(),
                   'nick': profile.get_nick_name() }
        self.add_participant(self.my_key, self.my_dict)

        zmq_fd = self._rep_socket.getsockopt(zmq.FD)
        GObject.io_add_watch(zmq_fd,
                         GObject.IO_IN|GObject.IO_ERR|GObject.IO_HUP,
                         self.zmq_callback, self._rep_socket)

    def get_participants(self):
        return self._participants

    def zmq_callback(self, queue, condition, socket):
        while socket.getsockopt(zmq.EVENTS) & zmq.POLLIN:
            print "Received req!"
            observed = socket.recv()
            print ("Received request here %s" % observed)
            received_req = json.loads(observed)
            self.broadcast_msg(observed)
            if received_req['type'] == 'buddy-new':
                buddy_key = received_req.pop('buddy_key')
                if self._participants.get(buddy_key, None):
                    self._participants[buddy_key]['presence'] = ONLINE
                buddy = self._buddy_discover.get_buddy_by_key(buddy_key)
                received_req.pop('type')
                received_req['ips'] = buddy.props.ips
                received_req['presence'] = ONLINE
                self.add_participant(buddy_key, received_req)
                msg = {}
                msg['type'] = 'participants'
                msg['buddy_key'] = self.my_key
                msg['participants'] = self._participants 
                txt = json.dumps(msg)
                socket.send(txt)
            elif received_req['type'] == 'buddy-remove':
                msg = {}
                msg['type'] = 'done'
                socket.send(json.dumps(msg))
                buddy_key = received_req.pop('buddy_key')
                buddy = self._buddy_discover.get_buddy_by_key(buddy_key)
                self.remove_participant(None, buddy, presence=OFFLINE)
            elif received_req['type'] == 'text':
                print "Replying to text"
                msg = {'type':'success'}
                txt = json.dumps(msg)
                socket.send(txt)
                self.emit('received-text',observed)

        return True

    def broadcast_msg(self, txt):
        msg = json.loads(txt)
        if msg['type'] == 'buddy-remove' and not msg.get('buddy_key', None):
            msg['buddy_key'] = profile.get_profile().privkey_hash
        txt = json.dumps(msg)
        self._pub_socket.send(txt)

    def add_participant(self, key, buddy_dict):
        buddy_rcv = self._buddy_discover.get_buddy_by_key(key)
        self._participants[key] = { 'ips': buddy_dict['ips'],
                                    'pub_port': buddy_dict['pub_port'],
                                    'rep_port': buddy_dict['rep_port'],
                                    'presence': buddy_dict['presence'],
                                    'color': buddy_dict['color'],
                                    'nick': buddy_dict['nick'] }
        print "participants are: %s" % self._participants

    def remove_participant(self, discovery, buddy, presence=AWAY):
        buddy_dict = self._participants.get(buddy.props.key,None)
        if buddy_dict is None:
            return
        buddy_dict['presence'] = presence
        self._participants[buddy.props.key] = buddy_dict
        if self._leader_key == buddy.props.key:
            print "Leader not available!!"

            for key, value in self._participants.items():
                if value['presence'] == ONLINE:
                    self._leader_key = key
                    self._leader_pub_port = value['pub_port']
                    self._leader_rep_port = value['rep_port']
                    print "New leader is"+str(self._leader_key)
                    if self._leader_key == self.my_key:
                        print "Sending updates 1"
                        self.is_leader = True
                        ips = []
                        ports = []
                        for key, value in self._participants.items():
                            if value['presence'] == OFFLINE:
                                print "Sending updates 2"
                                buddy = self._buddy_discover.get_buddy_by_key(key)
                                ips.append(buddy.props.ips)
                                ports.append( buddy.props.port)
                        self.emit('send-update', str(ips), str(ports))
                    else:
                        self.connect_to_leader()
                    break
            
            
        print "participants now are" + str(self._participants)

    def chk_participant_prop(self, discovery, buddy):
        buddy_dict = self._participants.get(buddy.props.key,None)
        if buddy_dict is None:
            return
        buddy_dict['ips'] = buddy.props.ips
        buddy_dict['nick'] = buddy.props.nick
        if not buddy_dict['presence'] == ONLINE:
            buddy_dict['pub_port'] = None
            buddy_dict['rep_port'] = None
            #TODO: ONLINE or OFFLINE
            buddy_dict['presence'] = OFFLINE
        self._participants[buddy.props.key] = buddy_dict
        print "participants after chk: %s" % self._participants

        if self.is_leader:
            ips = buddy_dict['ips']
            self.emit('send-update', str(ips), buddy.props.port)

    def start_listening(self):
        req_msg = {'type': 'buddy-new',
                   'pub_port': self._pub_port,
                   'rep_port': self._rep_port,
                   'presence': ONLINE,
                   'color': self.my_dict['color'],
                   'nick': self.my_dict['nick'] }
        txt = json.dumps(req_msg)
        print "My leader is "+ str(self._leader_key)
        self.connect_to_leader()
        self.send_msg_req(txt)

    def connect_to_leader(self):
        context = zmq.Context()
        self._sub_sockets = context.socket(zmq.SUB)
        for ip in self._leader_ips:
            logging.debug('Connecting to %s via port %s' % (ip, self._leader_pub_port) )
            self._sub_sockets.connect("tcp://"+str(ip)+":"+str(self._leader_pub_port))
            self._sub_sockets.setsockopt(zmq.SUBSCRIBE, "")
            zmq_fd = self._sub_sockets.getsockopt(zmq.FD)
            print "Started listening now!"
            GObject.io_add_watch(zmq_fd,
                         GObject.IO_IN|GObject.IO_ERR|GObject.IO_HUP,
                         self.received_update, self._sub_sockets)

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
                elif update['type'] == 'buddy-remove':
                    typ = update.pop('type')
                    buddy_rcv = self._buddy_discover.get_buddy_by_key(update['buddy_key'])
                    if buddy_rcv is None:
                        self._participants[update['key']] = {'ips': None,
                                                             'presence': OFFLINE }
                        continue
                    self.remove_participant(None, buddy_rcv, presence=OFFLINE)
                elif update['type'] == 'text':
                    self.emit('received-text', json.dumps(update))


        return True

    def received_reply(self, queue, condition, socket):
        print ('Received reply')
        while socket.getsockopt(zmq.EVENTS) & zmq.POLLIN:
            msg_rcv = socket.recv()
            print ("Received reply is %s" % msg_rcv)
            update = json.loads(msg_rcv)
            if update['type'] == 'success':
                print "Message received"
            elif update['buddy_key'] is not self.my_key:
                if update['type'] == 'participants':
                    typ = update.pop('type')
                    participants_rcv = update['participants']
                    print ("type here %s" % str((participants_rcv)))

                    for key, value in participants_rcv.items():
                        print ("leader key is %s and key is %s" % (self._leader_key, key))
                        if not key == self._leader_key:
                            self.add_participant(key, value)
            self.wait_send = 0
        #socket.disconnect()

        return True

    def send_msg_req(self, txt):
        msg = json.loads(txt)
        msg['buddy_key'] = profile.get_profile().privkey_hash
        txt = json.dumps(msg)
        for ip in self._leader_ips:
            context = zmq.Context()
            self._req_socket = context.socket(zmq.REQ)
            self._req_socket.connect("tcp://"+str(ip)+":"+str(self._leader_rep_port))
            self._req_socket.send(txt)
            zmq_fd = self._req_socket.getsockopt(zmq.FD)
            GObject.io_add_watch(zmq_fd,
                         GObject.IO_IN|GObject.IO_ERR|GObject.IO_HUP,
                         self.received_reply, self._req_socket)

    def get_socket_port_pair(self, socket_typ):
        context = zmq.Context()
        socket = context.socket(socket_typ)
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

    def set_leader_nick(self, nick):
        self._leader_nick = nick

    def get_leader_nick(self):
        return self._leader_nick

    leader_nick = GObject.property(type=object, getter=get_leader_nick,
        setter=set_leader_nick)
