# EVAL_BASELINES: 出発点となる公開評価関数の調査

本ドキュメントは「やねうら王 + 公開強力評価関数」の出発点候補を整理するためのもの(plan の B1)。
最終的な採用は `evals/baseline/<name>/README.md` と `evals/CHANGELOG.md` に記載する。

## 採用基準

1. **業界標準・実績**: WCSC・電竜戦などで上位入賞、もしくは広く配布され検証されている
2. **やねうら王互換**: NNUE HalfKP_256x2-32-32 形式で利用可能
3. **ライセンス整合**: GPLv3 互換、または再配布制約がはっきりしている(再配布禁止ならローカル取得スクリプト方式)
4. **入手性**: 配布元が現存し継続的に取得可能

## 主要候補

> 注: 以下はサーベイ用の列挙であり、最終確認は plan B1 の段階で各配布元の最新情報を当たること。
> 配布元 URL・ライセンス文言・最新バージョンは時期により変わるので、本ファイルは年次でレビュー。

### Suisho(水匠)系

- 概要: 国内最強級 NNUE 評価関数の代表格。WCSC・電竜戦で長年上位
- 形式: HalfKP_256x2-32-32(やねうら王互換)
- 入手: GitHub 等で公開(バージョンによる)
- ライセンス: 配布バージョンによる(要確認)。多くの世代は再配布許可・GPLv3 系
- 採否判断: **第1候補**

### tanuki / tnk 系

- 概要: 評価関数 + 定跡含めた強力なパッケージ。WCSC でも実績多数
- 形式: HalfKP 互換(派生形あり、要確認)
- 入手: 公式サイト / GitHub
- ライセンス: 配布物による(要確認)
- 採否判断: 第2候補(水匠と並列で比較ベンチマーク)

### Kristallweizen / Qhapaq / orqha 系

- 概要: 旧来から強力で、学習レシピが公開されているケースもあり研究価値が高い
- 形式: HalfKP 系
- 入手: GitHub
- ライセンス: 配布物による
- 採否判断: 学習レシピの参照用に主、評価関数の比較用に副

### illqha 系

- 概要: 強力な NNUE 評価関数。やねうら王での運用実績多数
- 形式: HalfKP 系
- 入手: GitHub / 配布元
- 採否判断: 第3候補

### やねうら王同梱の標準評価関数

- 概要: やねうら王リポジトリ自体が同梱する評価関数(あれば)
- 採否判断: ベースライン下限の参考(M2 のベースライン測定の片側として常に入れる)

## 配置規則

```
evals/baseline/<name>/
├── README.md          # この評価関数の出処・ライセンス・取得手順
├── fetch.ps1          # 取得スクリプト(再配布できない/したくない場合は必須)
├── nn.bin             # 評価関数本体(.gitignore 対象)
└── LICENSE            # 元ライセンスのコピー(可能なら)
```

`fetch.ps1` テンプレ:

```powershell
# 例: GitHub Releases から ZIP を取って展開
$ErrorActionPreference = "Stop"
$Url = "https://github.com/<repo>/releases/download/<tag>/<file>.zip"
$Out = Join-Path $PSScriptRoot "tmp.zip"
Invoke-WebRequest -Uri $Url -OutFile $Out
Expand-Archive -Path $Out -DestinationPath $PSScriptRoot -Force
Remove-Item $Out
Write-Host "Fetched and extracted to $PSScriptRoot"
```

## 比較ベンチマーク手順

`scripts/selfplay_match.py` で以下のラウンドロビン:

1. やねうら王同梱(あれば標準) vs 候補A(水匠)
2. 候補A(水匠) vs 候補B(tnk 等)
3. 候補A(水匠) vs 候補C(illqha 等)

各 100-200 局、1手1秒。結果は `results/matches/baselines/` に保存し、`evals/CHANGELOG.md` のベースライン節に記録。
最も強い候補を「第1出発点」として `evals/baseline/<name>/` に確定配置し、後続フェーズ(D, F)の起点とする。

## ライセンス対応のフロー

1. 候補ごとに配布元の LICENSE を確認(GPLv3 互換 / MIT / 独自再配布許可 / 再配布禁止 / 未明記)
2. **GPLv3 互換 or 再配布許可**: `evals/baseline/<name>/` 配下にバイナリを置いてもよいが、本リポジトリの `.gitignore` で除外している(リポジトリのサイズ抑制目的)。`fetch.ps1` で取得する運用が原則
3. **再配布禁止 / 未明記**: 必ず `fetch.ps1` ベース、`evals/baseline/<name>/README.md` に明記
4. **不明な場合**: 採用見送り、または配布元へ問い合わせ
