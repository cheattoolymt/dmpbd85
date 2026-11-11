# 実機情報を反映した追加解析：NAND、UART、USB CLI

調査日：2026-11-11。入力は前回と同じ日本版1.81のFRM。
この文書のELFアドレスは、明記したファイル内の**仮想アドレス（VA）**。
FRMのオフセットや実機基板の配線位置とは異なる。

## 1. ハードウェア情報

| 部品 | 実機からの報告 | 確認・解釈 |
| --- | --- | --- |
| SoC | MediaTek ARM MT8553HAAT | ユーザーの目視情報。ファーム中のmt8553と一致 |
| RAM | SK hynix HSTQ2G63FFR | `H5TQ2G63FFR`の可能性。先頭S/5と末尾速度gradeは未確認 |
| 不揮発メモリー | Toshiba x64504、追加でTC58NVG1S3HTAl0 | 製品型番はTC58NVG1S3HTAI0と読むのが有力。x64504の意味は未確定 |

[KIOXIAの公式製品資料](https://apac.kioxia.com/content/dam/kioxia/shared/business/memory/slc-nand/asset/productbrief/KIOXIA_SLCNAND_Product_Brief.pdf)
にTC58NVG1S3HTAI0が掲載されており、**2 Gbit = 256 MiB**のraw NAND、x8系、
VCC 2.70～3.60V、TSOP48、pageが2048+128 bytesと確認できる。
8ピンSPI NORやeMMCとは異なるため、それらの読み取り手順は適用しない。

同系列の[メーカーdatasheet](https://www.kioxia.com/content/dam/kioxia/newidr/productinfo/datasheet/202502/DST_TC58NVG1S3HTA00-TDE_EN_31442.pdf)
と公開LinuxソースのNAND ID表は、block=64 pages、2048 blocks、8-bit ECC/512 bytesを示す。
メイン領域256 MiBにOOBを加えると272 MiB（285,212,672 bytes）。
ダンプ比較では、OOB/ECCとbad blockの扱いを明記する必要がある。

RAMが`H5TQ2G63FFR`であれば、[SK hynix発行のdatasheet（ミラー）](https://www.bulcomp-eng.com/datasheet/H5TQ2G63FFR-PBC%20%28BGA%29%20-%20Datasheet%201.pdf)
は2 Gbit DDR3、128M×16構成を示す。1チップの容量は256 MiBで、2 GBではない。
これは型番の読みが正しい場合の容量であり、チップ個数・実機がLinuxへ割り当てる容量とは別。
SoCのコア名・周波数については、ARMv7まではバイナリで確認済みだが、
MT8553HAATの公式datasheetでの照合は未完了。800MHzなどを確定仕様にしない。

## 2. メーカー公開Linuxソースを取得した

取得元：<https://ospo.panasonic.com/oss/source/bdplayer/AWBPM15A2/linux.tgz>

SHA-256：`021e749f568ff8dda436ffbf41e0dc06aced7b9f0607602abecbff933594d731`

展開後のルートは `linux/`。主要な確認箇所：

| 相対パス | 行の目安 | 発見 |
| --- | ---: | --- |
| drivers/mtd/nand/nand_ids.c | 166 | TC58NVG1S3HTA00、2048-byte page、256 MiB、128-byte OOB、ECC条件 |
| drivers/mtd/nand/mt85xx_nand.c | 88 | 復号関数の登録口 |
| 同上 | 1155、2368、2770 | partition flagsのbit24とenc_sizeを使う読み取り時復号 |
| drivers/tty/serial/mt85xx_serial.c | 62、123、659 | UARTログを抑制するフラグ・条件と送信時チェック |
| 同上 | 2509 | `/proc/driver/uart/log` 作成処理 |
| drivers/tty/serial/Makefile | 87–88 | modern / traditionalの2種類のUART実装を区別 |

ソースのGPIO23によるログ制御は条件コンパイル内にある。
**GPIO23を実機で操作する根拠にはしない。** 対象カーネルのビルド設定と
基板の対応を確認していないためである。
カーネルの`IKCFG_ST`は見つからず、埋め込み.configは今回抽出できなかった。

`/proc/driver/uart/log`は、既にシェルがある場合のログ制御口であり、
USBメモリーにlog_file.txtを置くだけで自動起動する機能ではない。

## 3. NAND復号フラグの意味が一部判明

公開NANDドライバーは、partition flagsの `0x01000000` を暗号化フラグとして使い、
`fwDecrypt(buffer, page_size, cryptunit)`を呼ぶ。復号アルゴリズム本体は登録された外部関数。
したがって、このソースだけでは鍵や方式は確定しない。

付属FRM解析ツールに、PITの `mtd_crypt`、`encrypted_bytes_per_unit`、
`clear_bytes_per_unit` の記録を追加した。
この入力でbit24が立つのは`rootfs_enc_it_1`。enc_size=2048。
通常rootfsは平文のSquashFSで、initrdにはこのPITフラグが立っていない。
**initrdが読めない理由を、NANDドライバーの暗号化と直結させてはいけない。**

新たなチップ情報から、実機を調べる際はまずPITIT table ID 0の256 MiB構成が候補になる。
起動ログまたは実機PITを取得するまでは、更新ファイルの表を実機の確定パーティション表と呼ばない。

## 4. 最も重要な発見：診断CLIにLinuxコマンド実行ハンドラーがある

対象：通常rootfsの`usr/local/bin/bdpprog`。

SHA-256：`eea484e39b9738becc0891415a08e3e28a57c2bb1c99402d1fe2cf1f53fbbdbb`

単なる文字列発見から進めて、24-byte command recordと呼び出し命令を確認した。

| VA | 内容 |
| --- | --- |
| 0x00f79644 | `system` command record。handler=0x0065177c、helpはLinux shell呼び出しを示す |
| 0x00f790d4 | 上記command recordを含む配列の先頭 |
| 0x00f790a4 | `fm`グループ。child pointerが0x00f790d4 |
| 0x0065236c | `fm`テーブルを`x_cli_attach_cmd_tbl`へ渡す登録処理。category引数=3 |
| 0x0065177c | system handler。引数数=2を要求する |
| 0x006517d4 | `ipcd_exec`のPLT entry 0x0003096cを呼ぶ |

ハンドラーはコマンド引数をコピーし、`ipcd_exec(command, 0)`へ渡す。
Usage文字列は`system <cmd>`。`sbin/ipcd`は`system`をimportし、
`usr/local/lib/libipcdso.so`には`ipcd_exec`実装がある。
ただし、実機でipcdが起動しているか・何ユーザー権限か・commandの制約があるかは未確認。

これは**実機で使えるシェルを取得済み**という意味ではない。
CLIの入力経路、起動条件、権限検査、グループprefixの確認が必要。
`system` recordのrightsは0、親`fm`のrightsは2だが、数値の意味はまだ断定しない。

CLIに入れた場合の確認候補は、まず`help`と`fm`グループの列挙。
名前解決が確認できてから`fm.system "uname -a"`等の読み取り専用コマンドを試す。
共通コードの使用例には`mw.fm...`というprefixもあるため、
実際の起点によって`mw.fm.system`になる可能性がある。**いずれも実機未検証。**

## 5. USBシリアルの診断入力経路

`bdpprog`のUSB CLI入力処理を逆アセンブルした結果：

| VA | 確認した動作 |
| --- | --- |
| 0x008f92c8 | グローバルfdを取得し、read関数へ渡す |
| 0x008faf34 | 最初の受信byteを0x53（ASCII S）と比較 |
| 0x008faf50 | 続く6 bytesを受信 |
| 0x008faf68 | 比較対象の`nmk2bp`文字列をロード |
| 0x008faf74 | 上記6 bytesを比較関数へ渡す |
| 0x008faf88 | 一致時にUSB-CLI有効化メッセージをロード |

従って、この分岐に対する**静的解析上の入力候補はASCII `Snmk2bp`**。
コマンド投入以前の有効化処理であり、これだけでLinuxコマンドが通ると判断しない。

追加の根拠：

- `.data`には`/dev/ttyUSB0`、関連コードにはfdのopen/read/termios処理がある。
- `Open USB2USB device`コマンドのhandlerはVA 0x009107e4。
- rootfsに`usbserial.ko`、`ftdi_sio.ko`、`pl2303.ko`がある。
- アプリにはFTDI driverの検出処理と、usbserial/ftdiのロード処理が含まれる。

未確認：USBシリアル接続時の自動open、CLI threadの起動条件、実機でロードされるdriver、
USB側ボーレート、診断モードフラグの必要性。
`/dev/ttyUSB0`文字列だけから、任意アダプターを挿せば自動で使えるとは結論しない。

USBホスト端子を持つ本機とPCを単純なUSB A–Aケーブルで直結する方法ではない。
将来の検証案は、対応するUSB–UARTを本機側のUSBに接続し、
別のUSB–UARTをPC側に接続してTX/RXを交差、GNDを共有する構成。
アダプターの信号電圧を合わせ、VCC同士は結ばない。
本機側でdriver/CLIが起動すれば、基板UARTより少ない加工で使える可能性がある。
これは提案する接続構成であって、実機で動作確認したものではない。

## 6. UART側の実用的な方針

前回のbootloaderにあった`baudrate=115200`、`console=ttyMT0`を引き続き手掛かりにする。
まず適合電圧の受信器で、電源投入直後からのログを受信する。
TX/RX pad位置・電圧はこの解析だけでは特定できない。

公開ソースとカーネルの双方にUARTログ処理がある一方、抑制経路も存在する。
無出力の原因候補には、pad違い・baud違い・pinmux・ログ抑制・boot stageの違いがある。
公開ソース中のGPIO番号を使った短絡や、NAND書き換えには進まない。
今回のbootloader逆アセンブルではESC（0x1b）の反復を数える状態機械も確認したが、
診断フラグや再起動確認に関わるため、単なるLinuxログイン手順とは扱わない。

## 7. initrdの解析状況

`initrd_1` chunk（FRM 0x00b92c90、0x0023ded0 bytes）は引き続き未展開。
今回試した範囲：先頭付近のgzip/cpio/SquashFSシグネチャ探索、
offset 0/4/8/16/32/64からのLZMA展開。いずれも成功しなかった。
先頭は`48 ec 66 65 51 3c e4 6a`。

bootloaderのinitrd読み取り・bootargs構築部分を特定したが、
FRM内chunkの復号／変換経路と結び付けるには、前段loaderも含めた追跡が必要。
追加のkernel_2 chunkも用途未確定。
高エントロピー、16-byte整列、paddingらしい処理は手掛かりで、AES方式を確定する証拠にはしない。

## 8. 署名付きscriptとDoomへの見通し

`bin/secure-script`には`SIGNEDSCRIPT`、`/etc/shpub`、SHA-256、RSA関連実装がある。
したがって「USB上の任意.shをこのコマンドで起動する」案には署名確認が障害になりうる。
呼び出し元・署名の対象範囲・実機での使用条件はまだ未確認。

通常bashのELFはARMv7、Thumb-2、VFPv3-D16の属性を持ち、
loaderは`/lib/ld-linux.so.3`、glibcは2.18。
armhfの配布バイナリがそのまま動くとは限らない。
まず表示を使わない小さなARM EABIプログラムでABIとUSB実行可否を確認するのが順序となる。
Doomの前段にはCLI到達、コマンド実行、ファイル転送、表示・入力デバイスの確認が残る。

## 9. 再現方法

通常rootfsの抽出は[前回の手順](firmware-format-ja.md)を使う。
追加の静的解析ツールは以下で実行でき、対象プログラムは実行しない。

```sh
python3 -m venv work/venv
work/venv/bin/pip install -r tools/requirements-static.txt
work/venv/bin/python tools/inspect_elf.py work/rootfs/usr/local/bin/bdpprog \
  > work/bdpprog-static.json
# command handler（VA指定）
work/venv/bin/python tools/inspect_elf.py work/rootfs/usr/local/bin/bdpprog \
  --start 0x65177c --size 0x84 > work/system-handler.json
# USB handshake
work/venv/bin/python tools/inspect_elf.py work/rootfs/usr/local/bin/bdpprog \
  --start 0x8faf28 --size 0x80 > work/usb-handshake.json
```

出力はファイルのSHA-256、ELF情報、関連文字列の位置、ポインター参照、
CLI recordの親子関係、指定範囲の逆アセンブル。
アドレス・byte列の一致を検証し、別バージョンでは同じVAを流用しない。
Capstoneが命令と解釈しても、指定範囲がコードである保証にはならない。
`--start`のbit0はThumbモード指定に使用する。

[機械可読の追加解析結果](../reports/bdpprog-static.json)も保存した。
FRM本体・抽出ELF・メーカーのLinuxソースはリポジトリに含めない。
