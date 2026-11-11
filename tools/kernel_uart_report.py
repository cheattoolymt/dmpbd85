#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Report selected recovered kernel symbols after validating raw/ELF byte mapping."""
import argparse
import hashlib
import json
from pathlib import Path
from elftools.elf.elffile import ELFFile


def analyze(raw_path, elf_path):
    raw = raw_path.read_bytes()
    with elf_path.open('rb') as stream:
        elf = ELFFile(stream)
        if elf['e_machine'] != 'EM_ARM' or elf.elfclass != 32 or not elf.little_endian:
            raise ValueError('expected 32-bit little-endian ARM ELF')
        table = elf.get_section_by_name('.symtab')
        if table is None:
            raise ValueError('missing recovered symbol table')
        symbols = {s.name: s for s in table.iter_symbols() if s.name}
        segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
        matching = [s for s in segments if s['p_filesz'] == len(raw) and s.data() == raw]
        if len(matching) != 1:
            raise ValueError('ELF load segment does not exactly match original raw kernel')
        mapped = matching[0]
        base = mapped['p_vaddr']
        if symbols['_text']['st_value'] != base:
            raise ValueError('_text does not match verified load mapping')
        bss_start = symbols['__bss_start']['st_value']
        bss_stop = symbols['__bss_stop']['st_value']
        if bss_start != base + len(raw) or bss_stop <= bss_start:
            raise ValueError('unexpected original kernel BSS boundaries')
        selected = ['_text', '_stext', '__bss_start', '__bss_stop',
                    'g_u4disable_log', 'disable_print', 'g_enable_log',
                    '_disable_ctrlc', '_disable_rx', 'g_gpio_control_log',
                    '_mt85xx_uart_console_write', '_mt85xx_uart_console_setup',
                    '_mt85xx_rx_chars', 'sys_setlogopen', 'uart_disable_ctrlc',
                    '_mt85xx_late_console_init', '_mt85xx_uart_reg']
        records = []
        for name in selected:
            symbol = symbols.get(name)
            if symbol is None:
                records.append(dict(name=name, found=False))
                continue
            va = symbol['st_value']
            item = dict(name=name, found=True, va=va)
            if bss_start <= va < bss_stop:
                item.update(storage='original-bss', zero_initialized=True)
            elif base <= va < base + len(raw):
                offset = va - base
                item.update(storage='raw-kernel', raw_offset=offset)
                item['first_32_bytes_sha256'] = hashlib.sha256(raw[offset:offset + 32]).hexdigest()
            records.append(item)
        return dict(raw_sha256=hashlib.sha256(raw).hexdigest(), raw_size=len(raw),
                    elf_sha256=hashlib.sha256(elf_path.read_bytes()).hexdigest(),
                    mapping_verified_byte_for_byte=True, load_va=base,
                    symbol_count=table.num_symbols(), bss_start=bss_start, bss_stop=bss_stop,
                    note='Recovered symbol addresses and image initial state; not a running-device measurement.',
                    symbols=records)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('raw_kernel', type=Path)
    p.add_argument('recovered_elf', type=Path)
    args = p.parse_args()
    try:
        report = analyze(args.raw_kernel, args.recovered_elf)
    except (KeyError, ValueError) as exc:
        p.exit(1, f'{exc}\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
