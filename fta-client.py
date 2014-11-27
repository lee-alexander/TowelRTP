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
import time
from RTPSocket import RTPSocket
from fta_util import decodeHeader, HEADER_SIZE, encodeFileHeader, printNetworkStats


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
clientSocket = RTPSocket(7776)

response = ""
fromAddress = ""
try:
    clientSocket.connect('localhost', 7777)
    while 1:  #
        command = raw_input(">")
        if command == "connect":
            print "TODO"
        elif command[:4] == "post":
            filename = command[5:]
            try:
                originalFilename = filename
                if os.path.isfile(filename):
                    start = time.time()
                    progress = 0
                    lastUpdate = time.time()
                    infile = open(filename)  # readonly by default
                    print "Posting file '", filename, "' to server..."
                    clientSocket.send(encodeFileHeader(0, 1, filename) + infile.read())
                    infile.close()
                    done = False
                    while not done:
                        response = ''
                        while len(response) < HEADER_SIZE:
                            response += clientSocket.receive()
                        error, operation, filename, fileSize = decodeHeader(response)
                        if operation == "2":
                            remaining = fileSize + HEADER_SIZE - len(response)
                            while remaining > 0:
                                message = clientSocket.receive()
                                response += message
                                remaining -= len(message)
                            print response[HEADER_SIZE:]
                        else:
                            done = True
                            print "File was uploaded successfully."
                            totalTime = time.time() - start
                            printNetworkStats(totalTime, (os.path.getsize(originalFilename) + HEADER_SIZE)/totalTime)
                else:
                    print "File not found. Please check the file name and try again."
            except:
                print "Command: '", command, "'failed."
        elif command[:3] == "get":
            filename = command[4:]
            try:
                start = time.time()
                progress = 0
                lastUpdate = time.time()
                clientSocket.send(encodeFileHeader(0, 0, filename))
                data = ""
                while len(data) < HEADER_SIZE:
                    data += clientSocket.receive()
                if data[0] == "1":  # error repeat
                    print "File not found on server. Please check the file name and try again."
                else:
                    print "Downloading file '", filename, "' from server..."
                    error, operation, filename, fileSize = decodeHeader(data)
                    outfile = open("client-" + filename, "wr")
                    remaining = fileSize + HEADER_SIZE - len(data)
                    outfile.write(data[HEADER_SIZE:])
                    tick = 0
                    while remaining > 0:
                        message = clientSocket.receive()
                        data += message
                        outfile.write(message)
                        remaining -= len(message)
                        progress = len(data)/float((fileSize + HEADER_SIZE))
                        tick = time.time()
                        if tick - lastUpdate > .2:
                            print str(int(progress * 100)) + "%"
                            lastUpdate = time.time()
                    outfile.close()
                    end = time.time()
                    print "File '" + filename + "' downloaded successfully."
                    totalTime = end-start
                    printNetworkStats(totalTime, len(data)/totalTime)

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