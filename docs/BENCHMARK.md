# BENCHMARK: 自己対戦・棋力測定

`scripts/selfplay_match.py` と `scripts/match_summary.py` を使った棋力測定の手順。
plan の Phase C(M2)以降、ほぼ全フェーズで使う基盤ツール。

## 1. 対戦シナリオを定義

`configs/match/<scenario>.yaml` に対戦設定を書く。例:

```yaml
# configs/match/baseline.yaml
name: baseline_yane_vs_suisho
output_dir: ../results/matches/baseline
games: 200
parallel: 2          # 同時実行の対局数(本端末 8C/16T、エンジンが Threads=4 なら parallel=2 で 8 スレッド占有)
swap_colors: true    # 先後を1局ごとに入れ替え
seed: 42

time_control:
  byoyomi_ms: 1000   # 1手1秒
  # main_time_ms: 60000
  # inc_ms: 1000
  # max_moves: 256

engines:
  a:
    name: yane_standard
    binary: ../engine/bin/YaneuraOu-NORMAL.exe
    options:
      Threads: 4
      Hash: 1024
      EvalDir: ../evals/baseline/standard

  b:
    name: yane_suisho
    binary: ../engine/bin/YaneuraOu-NORMAL.exe
    options:
      Threads: 4
      Hash: 1024
      EvalDir: ../evals/baseline/suisho

opening:
  # 任意。指定しなければ初期局面から
  type: book   # or "sfen_list"
  book_path: ../evals/book/opening.csa
  random_choice: true
```

## 2. 対戦実行

```powershell
cd 03_develop
python scripts/selfplay_match.py --config configs/match/baseline.yaml
```

主な動作:

- `engines.a` と `engines.b` の USIエンジンを起動し、設定 (`setoption`) を反映
- `swap_colors=true` なら 1 局ごとに先後を入れ替え、`parallel` 並列で N 局実行
- 各対局の進行・指し手・評価値を記録
- 結果を `results/matches/<name>/<timestamp>/` に JSON + CSA 形式で出力

中断した場合は再実行で続きから(同じ `output_dir` 内の既存 JSON を読み、未消化局のみ走らせる)。

## 3. 結果集計

```powershell
python scripts/match_summary.py --dir results/matches/baseline/<timestamp>
```

出力例:

```
=== baseline_yane_vs_suisho ===
Games:    200 (a=99 wins, b=101 wins, draws=0, illegal/timeout=0)
Win rate (a): 49.50%  ±  6.93% (95% CI)
ΔElo (a−b):    -3.5   ±  48.2  (95% CI)
P(a is stronger): 0.443
Statistically significant: NO (CI crosses 50%)
```

判定: `Statistically significant: YES` で勝率 > 50% なら「変更が棋力向上に寄与」と扱う。

## 4. 試合数の目安

| 試合数 N | 95% CI(勝率)の幅 | 推定 ΔElo の幅 | 用途 |
|---|---|---|---|
| 100 | ±10% | ±70 Elo | 大まかなスモークテスト |
| 200 | ±7% | ±50 Elo | 通常の評価 |
| 500 | ±4% | ±30 Elo | 細かい比較(ハイパラ調整 等) |
| 1000+ | ±3% | ±20 Elo | 重要な意思決定(フェーズ移行 等) |

> 実装メモ: `match_summary.py` は内部で正規近似(p̂ ± 1.96 √(p̂(1−p̂)/N))と Elo 換算 (-400·log10((1/p̂)−1)) を使う簡易実装。500 局以下では幅が大きく出るが、判定としては実用に足る。

## 5. 並列度・時間配分の調整

本端末(8コア/16論理):

- 1エンジン Threads=4 → 2並列 = 8スレッド占有(余裕あり)
- 1エンジン Threads=8 → 2並列 = 16スレッド競合(対局時間と勝率に影響、要避け)
- 短い時間制(1手0.5秒)で並列を上げると測定ノイズが増えるので、判定したい局数と所要時間のトレードオフで調整

参考所要時間(本端末、Threads=4 × 2並列 × 1手1秒):

- 200局 ≒ 200 × 2 × 100手 × 1秒 ÷ 並列度 = ざっくり **2-4時間**(局の長さに依存)

## 6. 結果ディレクトリのサイズ管理

`results/matches/` は `.gitignore` 対象。サイズが膨らんだら古いシナリオを削除 or 圧縮。
重要な結果(M2/M4/M6/M7 のマイルストーン判定に使ったもの)は `evals/CHANGELOG.md` にサマリを残す。

## 7. レーティング推定の限界

- 自己対戦の Elo は **相対値** であり、floodgate のような外部レーティングとは絶対値が異なる
- 同じ評価関数でも別エンジン(将棋GUI / 別バージョン)と対戦すれば数値は変わる
- floodgate レーティング(M5以降)が出るまでは「相対比較ツール」と割り切る
