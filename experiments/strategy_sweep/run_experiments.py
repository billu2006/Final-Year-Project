"""Run a consistent parameter sweep over five BT396 example strategies."""
import csv
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROJECT = Path("/Users/billu/Desktop/BT396_version_0_1_5s")
PY = PROJECT / "venv" / "bin" / "python"
DATA_DIR = sys.argv[1] if len(sys.argv) > 1 else "./DATA/PART1"
LABEL = sys.argv[2] if len(sys.argv) > 2 else "PART1"
OUT = Path(__file__).resolve().parent / f"runs_{LABEL}"
OUT.mkdir(exist_ok=True)

# strategy -> (signal param(s) at default, at half, at double)
SIGNAL = {
    "copycat": {"half": ["stake=0.5"], "default": [], "double": ["stake=2"]},
    "sma_cross_multi": {"half": ["fast=5", "slow=15"], "default": [], "double": ["fast=20", "slow=60"]},
    "p_bbands_trend_following": {"half": ["lookback=10"], "default": [], "double": ["lookback=40"]},
    "p_bbands_contrarian": {"half": ["lookback=10"], "default": [], "double": ["lookback=40"]},
    "p_mm_spread": {"half": ["spreadPercentage=0.05"], "default": [], "double": ["spreadPercentage=0.2"]},
}

def jobs():
    for strat, levels in SIGNAL.items():
        yield strat, "baseline", levels["default"], 1.0
        yield strat, "signal_half", levels["half"], 1.0
        yield strat, "signal_double", levels["double"], 1.0
        yield strat, "smult_0", levels["default"], 0.0
        yield strat, "smult_2", levels["default"], 2.0

def run(job):
    strat, variant, params, smult = job
    outdir = OUT / f"{strat}__{variant}"
    cmd = [str(PY), "main.py", "--strategy", strat, "--no-plot", "--data-dir", DATA_DIR,
           "--s-mult", str(smult), "--output-dir", str(outdir)]
    for p in params:
        cmd += ["--param", p]
    proc = subprocess.run(cmd, cwd=PROJECT, capture_output=True, text=True)
    if proc.returncode != 0:
        return {"strategy": strat, "variant": variant, "error": proc.stderr[-500:]}
    s = json.loads((outdir / "run_summary.json").read_text())
    pdres = json.loads((outdir / "pd_results.json").read_text())
    per = pdres["per_instrument"]
    profitable = sum(1 for r in per.values() if r["net_profit"] > 0)
    fills = json.loads((outdir / "fills.json").read_text())
    return {
        "strategy": strat, "variant": variant,
        "params": " ".join(params) or "(defaults)", "s_mult": smult,
        "net_profit": round(s["net_profit"], 2),
        "pd_ratio": s["pd_ratio"], "pd_status": s["pd_status"],
        "max_drawdown": round(s["max_drawdown"], 2),
        "slippage_paid": round(s["slippage_paid"], 2),
        "fills": len(fills),
        "activity_pct": round(s["activity_pct"], 1),
        "profitable_series": f"{profitable}/10",
        "bankrupt": s["bankrupt"],
        "per_series_net": {k: round(v["net_profit"], 2) for k, v in per.items()},
    }

if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=4) as ex:
        rows = list(ex.map(run, list(jobs())))
    (OUT / "results.json").write_text(json.dumps(rows, indent=2))
    cols = ["strategy", "variant", "params", "s_mult", "net_profit", "pd_ratio", "pd_status",
            "max_drawdown", "slippage_paid", "fills", "activity_pct", "profitable_series", "bankrupt"]
    with (OUT / "results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            if "error" in r:
                print("FAILED", r["strategy"], r["variant"], r["error"], file=sys.stderr)
            else:
                w.writerow(r)
    for r in rows:
        if "error" not in r:
            print(f'{r["strategy"]:<26}{r["variant"]:<14}{r["params"]:<28}s_mult={r["s_mult"]:<4}'
                  f'net={r["net_profit"]:>12,.2f}  PD={r["pd_ratio"]:>10}  DD={r["max_drawdown"]:>11,.2f}  '
                  f'slip={r["slippage_paid"]:>10,.2f}  fills={r["fills"]:>5}  act={r["activity_pct"]:>5}%  '
                  f'prof={r["profitable_series"]}')
