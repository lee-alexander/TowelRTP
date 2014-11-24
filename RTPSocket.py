import socket

class RTPSocket(object):
    MTU_SIZE = 1000

    def __init__(self):
        self.sock = socket.socket()

    # Listen for client connections
    def listen(self, port):
        pass

    # Connect to the server
    def connect(self, address, port):
        pass

    # Close the RTP socket connection
    def close(self):
        pass

    # Send data to the other side
    def send(self, data):
        pass

    # Receive data from the other side into a buffer of size buffer_size
    def receive(self, buffer_size):
        pass

class RTPSocket_Mock(RTPSocket):
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def listen(self, port):
        self.sock.bind(('', port))
        self.sock.listen(1)

    def connect(self, address, port):
        self.sock.connect((address, port))

    def close(self):
        self.sock.close()

    def send(self, data):
        self.sock.send(data)

    def receive(self, buffer_size):
        self.sock.recv(buffer_size)