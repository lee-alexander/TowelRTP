"""
This is a client for the FTA Networking protocol assignment. This file should be run via command line with the
following arguments:

X: the port number at which the fta-client's UDP socket should bind to (even number)
A: the IP address of NetEmu
P: the UDP port number of NetEmu


Example: python fta-server *TODO*

"""

import sys
import os
from RTPSocket import RTPSocket_Mock

def encodeSize(fileSize):
    encoded = str(fileSize)
    while len(encoded) < 32:
        encoded = "0"+encoded
    return encoded


def encodeFilename(filename):
    encoded = filename
    while len(encoded) < 256:
        encoded = " "+encoded
    return encoded


def encodeHeader(filename):
    size = os.path.getsize(filename)
    return encodeFilename(filename) + encodeSize(size)


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
clientSocket = RTPSocket_Mock()

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
                infile = open(filename) #readonly by default
                print "Posting file '", filename, "' to server..."
                clientSocket.send(encodeHeader(filename) + infile.read())
                infile.close()
                print "File transfer complete!"
            except:
                print "Command: '", command, "'failed. Please check your file name and try again."
        elif command[:3] == "get":
            print "TODO"
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