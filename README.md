logship
======

A proof-of-concept for a service that continuously ships an ever-growing, ever-changing set of binary or text log files across the network to another machine. Supports resuming interrupted transfers, and picks up from where it left off if a file is appended to while logship is down.

Usage
-------
Basic
```shell
$ python logship.py --help
usage: logship.py [-h] [--port PORT] [--timeout TIMEOUT] {rx,tx} ...

positional arguments:
  {rx,tx}            sub-command help
    rx               receives logs from other hosts
    tx               transmits logs to another host or hosts

optional arguments:
  -h, --help         show this help message and exit
  --port PORT
  --timeout TIMEOUT
```

Receiver
```shell
$ python logship.py rx --help
usage: logship.py rx [-h] [--bindhost BINDHOST]
                     [--socket-queue-length SOCKET_QUEUE_LENGTH]
                     [--storage-path STORAGE_PATH]
                     [--host-in-filename HOST_IN_FILENAME]

optional arguments:
  -h, --help            show this help message and exit
  --bindhost BINDHOST
  --socket-queue-length SOCKET_QUEUE_LENGTH
  --storage-path STORAGE_PATH
  --host-in-filename HOST_IN_FILENAME
```

Transmitter
```shell
$ python logship.py tx --help
usage: logship.py tx [-h] --host HOST --glob GLOB
                     [--rescan-interval RESCAN_INTERVAL]

optional arguments:
  -h, --help            show this help message and exit
  --host HOST
  --glob GLOB
  --rescan-interval RESCAN_INTERVAL
```

Receiver
----------

Listens on localhost:7447, writes files to /var/tmp/logship/

```shell
$ python logship.py rx
```

Transmitter
--------------

Watches for new files matching ```/var/tmp/logship_inputs/*.log```. When any are found, they are transferred to the rx service running on ```localhost```. When new files matching this pattern are created, they are opened and transferred.

```shell
$ python logship.py tx --host localhost --glob '/var/tmp/logship_inputs/*.log'
```

Protocol
----------
When a connection is opened:
* The transmitter sends the local filename without path and with a newline: "foo.log\n"
* The receiver reads until the first newline, and assumes any content before this is a filename. It gets: "foo.log"
* The receiver checks for a file in the storage directory matching "foo.log", optionally prepending the IP of the transmitter, to avoid duplicates from multiple transmitters.
* The receiver opens the file, seeks to the end, and sends the offset (in bytes) to the transmitter. If the file is new, it will be created and the offset is zero. The format is the string representation of the integer offset in bytes, followed by a newline: "1234\n"
* The transmitter reads until the first newline, and assumes any content before this is the offset. It gets: "0"
* The transmitter seeks to this offset, and begins reading.
* Any content the transmitter is able to read is sent immediately to the receiver. From this point on, the traffic is not inspected by logship and arbitrary binary can be safely sent.

Bugs
------
* You betcha.

Future work
--------------
* The other 99%.
* More seriously, there are some TODOs in the code for next steps.
