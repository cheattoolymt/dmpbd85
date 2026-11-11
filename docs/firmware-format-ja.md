# 日本版DMP-BD85：ファームウェア形式とLinuxアクセスへの足掛かり

調査日：2026-11-11。対象は日本で2015年発売のDMP-BD85。
海外の同名DMP-BD85（2010年世代）と区別する。
以下のオフセットは、特記しない限りZIP展開後の `PANA_DVD.FRM` 先頭からの値。

## 1. 製品と公式資料

[日本版の公式仕様](https://panasonic.jp/bdplayer/products/DMP-BD85/spec.html)によれば、
HDMI出力1系統、USB1系統で、LAN・無線LAN・SDスロットはない。
電源はDC12V、消費電力6W、寸法245×38.5×175mm、質量0.8kg。
BD/DVD/CDおよび複数の動画・音声形式を再生する。
ネットワーク越しのSSH/Telnetを最初の入口とする根拠はない。

[公式更新ページ](https://av.jpn.support.panasonic.com/support/bd/download/pfw/plr/bd85.html)の
現行HTMLをcurlで取得すると、2026-09-29公開の1.81、
`UPDATE_BD85_8.zip`、76,526,986バイトが掲載されている。
更新内容はディスク再生の安定性改善と社名変更。
検索・Web閲覧ツールのキャッシュには旧1.78／`_7.zip`が返ったため、現行HTMLと区別した。
ZIP内部のファイル日時は2026-05-22であり、Web公開日や実機の導入済み版とは異なる。

[製品サポート・説明書](https://av.jpn.support.panasonic.com/support/bd/product/dmp_bd85.html)、
[公式更新案内](https://av.jpn.support.panasonic.com/support/bd/download/pfw/)も参照。
USBメモリーによる公式更新の存在は、任意プログラムをUSBから実行できることを意味しない。

## 2. 入力の同定

取得元：<https://fdl.jpn.support.panasonic.com/pc/jp/bd/bd85/UPDATE_BD85_8.zip>

| ファイル | バイト数 | SHA-256 |
| --- | ---: | --- |
| UPDATE_BD85_8.zip | 76526986 | `5aedd29e19a577ae99bb8117d1a6a7935a44fb2742856ba629d294124c75ad1c` |
| PANA_DVD.FRM | 78022484 | `70e4d546c81608af4590d56c4ea4877859ee41c8fb48384a004891eff3ef9bc6` |

ZIPには `PANA_DVD.FRM` が1個だけ入っている。
`file` はこれをOpenPGP Secret Keyと表示したが、実体の形式識別として採用できない。
後述のテーブル整合性・CRC・実際の展開成功を判断根拠とした。
高エントロピーであることだけから全体が暗号化されているとも判断しない。

## 3. 外側はMediaTek BDPのPITIT/PIT/BIT更新コンテナー

[unixtractのMediaTek BDP実装](https://github.com/theubusu/unixtract/tree/aadba866ea47ed9506ffe130a8558bb9147ee968/src/formats/mtk_bdp)
の構造を手掛かりに、実データの境界と全エントリーを検証した。
一般のPanasonic FRM復号器が扱う形式と、拡張子だけで同一視しない。

- `PITIT` は `0x04a68140`。先頭8バイトはASCII `iTIPiTIP`。
- +8のlittle-endian u32が1、+12が0。その後に32バイトの構成エントリーが続く。
- 構成エントリーはu32×8：NAND容量、PIT位置、PIT長、table ID、BIT位置、BIT長、予約×2。
- 終端はlittle-endian値 `0x69544950`（ファイル上は `PITi`）。

| table ID | NAND容量（テーブル上の値） | PIT | BIT | PIT件数 | BIT件数 |
| ---: | ---: | --- | --- | ---: | ---: |
| 0 | 256 MiB | 0x04a64140 | 0x04a57140 | 23 | 25 |
| 1 | 512 MiB | 0x04a65140 | 0x04a5b140 | 23 | 25 |
| 2 | 1 GiB | 0x04a66140 | 0x04a5f140 | 25 | 25 |
| 3 | 2 GiB | 0x04a67140 | 0x04a63140 | 25 | 25 |

これらは更新ファイルが持つ複数構成であり、日本版実機のNAND容量の確定値ではない。

PITは8バイトの `dc ea 30 85`×2で始まる。+8からversion、header長、entry長、entry数のu32。
この入力ではversion=1、header長=64、entry長=64。
各entryは名前16バイト、ID、flags、NAND上offset、NAND上sizeのu32、残り予約領域。

BITは `cd ab 30 85`×5で始まり、20バイトentryが続く。
各entryはID、FRM内offset、size、対象partition内offset、flagsのu32。
終端IDは `0x8530efef`。IDでPITと結び付ける。
**FRM内offsetとNAND上offsetは別物。** 同じpartitionへ複数chunkが書かれ、
同じデータが別partitionへ複製される場合もある。
付属ツールは各chunkを独立保存し、書き込み用イメージは生成しない。

主な格納物：

| 対象partition | FRM offset | size | 内容・確認状況 |
| --- | --- | --- | --- |
| boot_1 | 複数chunk | JSON参照 | U-Bootの文字列・環境・コードを含む |
| fe_bin_1 / fe_bin_2 | 0x000827b0 | 0x00100000 | フロントエンド用と推定、未解析 |
| kernel_1 / kernel_2 | 0x001827b0 | 0x00231360 | CRC検証済みuImage |
| kernel_2（追加chunk） | 0x003b3b10 | 0x007df180 | 用途・符号化未確定 |
| initrd_1 | 0x00b92c90 | 0x0023ded0 | 既知gzip／cpioヘッダーなし、未展開 |
| rootfs_normal_1 | 0x00dd0b60 | 0x03c48000 | gzip SquashFS 4.0 |
| rootfs_enc_it_1 | 0x04a18b60 | 0x00020000 | 名前は暗号化関連を示唆、意味未確定 |

末尾には `RSAX` / `XASR` の反復と `rsa_check: 1` のメタデータがある。
署名・検証関連の可能性はあるが、署名対象範囲・鍵・検証分岐は確認していない。
単純再パックやCRC修正だけで実機が受理すると判断しない。

## 4. カーネル：Linuxを実データで確認

`0x001827b0` から64バイトのlegacy U-Boot uImageヘッダー。
magic=`0x27051956`、OS=5（Linux）、arch=2（ARM）、type=2（kernel）、compression=0。
load/entryは共に `0x04000000`、payload長は2,298,656バイト。
ヘッダーCRC32=`0xdea6d905`、payload CRC32=`0x6044c126`。両方一致。

compression=0でも内側はARMの自己展開zImageである。
payload+36のlittle-endian magicは `0x016f2818`。
FRMの `0x00186e04` にあるgzip streamを展開すると4,541,216バイトのカーネルが得られる。
バナーはLinux 3.10.26、ARMv7、Linaro GCC 4.8.2、
ビルド日時は2026-05-07 18:04:27 CSTを示した。完全なバナーはJSONに記録。

## 5. rootfs：通常領域の抽出成功

SquashFS開始は `0x00dd0b60`。superblockのbytes_usedは63,207,324バイトで、
BITの格納サイズ63,209,472バイトには末尾パディングがある。
version=4.0、compression=1（gzip）、block size=131072、inode数=2075。
標準unsquashfs 4.6.1でエラーなく展開し、1843ファイル・158ディレクトリー・74symlinkを得た。

確認できたもの：

- `/bin/bash` と `/bin/sh -> bash`。bashはARM little-endian EABI5、動的リンク、interpreter=`/lib/ld-linux.so.3`。
- `/sbin/init`、`/sbin/agetty`、BusyBox、各種基本コマンド。
- `/usr/local/bin/cliprog`。文字列から `/dev/drvcli` をioctlで使うツールと分かるが、Linuxシェルとは別。
- `bin/secure-script`、DirectFB関連ファイルなど。存在だけでは実行条件を判断できない。
- 抽出した通常rootfs直下に `/etc` はない。initrd側または実行時生成領域の調査が必要。

ネットワークサービス向けファイルも含むが、共通ファームに含まれることと日本版ハードの機能は区別する。
ファーム内プログラムはホストで実行していない。

## 6. 再現手順

Python 3.10以降と、gzip対応の `unsquashfs` があればよい。
新規作業ディレクトリーで実行する。

```sh
mkdir -p work
curl --fail --location --output work/UPDATE_BD85_8.zip \
  https://fdl.jpn.support.panasonic.com/pc/jp/bd/bd85/UPDATE_BD85_8.zip
sha256sum work/UPDATE_BD85_8.zip
unzip -n work/UPDATE_BD85_8.zip -d work/input
sha256sum work/input/PANA_DVD.FRM
python3 tools/analyze_frm.py work/input/PANA_DVD.FRM \
  --out work/extracted > work/analysis.json
unsquashfs -s work/extracted/rootfs-00dd0b60.squashfs
unsquashfs -no-progress -no-xattrs -d work/rootfs \
  work/extracted/rootfs-00dd0b60.squashfs
file work/rootfs/bin/bash
```

`--out` は新しいディレクトリーを指定する。既存出力の上書きは拒否する。
各BIT chunk、CRC検証済みuImage、展開カーネル、SquashFSを出力する。
JSON内のoffset/sizeは10進数。全4構成のPIT/BITと各chunkのSHA-256を含む。
入力は変更しない。未対応のPITIT版や範囲外参照は失敗する。

今回は標準ツール未導入だったため、外部ディレクトリーで公式安定版をビルドした：

```sh
git clone --branch 4.6.1 --depth 1 https://github.com/plougher/squashfs-tools.git work/squashfs-tools
make -C work/squashfs-tools/squashfs-tools unsquashfs \
  XZ_SUPPORT=0 LZO_SUPPORT=0 LZ4_SUPPORT=0 ZSTD_SUPPORT=0 -j2
# 上記のunsquashfsコマンドを work/squashfs-tools/squashfs-tools/unsquashfs で置き換える
```

ビルドにはCコンパイラー、make、zlib/pthreadの開発環境が必要。
使用commitは `d8cb82d9840330f9344ec37b992595b5d7b44184`。
開発最新版ではビルドに失敗したため、安定版4.6.1で検証した。

## 7. Linuxへの入口：次の調査順序

**実機アクセスは未確認。現時点で「USBを挿すだけでシェルが取れる」方法は得られていない。**

1. **initrdと起動処理の解明。** `initrd_1` とkernel_2追加chunkの符号化を調べ、
   `/etc/inittab`、rcスクリプト、USB mount処理、ログイン／診断分岐を探す。
   シェルは通常rootfsに既に存在するため、起動経路の特定が重要。
2. **UARTを優先候補にする。** U-Boot環境に `baudrate=115200`、
   `console=ttyMT0 kgdboc=ttyMT0`、`bootdelay=0`、prompt=`mt8553_base #` がある。
   これらは静的な手掛かりで、実機のピン配置・電圧・出力有無・入力受付は未確認。
   基板でGNDと信号電圧を確認し、まず受信だけで起動ログを取る。
   電源ピンを接続せず、RS-232電圧を直結しない。115200 8N1は試験候補であり確定仕様ではない。
3. **USB診断フラグの呼び出し元を追う。** bootloaderの `0x0006ad62` 付近に
   `Enable D_USB_CLI_FLAG?`、`0x0006ebd4` 付近にアップグレード後のフラグ処理がある。
   USB autorunやLinuxシェルの存在を直接証明するものではない。
   更新コマンドの実行より先に、逆アセンブルと公開ソースで条件を読む。
4. **シェル取得後にDoomの要件を調べる。** CPU/ABI、使用可能RAM、
   `/dev/fb*`・DirectFBの表示経路、入力デバイス、USB上の実行権限を確認する。
   `/lib/ld-linux.so.3` に合わせたABIが必要で、一般的なarmhfバイナリをそのまま使えるとは限らない。

メタデータにはmt8553、dram256、nand128、rsa_check、dis_as_cliなどがある。
共通ビルドの設定文字列なので、SoC刻印・RAM/NAND実容量・CLI有効性の断定には使わない。

## 8. 公開ソースとライセンス

公式更新ページのOSSリンクは次の現行公開先へ移動していた：

- [対象モデル一覧](https://docs.connect.panasonic.com/oss/bdplayer/)
- [AWBPM15Aの公開一覧](https://docs.connect.panasonic.com/oss/bdplayer/AWBPM15A.html)
- [Linuxソース](https://ospo.panasonic.com/oss/source/bdplayer/AWBPM15A2/linux.tgz)
- [SquashFSソース](https://ospo.panasonic.com/oss/source/bdplayer/AWBPM15A2/squashfs.tgz)

一覧にはbash、DirectFB、glibc、sysvinitなどもある。今回は一覧とリンクを確認した段階で、
これらのソース一式のダウンロード・1.81との対応差分確認までは行っていない。

付属PythonツールはunixtractのPIT/BIT実装を参考に移植したためGPL-3.0-onlyとして配布し、
[出典と変更内容](../tools/NOTICE.md)・[ライセンス全文](../tools/COPYING)を同梱。
SquashFS toolsは外部の無改造ツールとして使用した。
メーカーのFRM・抽出物はGitHubに含めず、取得URL・ハッシュ・再現方法を公開する。
