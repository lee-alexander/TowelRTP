import os

HEADER_SIZE = 290


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


def encodeFileHeader(error, operation, filename):
    if operation == 1:
        size = os.path.getsize(filename)
    else:
        size = 0
    return str(error) + str(operation) + encodeFilename(filename) + encodeSize(size)


def encodeMessageHeader(error, operation, messageLength):
    return str(error) + str(operation) + encodeFilename("") + encodeSize(messageLength)


def decodeHeader(header):
    return header[0], header[1], header[2:258].strip(), int(header[258:HEADER_SIZE])


def printNetworkStats(time, rate):
    print "Network Stats:"
    print "Total time: " + str(time) + " seconds"
    print "Network Rate: " + str(rate) + " bytes per second"

