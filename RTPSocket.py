import socket
from Queue import Queue, Empty
from collections import OrderedDict
from threading import Thread, Lock
from hashlib import md5
from time import sleep
from datetime import datetime, timedelta

class RTPPacket:
    HEADER_SIZE = 51

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
        result += self.checksum if checksum_filled else ('0' * 32)
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
        checksum = data[19:51]
        payload = data[51:] if len(data) > 51 else ''

        pkt_result = cls(payload, is_ack, is_handshake, is_disconnect, client_info, seq_num=seq_num, ack_num=ack_num)

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
        print('Waiting on handshake')
        while pkt is None or not pkt.is_handshake:
            pkt = self.pipeline.dequeue_packet()

        self.pipeline.update_client_info(pkt.client_info[0], pkt.client_info[1])
        self.connected = True
        print('Connected')

    # Connect to the server (non-blocking)
    def connect(self, address, port):
        if self.connected:
            return

        print('Connected')
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

        # Make sure pipeline hasn't closed
        if not self.pipeline.running:
            self.close(broadcast=False)

        return None if pkt is None else pkt.payload



class RTPSocketPipeline(object):
    def __init__(self, port, rtp_socket):
        self._send_packets = Queue() # input packets sent to the pipeline to transmit reliably to other side
        self._pending_ack_packets = OrderedDict() # packets that were went but not yet acknowledged
        self._pending_ack_packets_lock = Lock()
        self._receive_packets_staging = {} # buffered packets that were received out of order, stored by seq_num
        self._receive_packets = Queue() # in order and final, ready to be used by upper level
        self._queued_ack_numbers = Queue() # ACK nums that need to be carried to the other side

        self.running = False
        self.rtp_sock = rtp_socket

        self.next_seq_num = 1
        self.send_base_lock = Lock()
        self.send_base = 1
        self.rcv_base = 1
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
            except KeyboardInterrupt:
                self.stop()
                raise

        return None

    def _run_receive(self):
        while self.running:
            try:
                data, addr = self.udp_sock.recvfrom(RTPSocket.MTU_SIZE)
                pkt = RTPPacket.deserialize_and_create(data, addr)

                # Don't proceed if the checksum was invalid
                if not pkt:
                    print('Bad checksum')
                    continue

                print('Received packet: (' + pkt.serialize() + ')')

                if pkt.is_disconnect:
                    self.running = False
                    continue

                # Do sender-side stuff (ACK handling)
                if pkt.is_ack and self.send_base <= pkt.ack_num < self.send_base + self.window_size:
                    self._pending_ack_packets_lock.acquire()

                    # Mark that packet as received, if it's still there
                    if pkt.ack_num in self._pending_ack_packets:
                        del self._pending_ack_packets[pkt.ack_num]
                        self._pending_ack_packets_lock.release()

                        # If this packet was the previous window base, we need to move it forward some amount
                        if self.send_base == pkt.ack_num:
                            self.send_base_lock.acquire()

                            new_send_base = self.send_base + 1
                            while new_send_base < min(self.next_seq_num, self.send_base + self.window_size) and new_send_base not in self._pending_ack_packets:
                                new_send_base += 1
                            self.send_base = new_send_base

                            self.send_base_lock.release()
                    else:
                        self._pending_ack_packets_lock.release()


                # Do receiver-side stuff (data itself)
                if self.rcv_base - self.window_size >= pkt.seq_num < self.rcv_base:
                    # Need to resend an ACK for this one, but no further actions
                    self._queued_ack_numbers.put(pkt.seq_num)
                elif self.rcv_base >= pkt.seq_num < self.rcv_base + self.window_size:
                    # First send an ACK
                    self._queued_ack_numbers.put(pkt.seq_num)

                    # Make sure it hasn't already been received before proceeding
                    if not pkt.seq_num in self._receive_packets_staging:
                        self._receive_packets_staging[pkt.seq_num] = pkt

                        if pkt.seq_num == self.rcv_base:
                            self._unstage_ordered_packets()

            except socket.timeout:
                continue

    # Try to move as many continuous packets upwards as we can
    def _unstage_ordered_packets(self):
        while self.rcv_base in self._receive_packets_staging:
            # Remove this packet from staging
            pkt = self._receive_packets_staging[self.rcv_base]
            del self._receive_packets_staging[self.rcv_base]

            # Send it upwards
            self._receive_packets.put(pkt)

            # Move forward in the staging buffer
            self.rcv_base += 1

    def _run_send(self):
        while self.running:
            self.send_base_lock.acquire()

            ack_ferried = False
            any_packet_sent = False

            # Send any outstanding packets
            if self.next_seq_num < self.send_base + self.window_size:
                try:
                    pkt = self._send_packets.get(timeout=1)
                    pkt.set_seq_num(self.next_seq_num)

                    # Try to ferry any ACKs over
                    if not self._queued_ack_numbers.empty():
                        pkt.set_ack_num(self._queued_ack_numbers.get())
                        ack_ferried = True
                        print('Ferrying ACK')

                    print('Sending packet: (' + pkt.serialize() + ')')
                    self._send_packet(pkt)
                    self.next_seq_num += 1
                    any_packet_sent = True
                except Empty:
                    continue
                finally:
                    self.send_base_lock.release()
            else:
                self.send_base_lock.release()

            # If no data could ferry the ACK over, send a dedicated ACK message over
            if not ack_ferried and not self._queued_ack_numbers.empty():
                pkt = RTPPacket(is_ack=True, ack_num=self._queued_ack_numbers.get())
                self._send_packet(pkt, pkt_timeout=False)
                print('Sending plain ACK')

            if not any_packet_sent:
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

    def _send_packet(self, pkt, pkt_timeout=True):
        if pkt_timeout:
            self._pending_ack_packets_lock.acquire()
            self._pending_ack_packets[pkt.seq_num] = pkt
            self._pending_ack_packets_lock.release()
            pkt.timeout = datetime.now() + timedelta(seconds=1)

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
