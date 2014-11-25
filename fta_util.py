import os

HEADER_SIZE = 289


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


def encodeHeader(operation, filename):
    size = os.path.getsize(filename)
    return str(operation) + encodeFilename(filename) + encodeSize(size)


def decodeHeader(header):
    return header[0], header[1:257].strip(), int(header[257:HEADER_SIZE])

