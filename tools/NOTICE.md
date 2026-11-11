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
