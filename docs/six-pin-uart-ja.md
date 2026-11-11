# 未使用6ピン端子の調査と、実カーネルのUART状態

2026-11-11追加調査。実機で未使用6ピン端子が見つかった、というユーザー報告を反映。
端子のシルク印字、1×6／2×3の配置、基板品番、測定値はまだ得られていない。
**現在、6本のピン割り当ては未確定。**

## 分かったこと

- UARTは有力な調査候補。ただし、6ピンはUARTの証拠ではなく、JTAGや製造検査用なども候補。
- 日本版1.81のカーネルから27,677個のsymbol table entriesを復元できた。
- UART consoleの送信／受信処理が実際のカーネルに入っている。
- UART出力抑制変数はBSSにあり、イメージの初期状態では0。
- 起動後の処理が変数を変更できるため、「必ずログが出る」とはまだ言えない。
- 公開ソースのGPIO23を用いる条件付きの抑制処理は、対象console_writeの分岐では確認されなかった。
  **GPIO23の操作・短絡を試す根拠はない。**

## 1. 機種の取り違えを除外

検索で多く見つかる2010年の海外DMP-BD85と、日本版2015年モデルは異なる。
2010年のサービスマニュアルのコネクター番号・ピン順は流用しない。
メーカー公開の近接世代BD81資料も比較したが、日本版BD85の6ピン割り当てを確定できる資料は得られなかった。
これは検索できた範囲の結果であり、資料が存在しないという結論ではない。

[MediaTek公式MT8553製品ページ](https://www.mediatek.com/products/blu-ray-and-dvd/mt8553)では、
シングルコア・32-bit、USB 2.0等を確認した。公式ページに周波数の記載はなく、
日本版BD85の非搭載機能をSoCの機能一覧から推定しない。

メーカー公開pinmuxヘッダー`arch/arm/mach-mt85xx/include/mach/mt8563_gpio_pinmux.h`には
`PIN_UARXD=92`、`PIN_UATXD=93`、JTAG選択定義がある。
これらはソフトウェア上の番号で、6ピン端子番号でもSoCの物理pin番号でもない。
MT8553HAATの該当packageと基板配線の一致も未確認なので、配線指示には使わない。

## 2. 実カーネルからのシンボル復元

外部ツール[vmlinux-to-elf](https://github.com/marin-m/vmlinux-to-elf) 1.4.0を無改造で使用。
ライセンスは導入wheelに付属するGPL v3全文を確認した。

入力は前回抽出したgzip展開後のカーネル4,541,216 bytes。
SHA-256：`edf7645f986e4b85105caaab3529326b4461a8809dddcf119444befb31997b7d`

復元ELFのLOAD segmentと元カーネルの全バイトが一致することを付属ツールで検証した。
復元されたベースVAは`0xc0008000`、元イメージのBSS境界は
`__bss_start=0xc045cb20`、`__bss_stop=0xc0480938`。
ELFの人工的なBSS segmentサイズから実機RAM容量を推定してはいけない。

| Symbol | カーネルVA | 確認内容 |
| --- | --- | --- |
| _mt85xx_uart_console_write | 0xc020713c | UART console出力処理 |
| _mt85xx_rx_chars | 0xc0205e04 | UART受信処理 |
| _mt85xx_uart_console_setup | 0xc042647c | console設定 |
| g_u4disable_log | 0xc047a5f0 | 元イメージのBSS内、初期値0 |
| disable_print | 0xc04620f0 | 元イメージのBSS内、初期値0 |
| _disable_ctrlc | 0xc047a5ec | 元イメージのBSS内、初期値0 |
| g_enable_log | 0xc047a6b4 | 元イメージのBSS内、初期値0 |
| sys_setlogopen | 0xc02073bc | 引数をg_u4disable_logへ保存する処理 |

console_writeの冒頭で、`g_u4disable_log == 1`の場合と
`disable_print & 1`が真の場合に出力せずreturnすることを逆アセンブルで確認した。
このほかUART hardware statusのチェックもある。
今回の分岐では`g_enable_log`やGPIO23を調べていない。
公開ソースにある複数の条件コンパイル経路を、対象バイナリへそのまま適用しない。

`sys_setlogopen`は名前からON/OFFの意味を取り違えやすいが、対象コードでは
引数1が出力抑制、0がその抑制フラグ解除に相当する。
これは既にLinux側で実行できる場合の実装情報であり、外からシェルを得る入口ではない。

## 3. 6ピンの現物確認：まず受信だけ

必要な追加情報は、端子近くの印字、基板品番、端子配列と向き。
測定時は、写真上の同じ向きを固定してA～Fなどの仮ラベルを付ける。
仮ラベルをメーカーのpin 1～6と混同しない。

| 仮ラベル | 電源断でGNDとの導通 | standby電圧 | 起動時の波形／変化 | 暫定解釈 |
| --- | --- | --- | --- | --- |
| A | 未測定 | 未測定 | 未測定 | 不明 |
| B | 未測定 | 未測定 | 未測定 | 不明 |
| C | 未測定 | 未測定 | 未測定 | 不明 |
| D | 未測定 | 未測定 | 未測定 | 不明 |
| E | 未測定 | 未測定 | 未測定 | 不明 |
| F | 未測定 | 未測定 | 未測定 | 不明 |

確認の順序：

1. DC電源・USB・HDMIを外してから、既知の電源GNDとの導通を調べる。
   HDMI外殻が信号GNDと直結とは限らないため、基準点も確認する。
2. 通電して、既知のGNDを基準に各端子の電圧を測る。
   3.3V付近で一定でも、VCCかidle中のUARTかは電圧だけでは区別できない。
   NANDのVCCが3.3VであることもUART信号電圧の証拠にはならない。
3. オシロスコープ／適合電圧のロジックアナライザーがあれば、起動直後のパルスを観測する。
   115200bpsなら1 bit約8.68µsが目安。クロック線のような連続波形も区別する。
4. TX候補と信号電圧を確認後、基板GND→受信器GND、基板TX候補→受信器RXだけを接続する。
   受信器のTX、VCC、RTS、DTRは接続しない。RS-232電圧の機器は直結しない。
5. 電源投入前に受信を開始し、115200／8N1／flow controlなしで起動ログを保存する。
   異常な文字列だけなら、電圧・GND・baud・信号反転・端子候補を再確認する。
   無出力だけではUARTでないと断定しない。

接続の一般原則は[Ubuntuの公式UART接続説明](https://ubuntu.com/hardware/docs/boards/how-to/special_hardware/uart-console/)
も参照。ただし本機のpinoutや電圧を示す資料ではない。
隣接端子の短絡、未知端子への電圧印加、reset/JTAGらしい端子の操作は、この段階では行わない。

## 4. 受信専用レコーダーを用意

`tools/capture_uart.py`はLinux PC用、Python標準ライブラリーのみで動作する。
ポートはread-onlyで開き、serial dataのwriteは行わない。
8N1に設定し、hardware/software flow controlとechoを無効にする。
termios設定は終了時に元へ戻す。コネクターの制御線は接続しない。

```sh
# device名はPC側USB–UARTのものに置き換える。既存のterminalアプリは閉じる。
python3 tools/capture_uart.py /dev/ttyUSB0 \
  --baud 115200 --seconds 30 --output work/capture-A
```

実機の電源投入前に開始する。出力先は新規ディレクトリーのみ受け付ける。
`uart.bin`に受信bytesを加工せず保存、`chunks.jsonl`に受信時刻とoffset、
`metadata.json`に設定・バイト数・SHA-256を記録する。
`chunks.jsonl`の時刻はPC側read時刻で、各bitの電気的なタイミングではない。

検証は疑似端末（PTY）を使い、CR/LF/NUL/0xff/XON/XOFFを含む列が完全に保存され、
受信器からデータが送信・echoされないこと、既存出力が上書きされないことを確認した。
**実機の6ピン端子ではまだテストしていない。**

## 5. シンボル解析の再現手順

[前回の抽出手順](firmware-format-ja.md)で`work/extracted/linux-001827b0.bin`を作成してから：

```sh
python3 -m venv work/venv
CC=gcc CXX=g++ work/venv/bin/pip install \
  -r tools/requirements-static.txt -r tools/requirements-kernel.txt
work/venv/bin/vmlinux-to-elf work/extracted/linux-001827b0.bin work/vmlinux.elf \
  > work/vmlinux-recovery.log 2>&1
work/venv/bin/python tools/kernel_uart_report.py \
  work/extracted/linux-001827b0.bin work/vmlinux.elf > work/kernel-uart.json
work/venv/bin/python tools/inspect_elf.py work/vmlinux.elf \
  --start 0xc020713c --size 0x44 > work/console-write.json
```

今回の環境ではminilzo依存のビルドがclang不在で失敗したため、
導入済みGCCを明示して成功した。環境によってはPython開発header等も必要になる。
復元ELFやカーネル本体はGitHubに含めず、[シンボル調査結果](../reports/kernel-uart.json)を保存する。

## 次の判断点

6ピン端子の印字／配置か測定値が得られれば、UART・JTAG・その他の候補を絞れる。
ログが得られたら、まず実機のファーム版、CPU/RAM、NAND認識、console割り当て、
initrdのロード・起動経路を静的解析結果と照合する。
Linux shell、U-Boot prompt、メーカー診断CLIはそれぞれ別の入口として区別する。
