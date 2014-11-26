import RTPSocket
from time import sleep

sock = RTPSocket.RTPSocket(8007)

try:
    sock.accept()
    sock.send('I am a server arghhh!')

    while True:
        sleep(1)
    '''
    data = sock.receive()
    while data is not None:
        print(data)

        data = sock.receive()
    '''
finally:
    print('Closing socket')
    sock.close()