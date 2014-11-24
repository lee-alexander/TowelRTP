import RTPSocket

sock = RTPSocket.RTPSocket(8007)
sock.connect('localhost', 8006)

sock.send('Client: 123456789123456789')
result = sock.receive()
print('From server: ' + str(result))

sock.close()