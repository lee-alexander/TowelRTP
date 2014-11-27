import socket
from Queue import Queue, Empty
from collections import OrderedDict
from threading import Thread, Lock
from hashlib import md5
from time import sleep
from datetime import datetime, timedelta

DEBUG_MSG = True
def log(msg):
    if DEBUG_MSG: print(msg)

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

    @classmethod
    def wrap(cls, text, color):
        return '[' + color + text + Colors.ENDC + ']'

    @classmethod
    def wraps(cls, text, color):
        return color + text + Colors.ENDC

# Handles wrapping payload data with an RTP header, and verifying/computing checksum
class RTPPacket:
    HEADER_SIZE = 56

    def __init__(self, payload='', is_ack=False, is_handshake=False, is_disconnect=False, client_info=None,
                 seq_num=0, ack_num=0, timeout=None, window_size=None):
        self.payload = payload
        self.is_ack = is_ack
        self.is_handshake = is_handshake
        self.is_disconnect = is_disconnect
        self.client_info = client_info
        self.ack_num = ack_num
        self.seq_num = seq_num
        self.timeout = timeout
        self.window_size = window_size
        self.compute_checksum()

    def set_seq_num(self, num):
        self.seq_num = num
        self.compute_checksum()

    def set_ack_num(self, num):
        self.ack_num = num
        self.is_ack = True
        self.compute_checksum()

    def set_is_handshake(self, is_handshake):
        self.is_handshake = is_handshake
        self.compute_checksum()

    def set_window_size(self, window_size):
        self.window_size = window_size
        self.compute_checksum()

    def is_expired(self):
        return datetime.now() > self.timeout

    def compute_checksum(self):
        self.checksum = md5(self.serialize(checksum_filled=False)).hexdigest()

    def has_non_ack_info(self):
        return self.seq_num > 0 or self.is_handshake or self.is_disconnect or self.payload

    def is_connect_part_2(self):
        return self.is_ack and self.is_handshake

    def is_connect_part_1(self):
        return self.is_handshake and not self.is_ack

    def is_connect(self):
        return self.is_handshake

    def serialize(self, checksum_filled=True):
        result = ''
        result += bool_str(self.is_ack)
        result += bool_str(self.is_handshake)
        result += bool_str(self.is_disconnect)
        result += str(self.seq_num).zfill(8)
        result += str(self.ack_num).zfill(8)
        result += str(self.window_size).zfill(5)
        result += self.checksum if checksum_filled else ('0' * 32)
        result += self.payload
        return result

    def debug_str(self):
        result = ''

        if not self.has_non_ack_info(): return Colors.wrap('ACK ' + str(self.ack_num), Colors.OKGREEN)

        if self.is_ack: result += Colors.wrap('ACK', Colors.OKGREEN)
        if self.is_handshake: result += Colors.wrap('SYN', Colors.OKGREEN)
        if self.is_disconnect: result += Colors.wrap('FIN', Colors.FAIL)
        if self.seq_num > 0: result += Colors.wrap('Seq: ' + str(self.seq_num), Colors.OKBLUE)
        if self.is_ack: result += Colors.wrap('Ack: ' + str(self.ack_num), Colors.OKBLUE)
        result += Colors.wrap('Win: ' + str(self.window_size), Colors.OKBLUE)
        result += (self.payload[:45] + '..') if len(self.payload) > 45 else self.payload
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
        window_size = int(data[19:24])
        checksum = data[24:56]
        payload = data[56:] if len(data) > 56 else ''

        pkt_result = cls(payload, is_ack, is_handshake, is_disconnect, client_info, seq_num=seq_num, ack_num=ack_num,
                         window_size=window_size)

        result = pkt_result if checksum == pkt_result.checksum else None

        if result is None:
            log(Colors.wrap('Bad checksum', Colors.FAIL))

        return result


def split_data(data, split_size):
    return [data[i:i+split_size] for i in range(0, len(data), split_size)]

def bool_str(bool):
    return 'T' if bool else 'F'

def str_bool(str):
    return str == 'T'

# Light wrapper around RTPSocketPipeline that deals with data at the bytestream level of abstraction
class RTPSocket(object):
    MTU_SIZE = 70

    def __init__(self, port):
        # Pipeline threads for updating send/receive buffers using UDP socket info
        self._pipeline = RTPSocketPipeline(port, self)
        self._pipeline.start()

    # Wait for a connection from a client (blocking)
    def accept(self):
        self._pipeline.await_connection()

    # Connect to a server (blocking)
    def connect(self, address, port):
        return self._pipeline.connect(address, port)

    # Disconnect from the server (non-blocking)
    def disconnect(self):
        self._pipeline.disconnect()

    # Close the RTP socket connection (non-blocking)
    def close(self):
        self._pipeline.stop()

    # Send data to the other side (non-blocking)
    def send(self, data):
        for chunk in split_data(data, RTPSocket.MTU_SIZE - RTPPacket.HEADER_SIZE):
            self._pipeline.enqueue_packet_to_send(RTPPacket(chunk))

    # Receive data from the other side (blocking)
    def receive(self):
        pkt = self._pipeline.dequeue_packet()
        msg = None if pkt is None else pkt.payload

        while self._pipeline.has_packet():
            pkt = self._pipeline.dequeue_packet()
            msg += '' if pkt is None else pkt.payload

        return msg

    def set_window_size(self, window_size):
        self._pipeline.set_window_size(window_size)


# Bulk of the RTP protocol code. Handles data at the packet level of abstraction. Ensures reliable delivery
# to the other side and handles connection management
class RTPSocketPipeline(object):
    PACKET_TIMEOUT = 1

    def __init__(self, port, rtp_socket):
        self.running = False
        self.rtp_sock = rtp_socket
        self.send_window_size = 10
        self.receive_window_size = 10
        self.reset_connection()

        # For thread control
        self._pending_ack_packets_lock = Lock()
        self.send_base_lock = Lock()

        # Internal UDP Socket initialization
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_sock.bind(('', port))
        self.udp_sock.settimeout(.01)

    # Initialize our RTP connection data structures and variables
    def reset_connection(self):
        self.connected = False
        self.handshaking = False
        self.received_part_1 = False
        self.received_part_2 = False
        self.other_addr = None
        self.other_port = None
        self.kill_time = None
        self.next_seq_num = 1
        self.send_base = 1
        self.rcv_base = 1
        self.part_2_expected_syn_ack = None
        self.part_3_expected_ack = None
        self._send_packets = Queue() # input packets sent to the pipeline to transmit reliably to other side
        self._pending_ack_packets = OrderedDict() # packets that were went but not yet acknowledged
        self._receive_packets_staging = {} # buffered packets that were received out of order, stored by seq_num
        self._receive_packets = Queue() # in order and final, ready to be used by upper level
        self._queued_ack_numbers = Queue() # ACK nums that need to be carried to the other side

    def update_client_info(self, other_addr, other_port):
        self.other_addr = other_addr
        self.other_port = other_port

    def start(self):
        self.running = True
        self.transfer_thread = Thread(target=self._run_transfer, name='TransferThread')
        self.transfer_thread.start()

    def stop(self):
        self.connected = False
        self.running = False
        self.transfer_thread.join()
        self.udp_sock.close()

    def await_connection(self):
        while not self.connected:
            sleep(1)

        log('\n' + Colors.wrap('Connected. Receive Base: ' + str(self.rcv_base), Colors.OKGREEN) + '\n')

    def connect(self, address, port):
        self.update_client_info(address, port)
        self.enqueue_packet_to_send(RTPPacket(is_handshake=True))
        self.await_connection()

    def disconnect(self):
        self.enqueue_packet_to_send(RTPPacket(is_disconnect=True))
        while self.connected:
            sleep(1)

    def enqueue_packet_to_send(self, pkt):
        self._send_packets.put(pkt)

    def set_window_size(self, window_size):
        self.receive_window_size = window_size

    def has_packet(self):
        return not self._receive_packets.empty()

    def print_debug(self):
        log('\n\nReceive base: ' + str(self.rcv_base) + '; Send Base: ' + str(self.send_base) + '; Next Seq: ' + str(self.next_seq_num))
        log('Receive window: ' + str(self.receive_window_size) + '; Send window: ' + str(self.send_window_size) + '\n')

    def dequeue_packet(self):
        while self.running and self.connected:
            try:
                return self._receive_packets.get(timeout=1)
            except Empty:
                continue

        if not self._receive_packets.empty():
            return self._receive_packets.get()

    # Thread that handles sending and receiving from the underlying socket, and associated processing
    def _run_transfer(self):
        while self.running:
            self._receive_and_process_packets()
            self._send_pending_packets()
            self._check_timers()

            if self.kill_time is not None and datetime.now() > self.kill_time:
                self.connected = False

    def _check_timers(self):
        self._pending_ack_packets_lock.acquire()

        oldest_seq = self._get_oldest_seq()
        while oldest_seq is not None and self.in_send_window(oldest_seq) and self._pending_ack_packets[oldest_seq].is_expired():
            # Resend it
            log(Colors.wraps('RESEND: [' + str(oldest_seq) + ']', Colors.WARNING))
            pkt = self._pending_ack_packets[oldest_seq]
            self._send_packet(pkt, lock=False)

            # Move to the end of the line
            del self._pending_ack_packets[oldest_seq]
            self._pending_ack_packets[oldest_seq] = pkt

            # Try the next oldest
            oldest_seq = self._get_oldest_seq()

        self._pending_ack_packets_lock.release()

    def _receive_and_process_packets(self):
        try:
            data, addr = self.udp_sock.recvfrom(RTPSocket.MTU_SIZE)
            pkt = RTPPacket.deserialize_and_create(data, addr)

            # Don't proceed if the checksum was invalid
            if not pkt:
                return True

            log('R: (' + pkt.debug_str() + ')')

            # Watch for disconnect
            if pkt.is_disconnect:
                if pkt.is_ack:
                    self.connected = False
                    return
                else:
                    self.kill_time = datetime.now() + timedelta(seconds=5)
                    self._send_packet(RTPPacket(is_disconnect=True, is_ack=True, seq_num=self.next_seq_num))
                    self.next_seq_num += 1

            # Watch for handshake-specific packets
            if self._process_handshake_packet(pkt):
                return True

            # Watch for a change in window
            if self.send_window_size != pkt.window_size:
                self._update_send_window(pkt.window_size)

            # SENDER-side stuff (Receive ACKs for things we sent and adjust send window accordingly)
            if pkt.is_ack and self.in_send_window(pkt.ack_num):
                self._pending_ack_packets_lock.acquire()

                # Mark that packet as received, if it's still there
                if pkt.ack_num in self._pending_ack_packets:
                    del self._pending_ack_packets[pkt.ack_num]
                    self._pending_ack_packets_lock.release()

                    # If this packet was the previous window base, we need to move it forward some amount
                    if self.send_base == pkt.ack_num:
                        self._move_send_window()
                else:
                    self._pending_ack_packets_lock.release()

            # RECEIVER-side stuff (Accept incoming data and send ACKs to the other side for it)
            if pkt.has_non_ack_info():
                if self.rcv_base - self.receive_window_size <= pkt.seq_num < self.rcv_base:
                    # Need to resend an ACK for this one, but no further actions
                    log(Colors.wraps('QUEUE Ack (Duplicate) [' + str(pkt.seq_num) + ']', Colors.WARNING))
                    self._queued_ack_numbers.put(pkt.seq_num)
                elif self.rcv_base <= pkt.seq_num < self.rcv_base + self.receive_window_size:
                    self._queued_ack_numbers.put(pkt.seq_num)
                    self._stage_packet(pkt)
                else:
                    log(Colors.wrap('[Received out of range packet. Window Base: ' + str(self.rcv_base) + '; this seq: ' + str(pkt.seq_num) + '*', Colors.WARNING))
            else:
                self._stage_packet(pkt)

        except socket.timeout:
            return False

        return True

    def in_send_window(self, num):
        return self.send_base <= num < self.send_base + self.send_window_size

    # Perform actions when receiving a connection handshake packet
    def _process_handshake_packet(self, pkt):
        # Server receives PART 1
        if pkt.is_connect_part_1():
            if not self.received_part_1:
                self.received_part_1 = True
                self._update_rcv_base(pkt.seq_num + 1)
                self.update_client_info(pkt.client_info[0], pkt.client_info[1])

                # Send part 2 (the SYN/ACK)
                self.enqueue_packet_to_send(RTPPacket(is_ack=True, ack_num=pkt.seq_num, is_handshake=True))

            return True

        # Client receives PART 2
        if pkt.is_connect_part_2():
            if not self.received_part_2:
                self.received_part_2 = True
                self.connected = True
                self._update_rcv_base(pkt.seq_num + 1)

                # Mark Part1 as received
                del self._pending_ack_packets[pkt.ack_num]
                self._move_send_window()

            # Send part 3 (the final ACK) even if we already sent it before
            self._queued_ack_numbers.put(pkt.seq_num)

            return True

        # Server receives PART 3
        if not self.connected and pkt.is_ack and pkt.ack_num == self.part_3_expected_ack:
            self.connected = True

        return False

    def _stage_packet(self, pkt):
        # Make sure it hasn't already been received before proceeding
        if not pkt.seq_num in self._receive_packets_staging:
            self._receive_packets_staging[pkt.seq_num] = pkt

            if pkt.seq_num == self.rcv_base:
                self._unstage_ordered_packets()

    def _update_send_window(self, new_value):
        self.send_window_size = new_value

    # Try to move the send window forward
    def _move_send_window(self):
        self.send_base_lock.acquire()

        new_send_base = self.send_base + 1
        while new_send_base < self.next_seq_num and new_send_base not in self._pending_ack_packets:
            new_send_base += 1
        self.send_base = new_send_base

        self.send_base_lock.release()

    def _update_rcv_base(self, value):
        self.rcv_base = value
        self._unstage_ordered_packets()

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

    def _send_pending_packets(self):
        self.send_base_lock.acquire()

        ack_ferried = False
        any_packet_sent = False

        # Send any outstanding packets
        if self.next_seq_num < self.send_base + self.send_window_size:
            self.send_window_full = False
            try:
                pkt = self._send_packets.get(timeout=0.01)
                pkt.set_seq_num(self.next_seq_num)

                # Try to ferry any ACKs over
                if not self._queued_ack_numbers.empty():
                    pkt.set_ack_num(self._queued_ack_numbers.get())
                    ack_ferried = True

                self._send_packet(pkt)
                self.next_seq_num += 1
                any_packet_sent = True
            except Empty:
                pass
            finally:
                self.send_base_lock.release()
        else:
            if not self.send_window_full:
                log(Colors.wrap('*Send window full*', Colors.WARNING))
                self.send_window_full = True

            self.send_base_lock.release()

        # If no data could ferry the ACK over, send a dedicated ACK message over
        if not ack_ferried and not self._queued_ack_numbers.empty():
            pkt = RTPPacket(is_ack=True, ack_num=self._queued_ack_numbers.get())
            self._send_packet(pkt, pkt_timeout=False)
            any_packet_sent = True

        return any_packet_sent

    def _get_oldest_seq(self):
        return None if not self._pending_ack_packets else self._pending_ack_packets.iterkeys().next()

    def _send_packet(self, pkt, pkt_timeout=True, lock=True):
        if pkt_timeout:
            if lock: self._pending_ack_packets_lock.acquire()
            self._pending_ack_packets[pkt.seq_num] = pkt
            if lock: self._pending_ack_packets_lock.release()
            pkt.timeout = datetime.now() + timedelta(seconds=RTPSocketPipeline.PACKET_TIMEOUT)

        # Special record keeping for Syn/Ack and Ack
        if pkt.is_connect_part_2():
            self.part_3_expected_ack = pkt.seq_num
        elif pkt.is_connect_part_1():
            self.part_2_expected_syn_ack = pkt.seq_num

        # Add on window size to the packet
        pkt.set_window_size(self.receive_window_size)

        log('S: (' + pkt.debug_str() + ')')
        self.udp_sock.sendto(pkt.serialize(), (self.other_addr, self.other_port))