import RTPSocket

sock = RTPSocket.RTPSocket_Mock()
sock.listen(4557)

try:
    while True:
        client = sock.accept()
        data = client.receive(128)

        print(str(data))

        client.send('Received your data!')
        client.close()
finally:
    sock.close()