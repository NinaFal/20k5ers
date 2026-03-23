#!/usr/bin/env python3
"""
Calculate trading metrics from backtest results.

Metrics:
RENDEMENT:
- Profit Factor
- Win Rate
- Real R:R (average win / average loss in R)
- EV per trade (expected value)
- Breakeven WR nodig

RISICO:
- Sharpe Ratio (annualized, risk-free = 0)
- Sortino Ratio (annualized)
- Calmar Ratio (CAGR / Max Drawdown)
- Ulcer Index
- Max Drawdown

CONSISTENTIE:
- Positieve maanden (% of months with positive PnL)
"""

import pandas as pd
import numpy as np
import json
import sys
from pathlib import Path


def load_data(output_dir: str):
    trades_path = Path(output_dir) / "trades.csv"
    results_path = Path(output_dir) / "results.json"

    trades = pd.read_csv(trades_path)
    with open(results_path) as f:
        results = json.load(f)

    return trades, results


def aggregate_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """Aggregate partial closes into full trades by base ticket."""
    trades["open_time"] = pd.to_datetime(trades["open_time"], utc=True)
    trades["close_time"] = pd.to_datetime(trades["close_time"], utc=True)

    # Extract base ticket number
    trades["base_ticket"] = (
        trades["ticket"].astype(str).str.extract(r"^(\d+)")[0].astype(int)
    )

    # Aggregate by base ticket + symbol
    agg = (
        trades.groupby(["base_ticket", "symbol"])
        .agg(
            total_pnl=("pnl", "sum"),
            open_time=("open_time", "min"),
            close_time=("close_time", "max"),
        )
        .reset_index()
    )

    agg["winner"] = agg["total_pnl"] > 0
    agg["year"] = agg["close_time"].dt.year
    agg["month"] = agg["close_time"].dt.to_period("M")

    return agg


def build_equity_curve(trades_agg: pd.DataFrame, initial_balance: float) -> pd.Series:
    """Build equity curve sorted by close time."""
    sorted_trades = trades_agg.sort_values("close_time")
    equity = initial_balance + sorted_trades["total_pnl"].cumsum()
    equity.index = sorted_trades["close_time"].values
    return equity


def calc_profit_factor(trades_agg: pd.DataFrame) -> float:
    gross_profit = trades_agg[trades_agg["total_pnl"] > 0]["total_pnl"].sum()
    gross_loss = abs(trades_agg[trades_agg["total_pnl"] <= 0]["total_pnl"].sum())
    if gross_loss == 0:
        return float("inf")
    return gross_profit / gross_loss


def calc_win_rate(trades_agg: pd.DataFrame) -> float:
    return trades_agg["winner"].mean() * 100


def calc_real_rr(trades_agg: pd.DataFrame) -> float:
    """Real R:R = average winning trade / average losing trade (absolute)."""
    wins = trades_agg[trades_agg["total_pnl"] > 0]["total_pnl"]
    losses = trades_agg[trades_agg["total_pnl"] <= 0]["total_pnl"]
    if len(wins) == 0 or len(losses) == 0:
        return 0.0
    avg_win = wins.mean()
    avg_loss = abs(losses.mean())
    if avg_loss == 0:
        return float("inf")
    return avg_win / avg_loss


def calc_ev_per_trade(trades_agg: pd.DataFrame) -> float:
    """EV = Win Rate * Avg Win - Loss Rate * Avg Loss."""
    wr = trades_agg["winner"].mean()
    lr = 1 - wr
    wins = trades_agg[trades_agg["total_pnl"] > 0]["total_pnl"]
    losses = trades_agg[trades_agg["total_pnl"] <= 0]["total_pnl"]
    avg_win = wins.mean() if len(wins) > 0 else 0
    avg_loss = abs(losses.mean()) if len(losses) > 0 else 0
    return wr * avg_win - lr * avg_loss


def calc_breakeven_wr(trades_agg: pd.DataFrame) -> float:
    """Breakeven WR = 1 / (1 + Real R:R) * 100."""
    rr = calc_real_rr(trades_agg)
    if rr == 0:
        return 100.0
    return 1 / (1 + rr) * 100


def calc_max_drawdown(equity: pd.Series) -> float:
    """Max drawdown as percentage of peak equity."""
    rolling_max = equity.expanding().max()
    drawdown = (equity - rolling_max) / rolling_max * 100
    return abs(drawdown.min())


def calc_sharpe_ratio(trades_agg: pd.DataFrame, initial_balance: float) -> float:
    """
    Annualized Sharpe Ratio using monthly returns, risk-free rate = 0.
    """
    # Monthly PnL
    monthly = trades_agg.groupby("month")["total_pnl"].sum()
    if len(monthly) < 2:
        return 0.0

    # Build running equity to get monthly returns
    # Start with initial balance and add cumulative monthly pnl
    monthly_sorted = monthly.sort_index()
    equity_start = initial_balance
    cumulative = equity_start + monthly_sorted.cumsum()
    prev_equity = pd.concat([pd.Series([equity_start]), cumulative.iloc[:-1]])
    prev_equity.index = cumulative.index
    monthly_returns = (cumulative - prev_equity) / prev_equity

    mean_ret = monthly_returns.mean()
    std_ret = monthly_returns.std()
    if std_ret == 0:
        return 0.0

    # Annualize (12 months)
    return (mean_ret / std_ret) * np.sqrt(12)


def calc_sortino_ratio(trades_agg: pd.DataFrame, initial_balance: float) -> float:
    """
    Annualized Sortino Ratio using monthly returns, MAR = 0.
    """
    monthly = trades_agg.groupby("month")["total_pnl"].sum().sort_index()
    if len(monthly) < 2:
        return 0.0

    equity_start = initial_balance
    cumulative = equity_start + monthly.cumsum()
    prev_equity = pd.concat([pd.Series([equity_start]), cumulative.iloc[:-1]])
    prev_equity.index = cumulative.index
    monthly_returns = (cumulative - prev_equity) / prev_equity

    mean_ret = monthly_returns.mean()
    negative_returns = monthly_returns[monthly_returns < 0]
    if len(negative_returns) == 0:
        return float("inf")

    downside_std = np.sqrt((negative_returns**2).mean())
    if downside_std == 0:
        return float("inf")

    return (mean_ret / downside_std) * np.sqrt(12)


def calc_calmar_ratio(trades_agg: pd.DataFrame, initial_balance: float, years: float) -> float:
    """
    Calmar Ratio = CAGR / Max Drawdown.
    """
    final_balance = initial_balance + trades_agg["total_pnl"].sum()
    if final_balance <= 0 or years <= 0:
        return 0.0

    cagr = ((final_balance / initial_balance) ** (1 / years) - 1) * 100

    # Max drawdown
    equity = build_equity_curve(trades_agg, initial_balance)
    max_dd = calc_max_drawdown(equity)

    if max_dd == 0:
        return float("inf")

    return cagr / max_dd


def calc_ulcer_index(equity: pd.Series) -> float:
    """
    Ulcer Index = sqrt(mean of squared percentage drawdowns from peak).
    """
    rolling_max = equity.expanding().max()
    pct_drawdown = (equity - rolling_max) / rolling_max * 100
    return np.sqrt((pct_drawdown**2).mean())


def calc_positive_months(trades_agg: pd.DataFrame) -> tuple:
    """Returns (positive_months, total_months, percentage)."""
    monthly = trades_agg.groupby("month")["total_pnl"].sum()
    total = len(monthly)
    positive = (monthly > 0).sum()
    pct = positive / total * 100 if total > 0 else 0.0
    return positive, total, pct


def calculate_all_metrics(output_dir: str):
    trades, results = load_data(output_dir)
    initial_balance = results.get("initial_balance", 20000.0)

    trades_agg = aggregate_trades(trades)
    equity = build_equity_curve(trades_agg, initial_balance)

    # Date range
    start_date = trades_agg["open_time"].min()
    end_date = trades_agg["close_time"].max()
    years = (end_date - start_date).days / 365.25

    # --- RENDEMENT ---
    profit_factor = calc_profit_factor(trades_agg)
    win_rate = calc_win_rate(trades_agg)
    real_rr = calc_real_rr(trades_agg)
    ev_per_trade = calc_ev_per_trade(trades_agg)
    breakeven_wr = calc_breakeven_wr(trades_agg)

    # --- RISICO ---
    sharpe = calc_sharpe_ratio(trades_agg, initial_balance)
    sortino = calc_sortino_ratio(trades_agg, initial_balance)
    calmar = calc_calmar_ratio(trades_agg, initial_balance, years)
    ulcer = calc_ulcer_index(equity)
    max_dd = calc_max_drawdown(equity)

    # --- CONSISTENTIE ---
    pos_months, total_months, pos_months_pct = calc_positive_months(trades_agg)

    # --- SUMMARY STATS ---
    final_balance = initial_balance + trades_agg["total_pnl"].sum()
    cagr = ((final_balance / initial_balance) ** (1 / years) - 1) * 100 if years > 0 else 0
    total_trades = len(trades_agg)
    winners = trades_agg["winner"].sum()
    losers = total_trades - winners

    print()
    print("=" * 60)
    print("  BACKTEST METRICS REPORT: 2015-2025")
    print("=" * 60)
    print(f"  Periode:          {start_date.date()} → {end_date.date()}")
    print(f"  Beginsaldo:       ${initial_balance:,.0f}")
    print(f"  Eindsaldo:        ${final_balance:,.2f}")
    print(f"  Totaal trades:    {total_trades} ({winners}W / {losers}L)")
    print(f"  CAGR:             {cagr:.1f}%")
    print()
    print("  ─── RENDEMENT ──────────────────────────────────────")
    print(f"  Profit Factor:    {profit_factor:.2f}")
    print(f"  Win Rate:         {win_rate:.1f}%")
    print(f"  Real R:R:         1 : {real_rr:.2f}")
    print(f"  EV per trade:     ${ev_per_trade:.2f}")
    print(f"  Breakeven WR:     {breakeven_wr:.1f}%")
    print()
    print("  ─── RISICO ─────────────────────────────────────────")
    print(f"  Sharpe Ratio:     {sharpe:.2f}")
    print(f"  Sortino Ratio:    {sortino:.2f}")
    print(f"  Calmar Ratio:     {calmar:.2f}")
    print(f"  Ulcer Index:      {ulcer:.2f}%")
    print(f"  Max Drawdown:     {max_dd:.2f}%")
    print()
    print("  ─── CONSISTENTIE ───────────────────────────────────")
    print(f"  Positieve maanden:{pos_months}/{total_months} ({pos_months_pct:.1f}%)")
    print("=" * 60)

    return {
        "rendement": {
            "profit_factor": round(profit_factor, 2),
            "win_rate_pct": round(win_rate, 1),
            "real_rr": round(real_rr, 2),
            "ev_per_trade_usd": round(ev_per_trade, 2),
            "breakeven_wr_pct": round(breakeven_wr, 1),
        },
        "risico": {
            "sharpe_ratio": round(sharpe, 2),
            "sortino_ratio": round(sortino, 2),
            "calmar_ratio": round(calmar, 2),
            "ulcer_index_pct": round(ulcer, 2),
            "max_drawdown_pct": round(max_dd, 2),
        },
        "consistentie": {
            "positieve_maanden": int(pos_months),
            "totale_maanden": int(total_months),
            "positieve_maanden_pct": round(pos_months_pct, 1),
        },
        "summary": {
            "initial_balance": initial_balance,
            "final_balance": round(final_balance, 2),
            "total_trades": total_trades,
            "winners": int(winners),
            "losers": int(losers),
            "cagr_pct": round(cagr, 1),
            "years": round(years, 1),
        },
    }


if __name__ == "__main__":
    output_dir = sys.argv[1] if len(sys.argv) > 1 else "backtest/output/backtest_2015_2025_metrics_run"
    metrics = calculate_all_metrics(output_dir)

    # Save to JSON
    metrics_path = Path(output_dir) / "metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\n  Metrics saved to: {metrics_path}")
