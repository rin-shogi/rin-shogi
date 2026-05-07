# 琳 (Rin) — a shogi engine

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE)

NNUE系・やねうら王ベースの将棋AI **琳(Rin)** の開発リポジトリ。

- **当面の中間ゴール**: floodgate での運用と R3300 帯到達
- **長期目標**: WCSC(世界コンピュータ将棋選手権)・電竜戦への大会出場

USI `id name`: `Rin NNUE 9.30git 64AVX2`(やねうら王の評価関数タイプ・アーキ表記が自動付与される)

## 概要

このプロジェクトは **車輪の再発明をしない**:

- エンジン本体には実績ある OSS の [**やねうら王**](https://github.com/yaneurao/YaneuraOu) を git submodule として取り込んでビルド
- 評価関数は当面 [**水匠5**](https://github.com/yaneurao/YaneuraOu/releases/tag/suisho5)(たややん氏配布、Apache 2.0)を出発点
- 独自開発するのは **(1) 定跡 / (2) 探索パラメータチューニング / (3) NNUE 評価関数の独自学習** — 計算資源依存度が低い順に注力

詳細な設計判断は [`docs/`](docs/) 配下、特に [`docs/ITERATION.md`](docs/ITERATION.md) を参照。

## ディレクトリ構成

```
.
├── README.md, LICENSE, NOTICE
├── requirements.txt, .gitignore
├── engine/                   git submodule: yaneurao/YaneuraOu
├── evals/                    評価関数・定跡(バイナリは .gitignore 対象)
│   ├── baseline/             公開評価関数(取得スクリプト経由)
│   ├── trained/              自前学習モデル(Rin-v0.1, Rin-v0.2, ...)
│   ├── book/                 定跡 DB
│   └── CHANGELOG.md
├── data/                     学習データ(.gitignore 対象、ローカル)
├── scripts/                  Python オーケストレーション
├── configs/                  設定 YAML(コードではなくデータ駆動)
├── results/                  自己対戦・学習結果(.gitignore 対象)
└── docs/                     開発手順書
    ├── BUILD.md              MSYS2 + clang ビルド手順
    ├── EVAL_BASELINES.md     公開評価関数の調査
    ├── BENCHMARK.md          自己対戦・棋力測定
    ├── TRAINING.md           教師生成・NNUE学習
    ├── FLOODGATE.md          floodgate 運用
    ├── ITERATION.md          棋力向上イテレーション
    └── HARDWARE.md           ハードウェア戦略・クラウド構成
```

## クイックスタート

### 必要環境

- **Windows 10/11**(Linux 対応は将来)
- **MSYS2**(<https://www.msys2.org/>)
- **Python 3.10 以上**
- **CPU**: AVX2 対応(2014 年以降の Intel/AMD はほぼ対応)

### 1. 環境構築

```powershell
# 1. このリポジトリを clone
git clone --recurse-submodules https://github.com/rin-shogi/rin-shogi.git
cd rin-shogi

# 2. MSYS2 で必要なパッケージを入れる
#    (詳細は docs/BUILD.md)
#    pacman -S mingw-w64-x86_64-clang mingw-w64-x86_64-lld \
#              mingw-w64-x86_64-make mingw-w64-x86_64-python p7zip

# 3. やねうら王をビルド
#    MSYS2 MINGW64 シェルから:
#    cd engine/source && mingw32-make -j8 normal
#    バイナリを engine/bin/ に配置
```

詳細手順は [`docs/BUILD.md`](docs/BUILD.md) 参照。

### 2. 評価関数の取得

```powershell
# 水匠5 を取得(やねうら王 GitHub Releases から)
cd evals/baseline/suisho5
.\fetch.ps1
```

取得後、`engine/bin/eval/nn.bin` にコピー(または `EvalDir` で指定)。
詳細は [`evals/baseline/suisho5/README.md`](evals/baseline/suisho5/README.md) と
[`docs/EVAL_BASELINES.md`](docs/EVAL_BASELINES.md) 参照。

### 3. 動作確認(GUI 対局)

将棋所 (<http://shogidokoro.starfree.jp/>) または ShogiGUI に
USIエンジンとして登録し、`FV_SCALE = 24` を設定して対局開始。

### 4. 自己対戦・学習・floodgate 運用

各々 [`docs/BENCHMARK.md`](docs/BENCHMARK.md) /
[`docs/TRAINING.md`](docs/TRAINING.md) /
[`docs/FLOODGATE.md`](docs/FLOODGATE.md) 参照。

## ライセンス

- **本リポジトリ**: GPL-3.0(やねうら王の派生物として継承、[`LICENSE`](LICENSE))
- **同梱コード(scripts / docs / configs)**: GPL-3.0
- **`evals/baseline/suisho5/nn.bin`(取得後)**: Apache 2.0(本リポジトリは再配布せず取得スクリプトのみ提供)
- 詳細は [`NOTICE`](NOTICE) 参照。

## 関連プロジェクト

- [やねうら王 (YaneuraOu)](https://github.com/yaneurao/YaneuraOu) — 本プロジェクトのベース
- [水匠5 (Suisho5)](https://github.com/yaneurao/YaneuraOu/releases/tag/suisho5) — 出発点となる評価関数
- [floodgate](http://wdoor.c.u-tokyo.ac.jp/shogi/) — コンピュータ将棋の自動対局場
