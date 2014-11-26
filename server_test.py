import RTPSocket
from time import sleep

sock = RTPSocket.RTPSocket(8007)

try:
    sock.accept()
    sleep(1)
    '''
    data = sock.receive()
    while data is not None:
        print(data)
        sock.send('Received your data!')

        data = sock.receive()
    '''
finally:
    print('Closing socket')
    sock.close()