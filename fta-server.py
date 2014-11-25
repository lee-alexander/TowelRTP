"""
This is a server for the FTA Networking protocol assignment. This file should be run via command line with the
following arguments:

X: the port number at which the fta-server's UDP socket should bind to (odd number)
A: the IP address of NetEmu
P: the UDP port number of NetEmu


Example: python fta-server *TODO*

"""
import os

import sys
import thread
from RTPSocket import RTPSocket_Mock
from fta_util import decodeHeader, HEADER_SIZE, encodeHeader


def listenForCommands(serverSocket):
    while 1:
        command = raw_input(">")
        print "Command: " + command
        if command.strip() == "terminate":
            serverSocket.close()
            os._exit(1)
        elif command[:6] == "window":
            #TODO
            print "TODO"
        else:
            print "Error: Unknown command. Please reference command list below:\n\n" \
                  "terminate:       Terminates any existing connections and stops the server.\n" \
                  "window [int]:    Takes a integer between x and z which determines the windows size"

FILE_READ_SIZE = 2048

serverPort = int(sys.argv[1])
emulatorIP = sys.argv[2]
emulatorPort = int(sys.argv[3])

#setup socket
serverSocket = RTPSocket_Mock()

try:
    thread.start_new_thread(listenForCommands, (serverSocket,))
except:
    print "Error: ", sys.exc_info()

print "Server is up and listening\n"
try:
    serverSocket.listen(serverPort)
    while 1:  # start listening and never stop
        client = serverSocket.accept()
        data = client.receive()
        operation, filename, fileSize = decodeHeader(data)
        if operation == 1:  # post
            outfile = open("server-" + filename, "wr")
            remaining = fileSize + HEADER_SIZE - len(data)
            outfile.write(data[HEADER_SIZE:])
            while remaining > 0:
                data = client.receive()
                outfile.write(data)
                remaining -= len(data)
            outfile.close()
        else:  # get
            infile = open("server-" + filename)
            client.send(encodeHeader(operation, filename) + infile.read())
            infile.close()
except:
    print "Error: ", sys.exc_info()
finally:
    serverSocket.close()
