# 琳 (Rin) — 評価関数 CHANGELOG

将棋AI 琳(Rin) で使用する評価関数の来歴と性能を記録。
新規バージョンを追加する際は、新しいエントリを **先頭** に追加(逆時系列)。

## 命名規則

- ベースライン(公開評価関数): `<source>` 例: `suisho5`
- 自前学習: `Rin-v<major>.<minor>` 例: `Rin-v0.1` / `Rin-v0.2` / `Rin-v1.0`

## フォーマット

```
## v<version> (yyyy-mm-dd)
- 種別: baseline / trained / 派生
- 出発点: <baseline name> または <previous version>
- 教師データ: <data/selfplay/<run_id> 等のソース、局面数>
- 学習レシピ: configs/train/<name>.yaml(エポック・学習率・損失関数 等の要点)
- 性能: 自己対戦勝率 vs <相手> = <rate>% (N=<games>, 95% CI=±<ci>%, ΔElo=<delta>)
- floodgate レーティング: R<rating>(対局数 <N>、計測期間 yyyy-mm-dd〜yyyy-mm-dd)
- 備考: 改善点・既知の弱点 など
```

## エントリ

(まだなし。M3 以降に追加)
