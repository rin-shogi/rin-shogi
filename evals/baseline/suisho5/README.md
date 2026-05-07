# Suisho5 (水匠5) — baseline 評価関数

本プロジェクト 琳(Rin) の **出発点となる公開評価関数**。
本リポジトリには `nn.bin` 本体は同梱せず、`fetch.ps1` で公式配布元から取得する方式を採用(再配布の冗長性を避けるため)。

## メタ情報

| 項目 | 値 |
|---|---|
| 名称 | Suisho5(水匠5) |
| 配布者 | たややん氏(<https://x.com/tayayan_ts>) |
| 公式配布元 | <https://github.com/yaneurao/YaneuraOu/releases/tag/suisho5> |
| 配布アーカイブ | `Suisho5.7z`(約 24 MB) |
| 展開後 | `nn.bin`(64,217,066 bytes、SHA-256: `768068f0d534a0603a5d38bcd143de6bbca820d5f1c95a14d40863e5b7892d76`) |
| 評価関数アーキテクチャ | NNUE_halfKP256(やねうら王 `YANEURAOU_ENGINE_NNUE` ビルドと一致) |
| **`FV_SCALE` 最適値** | **24**(やねうら王のデフォルト 16 から要変更) |
| ライセンス | Apache License, Version 2.0 |
| 強さ目安 | floodgate R3500+ 帯(2026 年時点でも上位エンジン群と互角〜) |

## 取得方法

### Windows (PowerShell)

```powershell
.\fetch.ps1
```

`Suisho5.7z` をダウンロードして `nn.bin` を展開する。p7zip が必要(MSYS2 経由で `pacman -S p7zip`)。

### 手動

1. <https://github.com/yaneurao/YaneuraOu/releases/tag/suisho5> から `Suisho5.7z` をダウンロード
2. このディレクトリに置いて 7-Zip で展開
3. `nn.bin` がこのディレクトリに出る

## エンジンへの配置

やねうら王 (`engine/bin/YaneuraOu-NORMAL.exe`) は同階層の `eval/nn.bin` を読み込む。

```powershell
# このディレクトリの nn.bin を engine/bin/eval/ にコピー
mkdir -Force ../../engine/bin/eval
cp nn.bin ../../engine/bin/eval/nn.bin
```

または USIオプション `EvalDir` でこのディレクトリを直接指定する方法でも可:

```
setoption name EvalDir value /path/to/evals/baseline/suisho5
setoption name FV_SCALE value 24
isready
```

## ライセンス

Suisho5 は **Apache License, Version 2.0** で配布されている。
本リポジトリは派生物として `nn.bin` を再配布せず、取得スクリプトのみを置く方針で運用する(必要なら個別に Apache 2.0 のライセンス文を併載)。

詳細は本プロジェクトの [`NOTICE`](../../../NOTICE) を参照。
