import multiprocessing
import logging
import argparse
import sys
import socket
import select
import os
import errno
import glob
import time

# "ship" in https://en.wikipedia.org/wiki/E.161
DEFAULT_PORT=7447

logger = logging.getLogger("logship")

# TODO configure logger


# http://stackoverflow.com/questions/600268/mkdir-p-functionality-in-python
def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc: # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else: raise

def open_file(args, remote_addr, filename):
    if args.host_in_filename:
        (host, port) = remote_addr
        filename = "%s_%s" % (host, filename) 
    full_path = os.path.join(args.storage_path, filename)
    mkdir_p(os.path.dirname(full_path))
    fh = open(full_path, "a+")
    return fh

def parse_header(header):
    # For now, the header is dead simple and is just the filename.
    filename = header.strip()
    return filename

def receiver_worker(args, sock, remote_addr):
    poller = select.poll()
    poller.register(sock.fileno(), select.POLLIN | select.POLLERR)
    file_fh = None
    while True:
        events = poller.poll(100) # 100ms timeout

        for (sock_fd, event) in events:
            if event & select.POLLIN:
                # new data waiting
                buf = sock.recv(4096)
                if len(buf) == 0:
                    # Connection closed!
                    # TODO logging, but not sure if I can just use logger
                    # here or if it's process-safe. I suspect not.
                    file_fh.close()
                    sock.close()
                    return
                else:
                    if file_fh is None:
                        # TODO logging
                        # If we have no file open yet, this first bit of data
                        # must be the header.
                        filename = parse_header(buf)
                        file_fh = open_file(args, remote_addr, filename)
                        # Seek to the end and tell the other side what
                        # offset we have.
                        file_fh.seek(0, 2)
                        sock.sendall("%d\n" % file_fh.tell())
                    else:
                        # Have header, so the contents of buf must now be
                        # data for the file.
                        file_fh.write(buf)

 
def receiver_master(args):
    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    listen_sock.bind((args.bindhost, args.port))
    listen_sock.listen(args.socket_queue_length)
    poller = select.poll()
    poller.register(listen_sock.fileno(), select.POLLIN | select.POLLERR)

    while True:
        events = poller.poll(100) # 100ms timeout

        for (fd, event) in events:
            if event & select.POLLIN:
                # New connection waiting, accept it and make a new process.
                (new_socket, remote_addr) = listen_sock.accept()
                p = multiprocessing.Process(target=receiver_worker, 
                    args=(args, new_socket, remote_addr))
                p.start()
                logging.info("New connection from '%s', started new process.", 
                    repr(remote_addr)) 


def transmitter_worker(args, path):
    sock = socket.create_connection((args.host, args.port), args.timeout)
    filename = os.path.basename(path)

    # Send the filename, wait for the expected offset from the other side.
    sock.sendall("%s\n" % filename)
    buf = sock.recv(4096)
    offset = int(buf.strip())
    # TODO debug logging
    # print "Got offset %d" % offset

    with open(path, "r") as fh:
        # Seek to the offset the remote side requested.
        fh.seek(offset)
        while True:
            buf = fh.read(4096)
            if len(buf) == 0:
                # Reached the end of the file, wait a moment for more.
                time.sleep(1)
            else:
                sock.sendall(buf)
                # TODO debug logging?
                #print "Sent %d bytes" % len(buf)
        
            # TODO check for the file being deleted (or the inode changing)
            # so we can exit and clean ourselves up.

def get_transmitter_worker(args, path):
    p = multiprocessing.Process(target=transmitter_worker, 
        args=(args, path))
    p.start()
    return p

def transmitter_master(args):
    workers = {}
    while True:
        paths = glob.glob(args.glob)

        for path in paths:
            try:
                if not workers[path].is_alive():
                    raise RuntimeError("Worker died")
            except (KeyError, RuntimeError) as ex:
                # Make a new worker for this path.
                workers[path] = get_transmitter_worker(args, path)

        # Clean up old paths that don't exist.
        # TODO This leaks for now, implement this. :)

        time.sleep(args.rescan_interval)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", action="store", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout", action="store", type=int, default=60)
    # TODO implement timeout support for rx
    subparsers = parser.add_subparsers(help='sub-command help')

    parser_rx = subparsers.add_parser('rx', help='receives logs from other hosts')
    parser_rx.set_defaults(func=receiver_master)
    parser_rx.add_argument("--bindhost", action="store", default="localhost")
    parser_rx.add_argument("--socket-queue-length", action="store", type=int, default=5)
    parser_rx.add_argument("--storage-path", action="store", default="/var/tmp/logship")
    parser_rx.add_argument("--host-in-filename", action="store", type=bool, default=True)
    
    parser_tx = subparsers.add_parser('tx', help='transmits logs to another host or hosts')
    parser_tx.set_defaults(func=transmitter_master)
    parser_tx.add_argument("--host", action="store", required=True)
    parser_tx.add_argument("--glob", action="store", required=True)
    parser_tx.add_argument("--rescan-interval", action="store", type=int, default=1)

    args = parser.parse_args()

    args.func(args)

if __name__ == "__main__":
    main()
