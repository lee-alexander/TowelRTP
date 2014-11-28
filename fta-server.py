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
import time
from RTPSocket import RTPSocket
from fta_util import decodeHeader, HEADER_SIZE, encodeFileHeader, encodeMessageHeader

def listenForCommands(serverSocket):
    while True:
        command = raw_input(">")
        print "Command: " + command

        if command == "terminate":
            serverSocket.disconnect()
            os._exit(0)
        elif command[:6] == "window":
            serverSocket.set_window_size(int(command[7:]))
            print "Window size set to " + command[7:]
        else:
            print "Error: Unknown command. Please reference command list below:\n\n"\
                  "terminate:       Terminates any existing connections and stops the server.\n"\
                  "window [int]:    Takes a integer between x and z which determines the windows size"

FILE_READ_SIZE = 2048
serverPort = int(sys.argv[1])
emulatorIP = sys.argv[2]
emulatorPort = int(sys.argv[3])

#setup socket
serverSocket = RTPSocket(serverPort)

# Background thread to listen for commands
thread.start_new_thread(listenForCommands, (serverSocket,))

print "Server is up and listening\n"
try:
    while True:
        serverSocket.accept()
        data = ""

        while len(data) < HEADER_SIZE:
            r = serverSocket.receive()
            if r is None:
                serverSocket.close()
                print "Client disconnected"
                sys.exit(0)
            data += r

        error, operation, filename, fileSize = decodeHeader(data)
        if operation == "1":
            # Receiving a file from client (client is POSTing)
            progress = 0
            lastUpdate = time.time()
            outfile = open(filename, "wr")
            remaining = fileSize + HEADER_SIZE - len(data)
            outfile.write(data[HEADER_SIZE:])

            while remaining > 0:
                message = serverSocket.receive()

                if message is None:
                    print "Client disconnected"
                    serverSocket.close()
                    sys.exit(0)

                data += message
                outfile.write(message)
                remaining -= len(message)
                tick = time.time()
                progress = len(data)/float((fileSize + HEADER_SIZE))

                if tick - lastUpdate > .2:
                    updateMessage = str(int(progress * 100)) + "%"
                    serverSocket.send(encodeMessageHeader(0, "2", len(updateMessage)) + updateMessage)
                    lastUpdate = time.time()
            outfile.close()
            response = ""
            serverSocket.send(encodeMessageHeader(0, "0", len(response)) + response)
        else:
            # Client is requesting a file (client is GETing)
            if os.path.isfile(filename):
                infile = open(filename)
                serverSocket.send(encodeFileHeader(0, 1, filename) + infile.read())
                infile.close()
            else:
                serverSocket.send(encodeFileHeader(1, operation, "") + "")
finally:
    serverSocket.close()
