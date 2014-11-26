import RTPSocket
from time import sleep

sock = RTPSocket.RTPSocket(8006)
try:
    sock.connect('localhost', 8000)
    sleep(1)
    '''
    sock.send('Client: 123456789123456789')

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