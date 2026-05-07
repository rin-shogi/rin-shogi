"""勝率・95%CI・Elo差の計算。

- 勝率 p̂ = (wins + 0.5 * draws) / N
- 95% CI: 正規近似 p̂ ± 1.96 √(p̂(1−p̂)/N)(N が小さいときは Wilson score interval が望ましいが、
  本プロジェクトの用途では単純な正規近似で十分)
- Elo 差: ΔElo = -400 * log10((1 / p̂) - 1)
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class MatchStats:
    games: int
    wins_a: int
    losses_a: int     # = wins_b
    draws: int
    illegal_or_timeout: int = 0

    @property
    def scored_games(self) -> int:
        # illegal/timeout は除外して有効局数とする
        return self.wins_a + self.losses_a + self.draws

    @property
    def win_rate_a(self) -> float:
        n = self.scored_games
        if n == 0:
            return 0.5
        return (self.wins_a + 0.5 * self.draws) / n

    @property
    def ci95(self) -> float:
        n = self.scored_games
        if n == 0:
            return 0.0
        p = self.win_rate_a
        return 1.96 * math.sqrt(p * (1 - p) / n)

    @property
    def elo_diff(self) -> float:
        p = max(min(self.win_rate_a, 0.99999), 0.00001)
        return -400.0 * math.log10((1.0 / p) - 1.0)

    @property
    def elo_ci95(self) -> float:
        # 上下端を勝率±CIに当てはめてElo範囲を取り、半幅を返す
        p = self.win_rate_a
        ci = self.ci95
        lo = max(min(p - ci, 0.99999), 0.00001)
        hi = max(min(p + ci, 0.99999), 0.00001)
        elo_lo = -400.0 * math.log10((1.0 / lo) - 1.0)
        elo_hi = -400.0 * math.log10((1.0 / hi) - 1.0)
        return (elo_hi - elo_lo) / 2.0

    @property
    def is_significant(self) -> bool:
        # 95% CI が 50% を含まないなら統計有意
        return abs(self.win_rate_a - 0.5) > self.ci95


def format_summary(name: str, stats: MatchStats) -> str:
    return (
        f"=== {name} ===\n"
        f"Games:    {stats.games} (a={stats.wins_a} wins, b={stats.losses_a} wins, "
        f"draws={stats.draws}, illegal/timeout={stats.illegal_or_timeout})\n"
        f"Win rate (a): {stats.win_rate_a*100:.2f}%  ±  {stats.ci95*100:.2f}%  (95% CI)\n"
        f"ΔElo (a−b):   {stats.elo_diff:+.1f}   ±  {stats.elo_ci95:.1f}   (95% CI)\n"
        f"Statistically significant: {'YES' if stats.is_significant else 'NO'}"
    )
