import socket
from Queue import Queue
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
    MTU_SIZE = 10

    def __init__(self, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('', port))
        self.sock.settimeout(1)
        self.other_addr = None
        self.other_port = None
        self.connected = False
        self.open = True
        self.buffer = Queue()
        self.background_thread = Thread(target=self._receive_packets)
        self.background_thread.start()

    # Wait for a client to accept (Blocking)
    def accept(self):
        if self.connected:
            return

        pkt = None
        while pkt is None or not pkt.is_handshake:
            pkt = self.buffer.get()

        self.other_addr = pkt.client_info[0]
        self.other_port = pkt.client_info[1]
        self.connected = True

    # Connect to the server (Blocking)
    def connect(self, address, port):
        if self.connected:
            return

        self.other_addr = address
        self.other_port = port

        self._send_packet(RTPPacket(is_handshake=True))
        self.connected = True

    # Close the RTP socket connection
    def close(self, broadcast=True):
        if not self.connected:
            return

        self.connected = False
        self.open = False
        if broadcast:
            self._send_packet(RTPPacket(is_disconnect=True))
        self.sock.close()

    # Send data to the other side (Blocking)
    def send(self, data):
        if not self.connected:
            return

        chunks = split_data(data, RTPSocket.MTU_SIZE - RTPPacket.HEADER_SIZE)

        for chunk in chunks:
            self._send_packet(RTPPacket(chunk))

    def _send_packet(self, packet):
        self.sock.sendto(packet.serialize(), (self.other_addr, self.other_port))

    # Receive data from the other side (Blocking if buffer is empty)
    def receive(self):
        return self.buffer.get().payload

    # This is running in the background for the duration of the session
    def _receive_packets(self):
        while self.open:
            try:
                data, addr = self.sock.recvfrom(RTPSocket.MTU_SIZE)
            except socket.timeout:
                continue

            pkt = RTPPacket.deserialize_and_create(data, addr)

            if pkt.is_disconnect:
                self.close(broadcast=False)

            self.buffer.put(pkt)


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
