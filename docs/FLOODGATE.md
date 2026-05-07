# FLOODGATE: shogi-server (floodgate) 参加手順

floodgate は東京大学が運用する将棋エンジンの自動対局場(CSA プロトコルベース)。
本プロジェクトでは `Rin-suisho5-v1` 等のハンドルで継続参加し、レーティング推移を
追跡する。本ticket(ticket-002)で接続クライアントを実装した。

公式: <http://wdoor.c.u-tokyo.ac.jp/shogi/>

## 1. 事前準備

### 1.1 ハンドル名とパスワードを決める

floodgate(shogi-server)は **Web フォームによる事前登録は不要**。
プロトコル仕様で「初回接続したハンドル名 + パスワード」がそのまま予約され、
以降は同じパスワードでないと同名でログインできない(first-come 自己登録方式)。

- 本プロジェクトのハンドル: **`Rin-suisho5-v1`**
- 命名規則: `Rin-<eval-version>-v<engine-version>`(評価関数を差し替えたら別ハンドル、例: `Rin-myeval01-v1`)
- パスワード: 任意の文字列を自分で決める。第三者に推測されにくいものを推奨(他者が同名で先に接続するのを防ぐ)
- 決めた値は次節 1.3 で `.env` に書く

### 1.2 エンジン・評価関数の準備

ticket-001 の手順に従い、以下を整える:

- やねうら王ビルド済み: `engine/bin/YaneuraOu-NORMAL.exe`(参照: `docs/BUILD.md`)
- suisho5 評価関数取得済み: `evals/baseline/suisho5/nn.bin`(参照: `evals/baseline/suisho5/fetch.ps1`)

### 1.3 シークレット設定

リポジトリ root で:

```powershell
copy .env.example .env
notepad .env  # FLOODGATE_PASSWORD に 1.1 で決めたパスワードを設定
```

`.env` は `.gitignore` 済み。コミット禁止。

### 1.4 Python 依存関係

```powershell
pip install -r requirements.txt
```

## 2. 接続方式: 自前 Python 実装

floodgate は CSA プロトコル(テキストベース TCP)、やねうら王は USI プロトコル。
両者の橋渡しを Python で自前実装している(`scripts/floodgate_client.py`)。

選定理由:
- 認証情報を扱うクリティカルパスを完全に読める状態にしておきたい(本プロジェクトは隠し玉なしの全公開方針)
- `cshogi` ライブラリで CSA/USI 指し手相互変換・局面追跡が高速・堅牢に行える
- 学習・自己対戦スクリプトと同じ Python 基盤で統一できる

実装ファイル:

```
scripts/
├── floodgate_client.py            エントリポイント(対局メインループ)
└── utils/
    ├── csa.py                     CSA プロトコル TCP クライアント
    ├── csa_usi.py                 CSA <-> USI 指し手変換
    ├── usi.py                     USI エンジン subprocess ラッパ(ticket-001)
    └── config.py                  YAML ローダー + $env: 展開(ticket-001)
```

## 3. 設定ファイル

`configs/match/floodgate_v1.yaml`(`Rin-suisho5-v1` 用、コミット済み):

```yaml
name: Rin-suisho5-v1
mode: floodgate

server:
  host: wdoor.c.u-tokyo.ac.jp
  port: 4081

account:
  username: Rin-suisho5-v1
  password: $env:FLOODGATE_PASSWORD   # .env から自動展開

engine:
  binary: ../engine/bin/YaneuraOu-NORMAL.exe
  options:
    Threads: 8
    USI_Hash: 4096
    EvalDir: ../evals/baseline/suisho5
    FV_SCALE: 24
    NetworkDelay: 120
    NetworkDelay2: 1120

log_dir: ../results/floodgate/Rin-suisho5-v1
kifu_dir: ../kifu

auto_reconnect: true
reconnect_wait_sec: 30
max_consecutive_failures: 5
max_games_per_session: 50
log_level: INFO
```

別ハンドルで参加する場合は `configs/match/floodgate_<handle>.yaml` を作って
`account.username` / `engine.options.EvalDir` / `log_dir` を変更。

## 4. 起動

```powershell
python scripts/floodgate_client.py --config configs/match/floodgate_v1.yaml
```

挙動:

1. `.env` をロード(リポ root の `.env` を優先)
2. やねうら王を subprocess 起動 → `usi`/`isready`/options 設定
3. floodgate サーバに TCP 接続 → `LOGIN <user> <pw>` → `LOGIN:<user> OK`
4. `BEGIN Game_Summary` 受信(対局割当待ち。ペア成立まで数十分かかることも)
5. `AGREE <game_id>` → `START:<game_id>` で対局開始
6. 対局ループ:
   - 自分手番: `position startpos moves ...` → `go btime ... wtime ... byoyomi ...` → bestmove → CSA変換 → 送信
   - 相手手番: サーバから `+/-XXXXFF,T<n>` 受信 → 局面更新
   - 終局: `#WIN` / `#LOSE` / `#DRAW` / `#SENNICHITE` 等を受信 → ループ抜け
7. 棋譜を `kifu/yyyy/mm/dd/<game_id>.csa` に保存
8. 結果 1 行を `<log_dir>/log.jsonl` に追記
9. 次の対局割当待ち(or `max_games_per_session` 到達で終了)

切断時は 30 秒待ってから再接続(`auto_reconnect=true`)。
連続 5 回失敗で停止。Ctrl-C で進行中の対局を完走後にグレースフル停止。

## 5. ローカル乾燥テスト(本番接続前の動作確認)

実 floodgate に接続せず、モック CSA サーバ + Fake USI Engine で 1 局のフローを
確認できる。本番接続前にこれが通ることを確認する習慣を推奨。

```powershell
python tests/test_floodgate_client_dryrun.py
```

期待出力:

```
test_floodgate_client_dryrun.py
  ok ran 1 game (returned 1)
  ok kifu written: ...csa (~700 bytes)
  ok log.jsonl appended: #LOSE (moves=N)
  ok server received expected commands (~6 lines)
ALL TESTS PASSED
```

その他の単体テスト:

```powershell
python scripts/utils/test_csa_usi.py     # CSA <-> USI 指し手変換
python scripts/utils/test_csa.py          # CSA プロトコルパース(socketpair モック)
```

## 6. レーティング監視

レーティングは floodgate 公式ページで確認:
<http://wdoor.c.u-tokyo.ac.jp/shogi/LATEST/rating.html>(エンジン名で検索)

当面は手動で `docs/RATING.md` に追記する運用。
将来的に自動取得スクリプトを別ticketで検討。

## 7. 棋譜の管理

- 1 局 1 ファイル: `kifu/yyyy/mm/dd/<game_id>.csa`
- 日次でまとめて GitHub にコミット(spec.md 確定方針)
- 累積で数百MB級になったら HuggingFace Dataset(`rin-shogi/rin-kifu`等)に移管(別ticket)
- 認証情報の漏洩防止:
  - 棋譜書込前に `FLOODGATE_PASSWORD` の値が含まれていないかを `_write_kifu` 内で assert
  - ログ出力時もパスワードを `mask_password()` で `********` に置換

## 8. 運用ガイドライン

| 項目 | 推奨 |
|---|---|
| ハンドル命名 | `Rin-<eval>-v<engine>`(例: `Rin-suisho5-v1`)。評価関数差し替え時は別ハンドル |
| 同時接続数 | 1 アカウント = 1 エンジン。複数並列はサーバ負荷に注意 |
| 評価関数差し替えタイミング | 自己対戦で出発点比 R+30 程度の優位が確認できた評価関数のみ floodgate へ |
| 時間制 | floodgate のサーバ側時間制を素直に受ける(設定改変不要) |
| ログ保管 | 全棋譜・全 log.jsonl を保管。教師再利用にも効く |
| 再接続 | `auto_reconnect=true` のデフォルト運用。連続失敗時は手動介入 |

## 9. リスク・トラブルシュート

| 症状 | 確認・対処 |
|---|---|
| `LOGIN:incorrect` | `.env` のパスワード or floodgate ハンドル名を再確認 |
| 対局オファーが来ない | 連続接続を控えてしばらく時間を空ける(サーバ側マッチング待ち) |
| 反則負け(`#ILLEGAL_MOVE`) | 棋譜の最後の指し手を確認、CSA<->USI 変換のバグなら issue 起票 |
| 連続切断 | ネットワーク確認後、`max_consecutive_failures` を一時的に下げて停止し、状況確認 |
| `8h2b+` 等で ValueError | エンジンが非合法手を返した可能性。`%TORYO` で投了して継続(ログを確認) |

## 10. 関連ドキュメント

- `docs/BUILD.md` — やねうら王ビルド手順
- `docs/EVAL_BASELINES.md` — 公開評価関数の調査
- `docs/RATING.md` — floodgate レーティング推移メモ
- `docs/ITERATION.md` — 棋力向上イテレーション全体像
