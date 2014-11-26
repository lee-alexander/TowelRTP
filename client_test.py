import RTPSocket
from time import sleep

sock = RTPSocket.RTPSocket(8006)
msg = ''
try:
    sock.connect('localhost', 8000)
    sock.send('It is important to note that in Step 2 in Figure 3.25, the receiver reacknowledges (rather than ignores) already received packets with certain sequence numbers below the current window base. You should convince yourself that this reacknowledgment is indeed needed. Given the sender and receiver sequence number spaces in Figure 3.23, for example, if there is no ACK for packet send_base propagating from the receiver to the sender, the sender will eventuall')

    while True:
        new_msg = sock.receive()
        if new_msg is None: break
        msg += new_msg

finally:
    print('Closing socket. Final message: ' + msg)
    sock.close()