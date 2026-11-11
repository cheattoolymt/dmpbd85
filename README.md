# 日本版 Panasonic DMP-BD85 ファームウェア解析

目標は、自分の実機でLinuxにアクセスし、最終的にDoomなどの自作プログラムを動かすこと。

第一段階では、日本版 `UPDATE_BD85_8.zip`（公式バージョン1.81）の形式を調べ、
Linuxカーネルと通常rootfsの抽出に成功した。実機のシェル取得はまだ達成していない。

- [解析結果・具体的な再現方法](docs/firmware-format-ja.md)
- [未使用6ピン端子・実カーネルのUART状態・受信手順](docs/six-pin-uart-ja.md)
- [実機情報・UART・USB CLIの追加解析](docs/hardware-and-access-ja.md)
- [全PIT/BITテーブルと検証結果（JSON）](reports/UPDATE_BD85_8.json)
- [読み取り専用の解析・抽出ツール](tools/analyze_frm.py)
- [ツールの出典とライセンス](tools/NOTICE.md)

ファームウェア本体、抽出されたプログラム、外部ツールのバイナリは含めない。
