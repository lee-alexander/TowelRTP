import socket
from Queue import Queue, Empty
from collections import OrderedDict
from threading import Thread, Lock
from hashlib import md5
from time import sleep
from datetime import datetime, timedelta

class RTPPacket:
    HEADER_SIZE = 35

    def __init__(self, payload='', is_ack=False, is_handshake=False, is_disconnect=False, client_info=None,
                 seq_num=0, ack_num=0, timeout=None):
        self.payload = payload
        self.is_ack = is_ack
        self.is_handshake = is_handshake
        self.is_disconnect = is_disconnect
        self.client_info = client_info
        self.ack_num = ack_num
        self.seq_num = seq_num
        self.timeout = timeout
        self.compute_checksum()

    def set_seq_num(self, num):
        self.seq_num = num
        self.compute_checksum()

    def set_ack_num(self, num):
        self.ack_num = num
        self.compute_checksum()

    def is_expired(self):
        return datetime.now() > self.timeout

    def compute_checksum(self):
        self.checksum = md5(self.serialize(checksum_filled=False)).hexdigest()

    def serialize(self, checksum_filled=True):
        result = ''
        result += bool_str(self.is_ack)
        result += bool_str(self.is_handshake)
        result += bool_str(self.is_disconnect)
        result += str(self.seq_num).zfill(8)
        result += str(self.ack_num).zfill(8)
        result += self.checksum if checksum_filled else ('0' * 16)
        result += self.payload
        return result

    @classmethod
    def deserialize_and_create(cls, data, client_info=None):
        if len(data) < RTPPacket.HEADER_SIZE:
            return None

        is_ack = str_bool(data[0])
        is_handshake = str_bool(data[1])
        is_disconnect = str_bool(data[2])
        seq_num = int(data[3:11])
        ack_num = int(data[11:19])
        checksum = data[19:35]
        payload = data[35:] if len(data) > 35 else ''

        pkt_result = cls(payload, is_ack, is_handshake, is_disconnect, client_info, ack_num=ack_num, seq_num=seq_num)

        return pkt_result if checksum == pkt_result.checksum else None


def split_data(data, split_size):
    return [data[i:i+split_size] for i in range(0, len(data), split_size)]

def bool_str(bool):
    return 'T' if bool else 'F'

def str_bool(str):
    return str == 'T'

class RTPSocket(object):
    MTU_SIZE = 1000

    def __init__(self, port):
        # Connection state variables
        self.connected = False

        # Pipeline thread for updating send/receive buffers using UDP socket info
        self.pipeline = RTPSocketPipeline(port, self)
        self.pipeline.start()

    # Wait for a client to accept (blocking)
    def accept(self):
        if self.connected:
            return

        # Wait to receive a handshake from a client
        pkt = None
        while pkt is None or not pkt.is_handshake:
            pkt = self.pipeline.dequeue_packet()

        self.pipeline.update_client_info(pkt.client_info[0], pkt.client_info[1])
        self.connected = True

    # Connect to the server (non-blocking)
    def connect(self, address, port):
        if self.connected:
            return

        self.pipeline.update_client_info(address, port)
        self.pipeline.enqueue_packet_to_send(RTPPacket(is_handshake=True))
        self.connected = True

    # Close the RTP socket connection (non-blocking)
    def close(self, broadcast=True):
        if not self.connected:
            return

        self.connected = False
        if broadcast:
            self.pipeline.enqueue_packet_to_send(RTPPacket(is_disconnect=True))
        self.pipeline.stop()

    # Send data to the other side (non-blocking)
    def send(self, data):
        if not self.connected:
            return

        for chunk in split_data(data, RTPSocket.MTU_SIZE - RTPPacket.HEADER_SIZE):
            self.pipeline.enqueue_packet_to_send(RTPPacket(chunk))

    # Receive data from the other side (blocking)
    def receive(self):
        if not self.connected:
            return None

        pkt = self.pipeline.dequeue_packet()
        return None if pkt is None else pkt.payload



class RTPSocketPipeline(object):
    def __init__(self, port, rtp_socket):
        self._send_packets = Queue() # input packets sent to the pipeline to transmit reliably to other side
        self._pending_ack_packets = OrderedDict()
        self._pending_ack_packets_lock = Lock()
        self._receive_packets_staging = {} # buffered packets that were received out of order, stored by seq_num
        self._receive_packets = Queue() # in order and final

        self.running = False
        self.rtp_sock = rtp_socket
        self.next_seq_num = 1
        self.base_num = 1
        self.window_size = 10

        # Internal UDP Socket initialization
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_sock.bind(('', port))
        self.udp_sock.settimeout(1)

        self.other_addr = None
        self.other_port = None

    def update_client_info(self, other_addr, other_port):
        self.other_addr = other_addr
        self.other_port = other_port

    def start(self):
        self.running = True
        self.receive_thread = Thread(target=self._run_receive)
        self.receive_thread.start()
        self.send_thread = Thread(target=self._run_send)
        self.send_thread.start()
        self.timer_thread = Thread(target=self._run_timer)
        self.timer_thread.start()

    def stop(self):
        self.running = False
        self.receive_thread.join()
        self.send_thread.join()
        self.timer_thread.join()
        self.udp_sock.close()

    def enqueue_packet_to_send(self, pkt):
        self._send_packets.put(pkt)

    def dequeue_packet(self):
        while self.running:
            try:
                return self._receive_packets.get(timeout=1)
            except Empty:
                continue

        return None

    def _run_receive(self):
        while self.running:
            try:
                data, addr = self.udp_sock.recvfrom(RTPSocket.MTU_SIZE)
                #print('received: ' + str(data))

                pkt = RTPPacket.deserialize_and_create(data, addr)
                self._receive_packets_staging.put(pkt)
                self._unstage_packets()
            except socket.timeout:
                continue

    def _unstage_packets(self):
        self._receive_packets.put(self._receive_packets_staging.get())

    def _run_send(self):
        while self.running:
            if self.next_seq_num < self.base_num + self.window_size:
                try:
                    pkt = self._send_packets.get(timeout=1)

                    pkt.set_seq_num(self.next_seq_num)
                    self._send_packet(pkt)
                    self.next_seq_num += 1
                except Empty:
                    continue
            else:
                sleep(1)

    def _run_timer(self):
        while self.running:
            self._pending_ack_packets_lock.acquire()

            oldest_seq = self._get_oldest_seq()
            while oldest_seq is not None and self._pending_ack_packets[oldest_seq].is_expired():
                # Resend it
                pkt = self._pending_ack_packets[oldest_seq]
                self._send_packet(pkt)

                # Move to the end of the line
                del self._pending_ack_packets[oldest_seq]
                self._pending_ack_packets[oldest_seq] = pkt

                # Try the next oldest
                oldest_seq = self._get_oldest_seq()

            self._pending_ack_packets_lock.release()

            sleep(0.25)


    def _get_oldest_seq(self):
        return None if not self._pending_ack_packets else self._pending_ack_packets.iterkeys().next()

    def _send_packet(self, pkt):
        #print('sending packet: (' + packet.serialize() + ')')
        pkt.timeout = datetime.now() + timedelta(seconds=1)
        self._pending_ack_packets[self.next_seq_num] = pkt
        self.udp_sock.sendto(pkt.serialize(), (self.other_addr, self.other_port))



class RTPSocket_Mock(RTPSocket):
    def __init__(self, port, internal_socket=None):
        self.sock = internal_socket if internal_socket is not None else socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(('', port))
        self.sock.listen(1)

    def accept(self):
        client, address = self.sock.accept()
        return RTPSocket_Mock(client)

    def connect(self, address, port):
        self.sock.connect((address, port))

    def close(self):
        self.sock.close()

    def send(self, data):
        self.sock.sendall(data)

    def receive(self):
        return self.sock.recv(1024)
