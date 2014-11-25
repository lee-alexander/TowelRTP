"""
This is a client for the FTA Networking protocol assignment. This file should be run via command line with the
following arguments:

X: the port number at which the fta-client's UDP socket should bind to (even number)
A: the IP address of NetEmu
P: the UDP port number of NetEmu


Example: python fta-server *TODO*

"""
import os

import sys
from RTPSocket import RTPSocket
from fta_util import decodeHeader, HEADER_SIZE, encodeHeader


if len(sys.argv) != 4:
    print "Entered incorrect number of arguments"
    print "Please use following command: python remotecalc-tcp.py <client port> <NetEmu IP> <NetEmu Port>"
    sys.exit(0)

servername = ""
serverPort = ""


#pull out arguments
clientPort = int(sys.argv[1])
netEmuIp = sys.argv[2]
netEmuPort = sys.argv[3]

#socket setup
clientSocket = RTPSocket(7798)

response = ""
fromAddress = ""
try:
    clientSocket.connect('localhost', 7799)
    while 1:  #
        command = raw_input(">")
        if command == "connect":
            print "TODO"
        elif command[:4] == "post":
            filename = command[5:]
            try:
                if os.path.isfile(filename):
                    infile = open(filename)  # readonly by default
                    print "Posting file '", filename, "' to server..."
                    clientSocket.send(encodeHeader(1, filename) + infile.read())
                    infile.close()
                    print "File transfer complete!"
                else:
                    print "File not found. Please check the file name and try again."
            except:
                print "Command: '", command, "'failed."
        elif command[:3] == "get":
            filename = command[4:]
            try:
                clientSocket.send(encodeHeader(0, filename))
                data = clientSocket.receive()
                operation, filename, fileSize = decodeHeader(data)
                outfile = open("client-" + filename, "wr")
                remaining = fileSize + HEADER_SIZE - len(data)
                outfile.write(data[HEADER_SIZE:])
                while remaining > 0:
                    data = clientSocket.receive()
                    outfile.write(data)
                    remaining -= len(data)
                outfile.close()
            except:
                print "Command: '", command, "'failed. Please check your file name and try again."
        elif command[:6] == "window":
            print "TODO"
        elif command == "disconnect":
            print "TODO"
        else:
            print "Error: Unknown command. Please reference command list below:\n\n" \
                  "connect:       Terminates any existing connections and stops the server.\n" \
                  "window [int]:  Takes a integer between x and z which determines the windows size.\n" \
                  "post [file]:   Upload a file to the server.\n" \
                  "get [file]:    Try to retrieve a file from the server.\n" \
                  "disconnect:    Terminates any existing connections and stops the server.\n"
except:
    print "Error: ", sys.exc_info()
finally:
    clientSocket.close()