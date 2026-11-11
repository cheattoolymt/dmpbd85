#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# PIT/BIT layout and traversal adapted from theubusu/unixtract (see NOTICE.md).
"""Read-only MediaTek BDP v1 table parser and validated image carver."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib


def analyze(data, out=None):
    def region(off, size):
        if off < 0 or size < 0 or off + size > len(data):
            raise ValueError(f'out-of-file range: {off:#x}+{size:#x}')
        return data[off:off + size]

    def unpack(fmt, off):
        return struct.unpack(fmt, region(off, struct.calcsize(fmt)))

    def save(name, content):
        if out is not None:
            target = out / name
            with target.open('xb') as f:
                f.write(content)

    marker = b'iTIPiTIP'
    candidates = [m.start() for m in re.finditer(marker, data)]
    if len(candidates) != 1:
        raise ValueError('expected exactly one PITIT marker')
    pos = candidates[0]
    if unpack('<II', pos + 8) != (1, 0):
        raise ValueError('only observed PITIT v1 layout supported')
    report = {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
              'pitit_offset': pos, 'variants': [], 'uimages': [], 'squashfs': []}
    cursor = pos + 16
    for _ in range(16):
        if unpack('<I', cursor)[0] == 0x69544950:
            break
        nand, pit, pitlen, tableid, bit, bitlen, p1, p2 = unpack('<8I', cursor)
        region(pit, pitlen)
        region(bit, bitlen)
        if region(pit, 8) != bytes.fromhex('dcea3085') * 2:
            raise ValueError('invalid PIT magic')
        ver, hdrlen, stride, count = unpack('<4I', pit + 8)
        if ver != 1 or stride != 64 or count > 256 or hdrlen + stride * count > pitlen:
            raise ValueError('invalid PIT layout')
        parts = []
        for index in range(count):
            off = pit + hdrlen + index * stride
            name = region(off, 16).split(b'\0')[0].decode('ascii')
            pid, flags, dst, length, enc_size, clear_size = unpack('<6I', off + 16)
            parts.append(dict(name=name, id=pid, flags=flags, nand_offset=dst, nand_size=length, mtd_crypt=bool(flags & 0x01000000),
                              encrypted_bytes_per_unit=enc_size, clear_bytes_per_unit=clear_size))
        if region(bit, 20) != bytes.fromhex('cdab3085') * 5:
            raise ValueError('invalid BIT magic')
        objects = []
        for off in range(bit + 20, bit + bitlen, 20):
            pid, src, size, dst, flags = unpack('<5I', off)
            if pid == 0x8530efef:
                break
            content = region(src, size)
            part = next((p for p in parts if p['id'] == pid), None)
            if part is None or dst + size > part['nand_size']:
                raise ValueError('BIT target outside PIT partition')
            name = part['name']
            if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
                raise ValueError('unsafe partition name')
            objects.append(dict(id=pid, name=name, file_offset=src, size=size,
                                target_offset=dst, flags=flags, sha256=hashlib.sha256(content).hexdigest()))
            # Separate chunks preserve file-vs-NAND offsets and never synthesize flash images.
            if tableid == 0:
                save(f'{len(objects):02d}-{name}-{dst:08x}.bin', content)
        else:
            raise ValueError('missing BIT terminator')
        report['variants'].append(dict(nand_size=nand, table_id=tableid, pit_offset=pit,
                                       pit_size=pitlen, bit_offset=bit, bit_size=bitlen,
                                       partitions=parts, objects=objects))
        cursor += 32
    else:
        raise ValueError('missing PITIT terminator')

    for match in re.finditer(re.escape(bytes.fromhex('27051956')), data):
        off = match.start()
        header = bytearray(region(off, 64))
        magic, hcrc, timestamp, size, load, entry, dcrc, osid, arch, kind, comp, name = unpack('>7I4B32s', off)
        header[4:8] = bytes(4)
        if zlib.crc32(header) != hcrc:
            continue
        payload = region(off + 64, size)
        if zlib.crc32(payload) != dcrc:
            raise ValueError('uImage data CRC mismatch')
        item = dict(offset=off, size=size, timestamp=timestamp, load=load, entry=entry,
                    os=osid, arch=arch, type=kind, compression=comp, header_crc_ok=True, data_crc_ok=True)
        save(f'uimage-{off:08x}.bin', region(off, size + 64))
        if len(payload) > 48 and struct.unpack_from('<I', payload, 36)[0] == 0x016f2818:
            item['arm_zimage'] = True
            for gz in re.finditer(b'\x1f\x8b\x08', payload):
                try:
                    decoder = zlib.decompressobj(31)
                    kernel = decoder.decompress(payload[gz.start():], 64 * 1024 * 1024)
                    if not decoder.eof:
                        continue
                except zlib.error:
                    continue
                banner = re.search(rb'Linux version [^\x00\n]+', kernel)
                if banner:
                    item['linux_banner'] = banner.group().decode('ascii', 'replace')
                    item['gzip_offset'] = off + 64 + gz.start()
                    item['kernel_size'] = len(kernel)
                    save(f'linux-{off:08x}.bin', kernel)
                    break
        report['uimages'].append(item)
    for match in re.finditer(b'hsqs', data):
        off = match.start()
        magic, inodes, timestamp, block, fragments, comp, log, flags, ids, major, minor, root, used, *tables = unpack('<5I6H8Q', off)
        if (major, minor) != (4, 0) or block != 1 << log or used < 96:
            continue
        content = region(off, used)
        report['squashfs'].append(dict(offset=off, size=used, inodes=inodes, block_size=block,
                                       compression=comp, version=f'{major}.{minor}', timestamp=timestamp,
                                       sha256=hashlib.sha256(content).hexdigest()))
        save(f'rootfs-{off:08x}.squashfs', content)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('firmware', type=Path)
    parser.add_argument('--out', type=Path, help='new empty output directory; existing directory is refused')
    args = parser.parse_args()
    if args.out:
        args.out.mkdir(parents=True, exist_ok=False)
    try:
        report = analyze(args.firmware.read_bytes(), args.out)
    except (ValueError, struct.error) as exc:
        parser.exit(1, f'Invalid/unsupported image: {exc}\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
