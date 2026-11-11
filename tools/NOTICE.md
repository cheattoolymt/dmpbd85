# Tool provenance

`analyze_frm.py` is a Python adaptation of the PITIT/PIT/BIT layouts and traversal
in [theubusu/unixtract](https://github.com/theubusu/unixtract), commit
`aadba866ea47ed9506ffe130a8558bb9147ee968`,
`src/formats/mtk_bdp/{include.rs,mod.rs}`. Upstream is GNU GPL v3.
Changes: Python standard library implementation, explicit bounds/target checks,
per-chunk extraction, all NAND variants, JSON evidence, uImage CRC validation,
ARM zImage/gzip carving and SquashFS superblock parsing. This adaptation is
GPL-3.0-only; the complete license is in `COPYING`. No upstream binaries are bundled.

SquashFS tools is used as an unmodified external command (4.6.1, GPL-2.0-or-later;
see https://github.com/plougher/squashfs-tools/tree/4.6.1 and its COPYING).
Firmware and extracted proprietary content are not licensed by this repository.

`inspect_elf.py` is new project code under GPL-3.0-only. Optional analysis
libraries are external dependencies, not copied into this repository:
[Capstone 5.0.9](https://github.com/capstone-engine/capstone) (BSD license) and
[pyelftools 0.33](https://github.com/eliben/pyelftools) (public domain, with the
upstream LICENSE describing its licenses). See `requirements-static.txt`.

`kernel_uart_report.py` and `capture_uart.py` are new project code under
GPL-3.0-only. Kernel symbol recovery uses unmodified external
[vmlinux-to-elf 1.4.0](https://github.com/marin-m/vmlinux-to-elf); its installed
wheel includes the GNU GPL v3 license. Neither the tool's sources nor its
binaries are bundled here. `capture_uart.py` uses Python's standard library.
