import RTPSocket
from time import sleep

sock = RTPSocket.RTPSocket(8006)
try:
    sock.connect('localhost', 8000)
    sock.send('I am the client and a towel I say!')

    while True:
        sleep(1)

    '''
    result = sock.receive()
    printresult = ''
    while result is not None:
        printresult += result
        result = sock.receive()

    print(printresult)
    '''
finally:
    print('Closing socket')
    sock.close()