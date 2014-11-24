import RTPSocket

sock = RTPSocket.RTPSocket_Mock()
sock.connect('localhost', 4557)

sock.send('this is a test')
result = sock.receive()
print('From server: ' + str(result))

sock.close()