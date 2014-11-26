import RTPSocket
from time import sleep

sock = RTPSocket.RTPSocket(8007)
msg = ''
try:
    sock.accept()
    sock.send('The SR receiver will acknowledge a correctly received packet whether or not it is in order. Out-of-order packets are buffered until any missing packets (that is, packets with lower sequence numbers) are received, at which point a batch of pack- ets can be delivered in order to the upper layer. Figure 3.25 itemizes the various actions taken by the SR receiver. Figure 3.26 shows an example of SR operation in the presence of lost packets. Note that in Figure 3.26, the receiver initially buffers packets 3, 4, and 5, and delivers them together with packet 2 to the upper layer when packet 2 is finally received.')

    while True:
        new_msg = sock.receive()
        if new_msg is None: break
        msg += new_msg

finally:
    print('Closing socket. Final message: ' + msg)
    sock.close()