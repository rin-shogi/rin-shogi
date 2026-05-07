# FLOODGATE: shogi-server (floodgate) 参加手順

floodgate は東京大学計算機科学コースが運用する将棋エンジンの自動対局場。
shogi-server プロトコル(CSAベース)で接続する。
本プロジェクトでは plan の Phase E(M5)以降、棋力測定の主軸として継続参加する。

公式: <http://wdoor.c.u-tokyo.ac.jp/shogi/>

## 1. 利用前の確認事項(plan E1)

- **登録方法・運用ポリシー**: 公式案内を都度確認(時期により変動)
- **接続先サーバ**: `wdoor.c.u-tokyo.ac.jp:4081`(例。最新は公式参照)
- **持ち時間制**: floodgate のデフォルト(15分切れ負け+秒読み等、複数枠あり)
- **エンジン名規則**: 自分のチーム/エンジン名を一意に決める
- **マナー**: 連続接続・複数エンジン同時参加に関する制限

## 2. 接続方式

shogi-server は CSA プロトコル(テキストベースのソケット通信)。

選択肢:

1. **公式の shogi-server クライアント(Ruby)** を使う(最も枯れている)
2. **将棋所 / ShogiGUI** に floodgate プラグインを入れる(GUI から)
3. **自前 Python 実装**(`scripts/floodgate_client.py`)

本プロジェクトでは **(3) 自前 Python 実装** を採用(運用自動化・ログ整備のため)。

## 3. 設定

```yaml
# configs/match/floodgate_v1.yaml
name: floodgate_v1
mode: floodgate
server:
  host: wdoor.c.u-tokyo.ac.jp
  port: 4081
account:
  username: <YOUR_HANDLE>
  password: <YOUR_PASSWORD>   # 環境変数経由を推奨。後述
engine:
  binary: ../engine/bin/YaneuraOu-NORMAL.exe
  options:
    Threads: 8
    Hash: 4096
    EvalDir: ../evals/baseline/suisho   # 当面は出発点で運用、徐々に trained に差し替え
    BookFile: ../evals/book/main.db     # 任意
time_control_hint:
  byoyomi_ms: 10000           # サーバ側の時間制に合わせて
  fischer_inc_ms: 0
log_dir: ../results/floodgate/v1
auto_reconnect: true
max_games_per_session: null   # null = 無制限
```

> 認証情報: パスワードは設定ファイルに直書きせず、環境変数(`FLOODGATE_PASSWORD`)から
> 読む実装にする。`scripts/floodgate_client.py` は YAML の `password: $env:FLOODGATE_PASSWORD`
> 形式を解釈する。

## 4. 起動

```powershell
$env:FLOODGATE_PASSWORD = "your-password-here"
python scripts/floodgate_client.py --config configs/match/floodgate_v1.yaml
```

挙動:

- サーバに接続 → ログイン → ゲーム待ち受け
- ゲームが始まったら USIエンジンに `position` / `go` を送り、CSA に `bestmove` を送り返す
- 終局後、棋譜を `<log_dir>/<game_id>.csa` に保存、結果サマリを `<log_dir>/log.jsonl` に追記
- `auto_reconnect=true` ならネットワーク切断時に自動再接続

## 5. レーティング監視

- floodgate 公式ページの Self-rating 一覧で確認(エンジン名で検索)
- ローカルでは `<log_dir>/log.jsonl` に対局相手・結果が貯まるので、`scripts/match_summary.py --jsonl` で勝率を集計可能

## 6. 棋譜の二次活用(教師データへ)

floodgate アーカイブ棋譜は教師データとして再利用できる(D8 で参照):

```powershell
python scripts/floodgate_pgn.py --year 2025 --output ../data/floodgate/2025
python scripts/floodgate_pgn.py --rating-min 3000 --output ../data/floodgate/strong
```

(詳細は `scripts/floodgate_pgn.py --help`)

## 7. 運用ガイドライン

| 項目 | 推奨 |
|---|---|
| エンジン名 | プロジェクト名 + 評価関数バージョン(例: `shogi-ai-v01-suisho`) |
| 同時接続数 | 1 アカウント = 1 エンジン(複数並列はサーバ負荷に注意) |
| 評価関数差し替えタイミング | 30日移動平均レーティングが安定してから(M2 ベンチで上振れが確認できた版に限る) |
| 時間制 | サーバ側の時間制を素直に受ける(無理に短時間設定にしない) |
| ログ保管 | 全棋譜・全セッションログを `<log_dir>` に保管。教師再利用に効く |
| 障害時 | 公式案内・コミュニティ Slack/X をウォッチ。`auto_reconnect` でも回復しない場合は手動介入 |

## 8. リスク(R5 / R10)

- floodgate サーバの仕様変更・停止: 常時公式情報をチェック
- 想定より低いレーティングが出る: 自己対戦と floodgate でレーティング絶対値が乖離するのは正常。
  まず数百局走らせて移動平均で評価
- 接続不安定で負け扱いされる: ネットワーク冗長化 / `auto_reconnect` の徹底
