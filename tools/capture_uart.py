#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Linux receive-only UART recorder: no serial data writes; saves exact bytes."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import termios
import time


def capture(device, output, baud=115200, seconds=30):
    speed = getattr(termios, f'B{baud}', None)
    if speed is None or seconds <= 0 or seconds > 600:
        raise ValueError('unsupported baud or duration (must be 0 < seconds <= 600)')
    output.mkdir(parents=True, exist_ok=False)
    fd = None
    original = None
    started = time.monotonic()
    meta = dict(device=device, baud=baud, framing='8N1', flow_control='none',
                started_utc=datetime.now(timezone.utc).isoformat(),
                serial_data_write_calls=0, bytes_received=0, stopped='duration')
    digest = hashlib.sha256()
    try:
        fd = os.open(device, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
        fcntl.ioctl(fd, termios.TIOCEXCL)
        original = termios.tcgetattr(fd)
        attrs = termios.tcgetattr(fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[2] &= ~(termios.CSIZE | termios.PARENB | termios.CSTOPB | getattr(termios, 'CRTSCTS', 0))
        attrs[2] |= termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[3] = 0
        attrs[4] = speed
        attrs[5] = speed
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        started = time.monotonic()
        deadline = started + seconds
        with (output / 'uart.bin').open('xb') as sink, (output / 'chunks.jsonl').open('x') as chunks:
            while (remaining := deadline - time.monotonic()) > 0:
                if not select.select([fd], [], [], min(remaining, 0.5))[0]:
                    continue
                try:
                    data = os.read(fd, 65536)
                except BlockingIOError:
                    continue
                if not data:
                    meta['stopped'] = 'device-eof'
                    break
                offset = meta['bytes_received']
                sink.write(data)
                digest.update(data)
                meta['bytes_received'] += len(data)
                chunks.write(json.dumps(dict(seconds_since_start=round(time.monotonic() - started, 6),
                                             offset=offset, size=len(data))) + '\n')
    except KeyboardInterrupt:
        meta['stopped'] = 'keyboard-interrupt'
    except Exception as exc:
        meta['stopped'] = 'error'
        meta['error'] = str(exc)
        raise
    finally:
        if fd is not None:
            try:
                if original is not None:
                    termios.tcsetattr(fd, termios.TCSANOW, original)
            finally:
                try:
                    fcntl.ioctl(fd, termios.TIOCNXCL)
                finally:
                    os.close(fd)
        meta['elapsed_seconds'] = round(time.monotonic() - started, 6)
        meta['sha256'] = digest.hexdigest()
        (output / 'metadata.json').write_text(json.dumps(meta, indent=2) + '\n')
    return meta


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('device', help='PC serial adapter device, for example /dev/ttyUSB0')
    p.add_argument('--output', type=Path, required=True, help='new capture directory')
    p.add_argument('--baud', type=int, default=115200)
    p.add_argument('--seconds', type=float, default=30)
    args = p.parse_args()
    try:
        meta = capture(args.device, args.output, args.baud, args.seconds)
    except (OSError, ValueError, termios.error) as exc:
        p.exit(1, f'Capture failed: {exc}\n')
    print(json.dumps(meta, indent=2))


if __name__ == '__main__':
    main()
