# TRAINING: 教師生成と NNUE 学習

plan の Phase D(M3〜M4)。やねうら王の `gensfen` で教師局面を生成し、`learn` コマンドで
NNUE 評価関数を学習する。本端末では計算資源の制約があるため、段階的に規模を上げる。

## 全体の流れ

```
1. 教師生成   gensfen        →  data/selfplay/<run_id>/gensfen.bin
2. 学習       learn          →  evals/trained/v<version>/nn.bin
3. 動作確認   selfplay_match →  出発点比の勝率測定
4. CHANGELOG  evals/CHANGELOG.md に結果を追記
```

## 1. 教師生成 (gensfen)

GENSFEN ビルドのエンジンが必要(`docs/BUILD.md` の「学習用ビルド」参照)。

```powershell
python scripts/gen_teacher.py --config configs/train/gensfen_v1.yaml
```

設定例:

```yaml
# configs/train/gensfen_v1.yaml
name: selfplay_v1
engine_binary: ../engine/bin/YaneuraOu-GENSFEN.exe
eval_dir: ../evals/baseline/suisho   # 教師の指し手品質はここで決まる
options:
  Threads: 8
  Hash: 4096
gensfen:
  loop: 100000000              # 1億局面(本端末でまずは 1000万〜1億)
  depth: 8                     # 探索深さ。深いほど質高/時間大
  random_move_minply: 1
  random_move_maxply: 24
  random_multi_pv: 4
  output_file_name: ../data/selfplay/selfplay_v1/gensfen.bin
```

> 本端末スループット目安: depth=8, Threads=8 で **数百〜千万局面/時** 程度(やねうら王設定とハードによる)。
> 1億局面なら 10-100 時間オーダー。**最初は 100万〜1000万** 局面で動作確認すること(D2)。

## 2. 学習 (learn)

LEARN ビルドのエンジンが必要。

```powershell
python scripts/train_nnue.py --config configs/train/train_v0.1.yaml
```

設定例:

```yaml
# configs/train/train_v0.1.yaml
name: train_v0.1
engine_binary: ../engine/bin/YaneuraOu-LEARN.exe
seed_eval_dir: ../evals/baseline/suisho   # 出発点(D7 の重要設計)
options:
  Threads: 8
  Hash: 4096
learn:
  targetdir: ../data/selfplay/selfplay_v1
  loop: 1                       # 全教師を何周するか
  batchsize: 1000000            # ミニバッチサイズ(やねうら王の慣例値)
  newbob_decay: 0.5
  eta: 1.0                      # 学習率
  validation_set_file_name: null # 任意の検証セット
  output_dir: ../evals/trained/v0.1
  save_every: 50000000          # この局面数ごとにスナップショット
```

> ハイパラの指針:
> - 出発点が強い場合(水匠等)、`eta` を小さめ(0.5-1.0)から始め、過学習防止
> - 短時間で試すなら `loop=1`, `batchsize=10000` でも動く(品質は下がる)
> - 評価関数アーキテクチャ(`EVAL_TYPE`)はビルド時に固定。途中変更不可

## 3. 動作確認・自己対戦

学習出力 `evals/trained/v0.1/nn.bin` を `EvalDir` に指定して対戦シナリオを回す:

```yaml
# configs/match/v01_vs_suisho.yaml
name: v0.1_vs_suisho
games: 200
engines:
  a:
    binary: ../engine/bin/YaneuraOu-NORMAL.exe
    options: { Threads: 4, Hash: 1024, EvalDir: ../evals/trained/v0.1 }
  b:
    binary: ../engine/bin/YaneuraOu-NORMAL.exe
    options: { Threads: 4, Hash: 1024, EvalDir: ../evals/baseline/suisho }
time_control: { byoyomi_ms: 1000 }
swap_colors: true
output_dir: ../results/matches/v01_vs_suisho
```

```powershell
python scripts/selfplay_match.py --config configs/match/v01_vs_suisho.yaml
python scripts/match_summary.py --dir results/matches/v01_vs_suisho/<timestamp>
```

## 4. CHANGELOG への記録

学習成功(または失敗)を `evals/CHANGELOG.md` に追記。スクリプト `match_summary.py` の出力をコピーして転記する。

## 5. 段階的にスケールを上げる(M4 への道)

M3 完了(1 サイクル動く)後、以下の順で規模を上げる:

| バージョン | 教師量 | エポック | 推定所要 | 期待 |
|---|---|---|---|---|
| v0.1 | 100万局面 | 1 | 数十分 | サイクル動作確認(M3) |
| v0.2 | 1000万 | 1 | 数時間 | わずかな差(誤差レベル) |
| v0.3 | 1億 | 1 | 1-3 日 | 統計有意な差が出るかの分水嶺 |
| v0.4+ | 1億+ | 2-3 | 数日〜週 | 本気の試行(本端末上限近傍) |

> R8(リスク): 本端末では v0.4 でも出発点に届かない可能性が高い。届かなければ
> Phase G(クラウド試行)で再挑戦するのが計画上の想定動作(D14 参照)。

## 6. 再現性の担保

- 教師生成のランダムシード(`gensfen` の `random_file_name` 等のオプション)
- 学習のシード(`learn` 側で指定可能なら設定)
- ハイパラ・コマンド行を `configs/train/<name>.yaml` に固定し commit
- 出力評価関数のハッシュ(`Get-FileHash` 等)を `evals/CHANGELOG.md` に記録

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| 教師生成が遅すぎる | `depth` を 6 に下げる、Threads を増やす(本端末上限 8 物理コア)、loop を分割 |
| 学習中に発散(loss が増える) | `eta` を半分に、`newbob_decay` を 0.7 に |
| 学習結果が出発点を下回る | 教師量不足が最有力。次に学習レシピ。出発点との kpp/kpe 差を疑う場合はアーキテクチャ整合を確認 |
| 出力評価関数が読み込めない | `EVAL_TYPE` のビルド指定と整合しているか確認 |
