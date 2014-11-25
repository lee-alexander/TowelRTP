import socket
from Queue import Queue, Empty
from threading import Thread

class RTPPacket:
    HEADER_SIZE = 2

    def __init__(self, payload='', is_handshake=False, is_disconnect=False, client_info=None):
        self.payload = payload
        self.is_handshake = is_handshake
        self.is_disconnect = is_disconnect
        self.client_info = client_info

    def serialize(self):
        result = ''
        result += 'T' if self.is_handshake else 'F'
        result += 'T' if self.is_disconnect else 'F'
        result += self.payload
        return result

    @classmethod
    def deserialize_and_create(cls, data, client_info=None):
        is_handshake = data[0] == 'T'
        is_disconnect = data[1] == 'T'
        payload = data[2:]

        return cls(payload, is_handshake, is_disconnect, client_info)


def split_data(data, split_size):
    return [data[i:i+split_size] for i in range(0, len(data), split_size)]


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
        self._receive_packets_staging = Queue() # possibly out of order, but correct contents
        self._receive_packets = Queue() # in order and final
        self.running = False
        self.rtp_sock = rtp_socket

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

    def stop(self):
        self.running = False
        self.receive_thread.join()
        self.send_thread.join()
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
                self._receive_packets_staging.put(RTPPacket.deserialize_and_create(data, addr))
                self._unstage_packets()
            except socket.timeout:
                continue

    def _unstage_packets(self):
        self._receive_packets.put(self._receive_packets_staging.get())

    def _run_send(self):
        while self.running:
            try:
                pkt = self._send_packets.get(timeout=1)
                self._send_packet(pkt)
            except Empty:
                continue

    def _send_packet(self, packet):
        #print('sending packet: (' + packet.serialize() + ')')
        self.udp_sock.sendto(packet.serialize(), (self.other_addr, self.other_port))



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
