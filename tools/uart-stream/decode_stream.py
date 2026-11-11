#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Validate a BD85STR1 binary capture and export falling-edge timestamps."""
import argparse
import binascii
import csv
import json
import struct
from pathlib import Path


def decode(data):
    start = data.find(b"BD85STR1")
    if start < 0:
        raise ValueError("BD85STR1 header missing: check PC baud and binary logging")
    pos, sequence, tick, value, shift = start + 8, 0, 0, 0, 0
    ticks = []
    while True:
        if pos + 8 > len(data):
            raise ValueError("truncated capture: end summary missing")
        if data[pos:pos + 2] != b"\xa5\x5a":
            raise ValueError(f"frame synchronization lost at {pos:#x}")
        kind, size, seq = struct.unpack_from("<BBH", data, pos + 2)
        if size > 64 or seq != sequence:
            raise ValueError(f"invalid length or missing frame at {pos:#x}")
        end = pos + 6 + size
        if end + 2 > len(data):
            raise ValueError("truncated frame")
        crc = struct.unpack_from("<H", data, end)[0]
        if binascii.crc_hqx(data[pos + 2:end], 0xffff) != crc:
            raise ValueError(f"CRC mismatch at {pos:#x}")
        payload = data[pos + 6:end]
        sequence = (sequence + 1) & 0xffff
        pos = end + 2
        if kind == 1:
            for byte in payload:
                value |= (byte & 0x7f) << shift
                if value > 0xffffffff or (shift == 28 and byte & 0x80):
                    raise ValueError("invalid 32-bit interval")
                if byte & 0x80:
                    shift += 7
                else:
                    tick += value
                    ticks.append(tick)
                    value = shift = 0
        elif kind == 2:
            if size != 16 or shift:
                raise ValueError("invalid summary or incomplete interval")
            duration, observed, dropped, sent = struct.unpack("<IIII", payload)
            if len(ticks) != sent or observed != sent + dropped:
                raise ValueError("edge counts do not match summary")
            return ticks, dict(duration_ms=duration, observed=observed,
                               buffer_dropped=dropped, sent=sent,
                               frames_crc_and_sequence_valid=True,
                               hardware_capture_overruns_detectable=False)
        else:
            raise ValueError(f"unknown frame type {kind}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--csv", type=Path, required=True)
    args = parser.parse_args()
    try:
        ticks, summary = decode(args.input.read_bytes())
    except ValueError as exc:
        parser.exit(1, f"Invalid capture: {exc}\n")
    with args.csv.open("x", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["index", "time_us", "delta_us"])
        previous = 0
        for index, tick in enumerate(ticks):
            writer.writerow([index, f"{tick / 2:.1f}",
                             f"{(tick - previous) / 2:.1f}" if index else ""])
            previous = tick
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
