import RTPSocket

sock = RTPSocket.RTPSocket(8006)

try:
    sock.accept()

    while sock.connected:
        data = sock.receive()
        print(str(data))

        sock.send('Received your data!')
finally:
    sock.close()