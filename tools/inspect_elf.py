#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Inspect ARM ELF strings, CLI records, symbols and optional disassembly. Never executes target."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from elftools.elf.elffile import ELFFile


def inspect(path, start=None, size=128):
    data = path.read_bytes()
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        if elf['e_machine'] != 'EM_ARM' or not elf.little_endian or elf.elfclass != 32:
            raise ValueError('expected 32-bit little-endian ARM ELF')
        loads = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']

        def file_offset(va):
            for seg in loads:
                if seg['p_vaddr'] <= va < seg['p_vaddr'] + seg['p_filesz']:
                    return seg['p_offset'] + va - seg['p_vaddr']
            return None

        def address(offset):
            for seg in loads:
                if seg['p_offset'] <= offset < seg['p_offset'] + seg['p_filesz']:
                    return seg['p_vaddr'] + offset - seg['p_offset']
            return None

        def string(va):
            off = file_offset(va)
            if off is None:
                return None
            text = data[off:off + 256].split(b'\0', 1)[0]
            if not text or any((c < 32 or c > 126) and c not in (9, 10, 13) for c in text):
                return None
            return text.decode('ascii')

        def references(va):
            pattern = re.escape(struct.pack('<I', va))
            return [dict(file_offset=m.start(), va=address(m.start()))
                    for m in re.finditer(pattern, data) if m.start() % 4 == 0]

        terms = ['Call Linux shell', 'Usage: system <cmd>', 'nmk2bp', '\nUSB-CLI Enabled ',
                 '/dev/ttyUSB0', '/dev/ttyMT0', '/dev/drvcli', 'SIGNEDSCRIPT', '/etc/shpub']
        evidence = []
        cli = []
        for term in terms:
            for match in re.finditer(re.escape(term.encode()), data):
                offset = match.start()
                va = address(offset)
                refs = references(va) if va is not None else []
                evidence.append(dict(text=term, file_offset=offset, va=va, pointer_references=refs))
                if term != 'Call Linux shell':
                    continue
                for ref in refs:
                    rowoff = ref['file_offset'] - 16
                    if rowoff < 0 or rowoff + 24 > len(data):
                        continue
                    name, alias, handler, child, helpva, rights = struct.unpack_from('<6I', data, rowoff)
                    if string(name) != 'system' or file_offset(handler & ~1) is None:
                        continue
                    rowva = address(rowoff)
                    base = rowva
                    # CLI arrays have 24-byte records, terminated by a zero record.
                    for _ in range(256):
                        prev = file_offset(base - 24)
                        if prev is None:
                            break
                        record = struct.unpack_from('<6I', data, prev)
                        if not string(record[0]) or len(string(record[0])) > 32 or not string(record[4]):
                            break
                        base -= 24
                    parents = []
                    for parentref in references(base):
                        po = parentref['file_offset'] - 12
                        if po < 0 or po + 24 > len(data):
                            continue
                        rec = struct.unpack_from('<6I', data, po)
                        if string(rec[0]) and string(rec[4]):
                            parents.append(dict(name=string(rec[0]), row_va=address(po), rights=rec[5]))
                    cli.append(dict(name='system', handler_va=handler, row_va=rowva,
                                    table_va=base, rights=rights, parents=parents))
        symbols = []
        for secname in ['.dynsym', '.symtab']:
            section = elf.get_section_by_name(secname)
            if section is not None:
                for symbol in section.iter_symbols():
                    if symbol.name in ['ipcd_exec', 'system', 'x_cli_attach_cmd_tbl', 'x_strncpy', 'x_strlen']:
                        symbols.append(dict(name=symbol.name, value=symbol['st_value'],
                                            size=symbol['st_size'], table=secname,
                                            section=symbol['st_shndx']))
        report = dict(file=path.name, sha256=hashlib.sha256(data).hexdigest(), size=len(data),
                      machine=elf['e_machine'], elf_class=elf.elfclass,
                      elf_flags=elf['e_flags'], strings=evidence, cli_commands=cli, symbols=symbols)
        if start is not None:
            from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
            from capstone.arm import ARM_INS_LDR, ARM_OP_MEM, ARM_REG_PC
            mode = CS_MODE_THUMB if start & 1 else CS_MODE_ARM
            begin = start & ~1
            offset = file_offset(begin)
            if offset is None or size < 1 or size > 65536:
                raise ValueError('invalid disassembly range')
            segment = next(s for s in loads if s['p_offset'] <= offset < s['p_offset'] + s['p_filesz'])
            if offset + size > segment['p_offset'] + segment['p_filesz']:
                raise ValueError('disassembly crosses file-backed segment')
            disassembler = Cs(CS_ARCH_ARM, mode)
            disassembler.detail = True
            instructions = []
            for ins in disassembler.disasm(data[offset:offset + size], begin):
                item = dict(va=ins.address, mnemonic=ins.mnemonic, operands=ins.op_str)
                if ins.id == ARM_INS_LDR and len(ins.operands) > 1:
                    op = ins.operands[1]
                    if op.type == ARM_OP_MEM and op.mem.base == ARM_REG_PC and not op.mem.index:
                        pc = (ins.address + (4 if mode == CS_MODE_THUMB else 8)) & ~3
                        lit = file_offset(pc + op.mem.disp)
                        if lit is not None and lit + 4 <= len(data):
                            value = struct.unpack_from('<I', data, lit)[0]
                            item['literal_u32'] = value
                            item['literal_string'] = string(value)
                instructions.append(item)
            report['disassembly'] = instructions
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--start', type=lambda x: int(x, 0), help='ELF virtual address; bit 0 selects Thumb')
    parser.add_argument('--size', type=lambda x: int(x, 0), default=128)
    args = parser.parse_args()
    try:
        report = inspect(args.elf, args.start, args.size)
    except ValueError as exc:
        parser.exit(1, f'{exc}\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
