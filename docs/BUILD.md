# BUILD: やねうら王のビルド手順

本端末(Windows 11 / Ryzen 7 7735HS, AVX2/BMI2 対応)で
やねうら王を NNUE評価関数対応の AVX2/BMI2 バイナリとしてビルドする手順。

## 1. MSYS2 セットアップ

[MSYS2 公式](https://www.msys2.org/) からインストーラを取得して実行。

インストール後、MSYS2 MINGW64 シェルを起動し以下を実行:

```bash
pacman -Syu                                    # システム更新(初回は再起動)
pacman -S mingw-w64-x86_64-clang               # clang
pacman -S mingw-w64-x86_64-gcc                 # g++ (フォールバック用)
pacman -S mingw-w64-x86_64-make
pacman -S git
pacman -S mingw-w64-x86_64-openblas            # OpenBLAS(任意・学習高速化)
```

> 注: 以後のビルドコマンドは **MSYS2 MINGW64 シェル** で実行。Windows の cmd / PowerShell ではなく、`/mingw64/bin/` が PATH に通った環境であること。

## 2. やねうら王ソースの取得

本リポジトリでは git submodule として取り込み済み。
クローン直後は submodule の中身が空なので初期化が必要:

```powershell
# プロジェクトルートで一度だけ
git submodule update --init --recursive
```

`03_develop/engine/` にやねうら王ソースが展開される。

## 3. ビルド

MSYS2 MINGW64 シェルから:

```bash
cd /c/workspace/morishita-dev-ai/ticket-001-shogi-ai/03_develop/engine/source
make -j8 clang TARGET_CPU=AVX2 EVAL_TYPE=halfkp_256x2-32-32 ENGINE_TARGET=NORMAL_ENGINE COMPILER=clang++
```

主なオプション:

| 変数 | 推奨値 | 説明 |
|---|---|---|
| `TARGET_CPU` | `AVX2`(本端末は `BMI2` も可) | CPU 命令セット。Ryzen 7 7735HS は AVX2/BMI2 対応 |
| `EVAL_TYPE` | `halfkp_256x2-32-32` | NNUE 評価関数アーキテクチャ。水匠等の公開評価関数と互換 |
| `ENGINE_TARGET` | `NORMAL_ENGINE` | 通常の対局用。学習用は `LEARN_ENGINE`、教師生成は `GENSFEN_ENGINE` |
| `COMPILER` | `clang++` | 推奨。`g++` でも可 |

ビルド成果物は `engine/source/YaneuraOu-by-clang.exe` 等として生成される。
慣例に合わせ、生成バイナリを `engine/bin/` にコピー(本リポジトリでは `.gitignore` 対象):

```bash
mkdir -p ../bin
cp YaneuraOu-by-clang.exe ../bin/YaneuraOu-NORMAL.exe
```

## 4. 学習用ビルド・教師生成用ビルド(必要時)

```bash
make clean
make -j8 clang TARGET_CPU=AVX2 EVAL_TYPE=halfkp_256x2-32-32 ENGINE_TARGET=LEARN_ENGINE COMPILER=clang++
cp YaneuraOu-by-clang.exe ../bin/YaneuraOu-LEARN.exe

make clean
make -j8 clang TARGET_CPU=AVX2 EVAL_TYPE=halfkp_256x2-32-32 ENGINE_TARGET=GENSFEN_ENGINE COMPILER=clang++
cp YaneuraOu-by-clang.exe ../bin/YaneuraOu-GENSFEN.exe
```

> Tip: 普段の対局には `NORMAL_ENGINE` のみで十分。学習・教師生成は別チケット段階(D, F)で必要になってからビルドする。

## 5. 動作確認

コマンドラインで USI モードを試す:

```bash
echo -e "usi\nisready\nposition startpos\ngo movetime 3000\nquit" | ./../bin/YaneuraOu-NORMAL.exe
```

`bestmove ...` が返れば成功(評価関数を読み込めない場合はエラーが出る — 評価関数の配置は [`EVAL_BASELINES.md`](EVAL_BASELINES.md) 参照)。

## 6. ビルドオプションの記録

実際に採用したオプションは [`../configs/build/`](../configs/build/) 配下に YAML で記録する(`run_id` ごと):

```yaml
# configs/build/normal_avx2_v1.yaml
target_cpu: AVX2
eval_type: halfkp_256x2-32-32
engine_target: NORMAL_ENGINE
compiler: clang++
flags: ["-march=znver3"]   # 任意の追加フラグ
binary_path: ../engine/bin/YaneuraOu-NORMAL.exe
upstream_commit: dc943f897baf6dcd77c2a22170e2b19e2e37c1d0
built_at: 2026-05-XX
notes: "本端末初回ビルド"
```

## トラブルシューティング

| 症状 | 原因/対処 |
|---|---|
| `clang: command not found` | MSYS2 MINGW64 シェルでない。`pacman` で `mingw-w64-x86_64-clang` を導入 |
| ビルド中に `__BMI2__` 関連エラー | `TARGET_CPU=AVX2` に下げて再試行。本端末は BMI2 対応のはずだが、ビルド環境による |
| `cannot find -lz` 等 | `pacman -S mingw-w64-x86_64-zlib` などで該当ライブラリを追加 |
| 起動時 `evaluate file open error` | 評価関数 (.bin) が `eval/` フォルダ または `EvalDir` に置かれていない |
| Windows Defender が exe を隔離 | 例外設定を追加 |
