# plotting.py
# Every standard performance plot uses the same net-profit curve as official PD.

from pathlib import Path
import math
import matplotlib.pyplot as plt
from framework.reporting import write_json


def _label(score):
    return "∞" if math.isinf(score) else f"{score:.2f}"


def _underwater(values):
    peak = 0.0
    result = []
    for value in values:
        peak = max(peak, value)
        result.append(value - peak)
    return result


def _curve(ax, dates, values, metrics, title):
    # Show initial zero profit as well as the first daily observation.
    if dates:
        ax.plot([dates[0], *dates], [0.0, *values], label="Net profit")
    ax.axhline(0, color="black", linestyle="--", linewidth=0.8)
    ax.set_title(f"{title} | PD={_label(metrics['pd_ratio'])} | Max DD=£{metrics['max_drawdown']:,.2f}")
    ax.set_ylabel("Net profit (£)")
    ax.grid(alpha=0.2)
    ax.tick_params(axis="x", rotation=25)
    if values and metrics["max_drawdown"] > 0:
        depths = _underwater(values)
        trough = min(range(len(depths)), key=depths.__getitem__)
        peak_value, peak_index = 0.0, -1
        for i in range(trough + 1):
            if values[i] > peak_value:
                peak_value, peak_index = values[i], i
        ax.axvspan(dates[max(peak_index, 0)], dates[trough], color="red", alpha=0.12)


def save_per_series_pd(pdres, outdir):
    rows = [{"series": name, **row} for name, row in pdres["per_instrument"].items()]
    rows.append({"series": "portfolio", **pdres["portfolio"]})
    write_json(Path(outdir) / "per_series_pd.json", rows)


def save_performance_plots(net, pdres, activity, outdir):
    outdir = Path(outdir)
    dates, values = net["dates"], net["portfolio_cum"]
    fig, ax = plt.subplots(figsize=(12, 6))
    _curve(ax, dates, values, pdres["portfolio"], "Portfolio")
    ax.set_xlabel("Date (daily closing valuation)")
    fig.tight_layout()
    fig.savefig(outdir / "equity_curve.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(12, 5))
    if dates:
        ax.plot([dates[0], *dates], [net["start_equity"], *net["values"]])
    ax.axhline(net["start_equity"], color="black", linestyle="--", linewidth=0.8)
    ax.set(title="Account equity after commission and market-order slippage",
           ylabel="Account equity (£)", xlabel="Date")
    fig.tight_layout()
    fig.savefig(outdir / "account_equity.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(dates, _underwater(values))
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set(title="Portfolio drawdown from net profit", ylabel="Drawdown (£, negative)", xlabel="Date")
    fig.tight_layout()
    fig.savefig(outdir / "portfolio_underwater.png", dpi=130)
    plt.close(fig)

    names = list(net["per_instrument_cum"])
    for name in names:
        fig, ax = plt.subplots(figsize=(10, 4))
        _curve(ax, dates, net["per_instrument_cum"][name], pdres["per_instrument"][name], name)
        ax.set_xlabel("Date")
        fig.tight_layout()
        fig.savefig(outdir / f"{name}_equity.png", dpi=130)
        plt.close(fig)

    rows = 1 + (len(names) + 1) // 2
    fig = plt.figure(figsize=(15, 3.1 * rows), layout="constrained")
    grid = fig.add_gridspec(rows, 2)
    ax = fig.add_subplot(grid[0, :])
    _curve(ax, dates, values, pdres["portfolio"],
           f"Portfolio; activity {activity['activity_pct']:.1f}%")
    for i, name in enumerate(names):
        ax = fig.add_subplot(grid[1 + i // 2, i % 2])
        _curve(ax, dates, net["per_instrument_cum"][name], pdres["per_instrument"][name], name)
    fig.savefig(outdir / "equity_dashboard.png", dpi=110)
    plt.close(fig)


def save_diagnostic_plot(result, outdir, filename, title):
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(result["dates"], result["portfolio_cum"])
    ax.axhline(0, color="black", linestyle="--", linewidth=0.8)
    ax.set(title=title, xlabel="Date", ylabel="Diagnostic P&L (£)")
    fig.tight_layout()
    fig.savefig(Path(outdir) / filename, dpi=120)
    plt.close(fig)
