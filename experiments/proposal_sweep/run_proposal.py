"""Run the parameter sweep described in project_proposal_data.md.

Usage: venv/bin/python experiments/proposal_sweep/run_proposal.py [workers]
Writes results.csv and per_series.csv next to this file.
"""
import csv
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
PY = PROJECT / "venv" / "bin" / "python"
DATASETS = ["PART1", "PART1_UPDATED"]
WORKERS = int(sys.argv[1]) if len(sys.argv) > 1 else 8


def L(v, n=10):
    return json.dumps([v] * n)


# strategy -> (fixed extra params, OFAT {param: [(level, value), ...]})
FIVE = ["low2", "low1", "high1", "high2"]
SIZE = ["low1", "high1"]


def lv(names, values):
    return list(zip(names, values))


S = {
    "sma_cross": ({}, {"fast": lv(FIVE, [5, 7, 15, 20]), "slow": lv(FIVE, [15, 20, 45, 60]),
                       "stake": lv(SIZE, [0.5, 2.0])}),
    "sma_cross_multi": ({}, {"fast": lv(FIVE, [5, 7, 15, 20]), "slow": lv(FIVE, [15, 20, 45, 60]),
                             "stake": lv(SIZE, [0.5, 2.0])}),
    "p_trend_demo": ({}, {"fast": lv(FIVE, [10, 15, 30, 40]), "slow": lv(FIVE, [50, 75, 150, 200]),
                          "allocation": lv(FIVE, [0.1, 0.25, 0.75, 1.0]),
                          "allow_short": [("False", False)]}),
    "p_bbands_trend_following": ({}, {"lookback": lv(FIVE, [10, 15, 30, 40]),
                                      "sdParam": lv(FIVE, [1.0, 1.5, 2.5, 3.0]),
                                      "exit_on_mid": [("True", True)],
                                      "default_size": lv(SIZE, [0.5, 2.0])}),
    "p_bbands_contrarian": ({}, {"lookback": lv(FIVE, [10, 15, 30, 40]),
                                 "sdParam": lv(FIVE, [1.0, 1.5, 2.5, 3.0]),
                                 "default_size": lv(SIZE, [0.5, 2.0])}),
    "bbands_holding_period": ({}, {"lookback": lv(FIVE, [10, 15, 30, 40]),
                                   "sdParam": lv(FIVE, [1.0, 1.5, 2.5, 3.0]),
                                   "holdPeriod": lv(FIVE, [1, 3, 10, 20]),
                                   "default_size": lv(SIZE, [0.5, 2.0])}),
    "p_RSI_contrarian": ({}, {"lookback": lv(FIVE, [7, 10, 21, 28]),
                              "threshold": lv(FIVE, [0, 2.5, 10, 20]),
                              "default_size": lv(SIZE, [0.5, 2.0])}),
    "copycat": ({}, {"stake": lv(FIVE, [0.25, 0.5, 2, 4])}),
    "condpr": ({"response_to_up": L(1), "response_to_dn": L(-1)}, {}),  # variants handled below
    "p_mm_spread": ({}, {"spreadPercentage": lv(FIVE, [0.025, 0.05, 0.2, 0.4]),
                         "inventoryLimits": lv(FIVE, [100, 500, 2000, 5000]),
                         "quote_size": lv(SIZE, [0.5, 2.0])}),
    "simple_limit": ({"log_debug": False}, {"spreadPercentage": lv(FIVE, [0.1, 0.2, 0.45, 0.6]),
                                            "inventoryLimits": lv(FIVE, [10, 25, 100, 200]),
                                            "size": lv(SIZE, [0.5, 2]),
                                            "center_on": [("open", "open"), ("prev_close", "prev_close")],
                                            "range_source": [("yesterday", "yesterday")],
                                            "series_mode": [("rotate", "rotate")]}),
    "example_buy_and_hold": ({"printlog": False}, {"size": lv(SIZE, [0.5, 2])}),
    "fixed": ({}, {"sizes": [("low1", L(0.5)), ("high1", L(2)), ("all_short", L(-1)),
                             ("alternating", json.dumps([1, -1] * 5))]}),
    "p_big_spender": ({}, {"sizes": [("low1", L(0.5)), ("high1", L(2)), ("high2", L(5))],
                           "precheck": [("False", False)]}),
    "p_random": ({}, {"maxLots": lv(FIVE, [1, 5, 20, 40])}),
    "p_bankrupt": ({}, {"leverage": lv(FIVE, [10e6, 20e6, 60e6, 80e6]),
                        "cash_buffer": lv(FIVE, [0, 0.5e6, 2e6, 4e6])}),
    "p_short5_long5": ({}, {"leverage": lv(FIVE, [10e6, 20e6, 60e6, 80e6]),
                            "cash_buffer": lv(FIVE, [0, 0.5e6, 2e6, 4e6])}),
    "s_short_then_long": ({}, {"leverage": lv(FIVE, [2e6, 4e6, 12e6, 16e6]),
                               "cash_buffer": lv(FIVE, [0, 0.5e6, 2e6, 4e6])}),
    "template_strategy": ({"printlog": False}, {}),
}

CONDPR_VARIANTS = [
    ("response", "contrarian", {"response_to_up": L(-1), "response_to_dn": L(1)}),
    ("response", "long_only", {"response_to_up": L(1), "response_to_dn": L(0)}),
    ("response", "short_only", {"response_to_up": L(0), "response_to_dn": L(-1)}),
    ("response", "split", {"response_to_up": json.dumps([1] * 5 + [-1] * 5),
                           "response_to_dn": json.dumps([-1] * 5 + [1] * 5)}),
    ("fixed_stake", "low1", {"stake_policy": "fixed", "fixed_stake": 0.5}),
    ("fixed_stake", "baseline", {"stake_policy": "fixed", "fixed_stake": 1}),
    ("fixed_stake", "high1", {"stake_policy": "fixed", "fixed_stake": 2}),
]

GRIDS = {
    "sma_cross_multi": ("fast", [5, 7, 10, 15, 20], "slow", [15, 20, 30, 45, 60]),
    "p_trend_demo": ("fast", [10, 15, 20, 30, 40], "slow", [50, 75, 100, 150, 200]),
    "p_bbands_trend_following": ("lookback", [10, 15, 20, 30, 40], "sdParam", [1.0, 1.5, 2.0, 2.5, 3.0]),
    "p_bbands_contrarian": ("lookback", [10, 15, 20, 30, 40], "sdParam", [1.0, 1.5, 2.0, 2.5, 3.0]),
    "p_RSI_contrarian": ("lookback", [7, 10, 14, 21, 28], "threshold", [0, 2.5, 5, 10, 20]),
    "p_mm_spread": ("spreadPercentage", [0.025, 0.05, 0.1, 0.2, 0.4],
                    "inventoryLimits", [100, 500, 1000, 2000, 5000]),
}


def fmt(v):
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float) and v.is_integer() and abs(v) >= 1000:
        return str(int(v))
    return str(v)


def jobs():
    for ds in DATASETS:
        for strat, (base, ofat) in S.items():
            yield dict(dataset=ds, strategy=strat, block="baseline", parameter="", level="baseline",
                       params=dict(base), s_mult=1.0)
            for p, levels in ofat.items():
                for name, val in levels:
                    yield dict(dataset=ds, strategy=strat, block="ofat", parameter=p, level=name,
                               params={**base, p: val}, s_mult=1.0)
            if strat == "condpr":
                for p, name, extra in CONDPR_VARIANTS:
                    yield dict(dataset=ds, strategy=strat, block="ofat", parameter=p, level=name,
                               params={**base, **extra}, s_mult=1.0)
            for sm in [0.0, 0.5, 1.5, 2.0]:
                yield dict(dataset=ds, strategy=strat, block="cost", parameter="s_mult", level=str(sm),
                           params=dict(base), s_mult=sm)
        for seed in range(1, 30):
            yield dict(dataset=ds, strategy="p_random", block="seed", parameter="seed", level=str(seed),
                       params={"seed": seed}, s_mult=1.0)
        for strat, (pa, va, pb, vb) in GRIDS.items():
            base = S[strat][0]
            for a in va:
                for b in vb:
                    if pa == "fast" and pb == "slow" and a >= b:
                        continue
                    yield dict(dataset=ds, strategy=strat, block="grid", parameter=f"{pa}|{pb}",
                               level=f"{a}|{b}", params={**base, pa: a, pb: b}, s_mult=1.0)


def run(job):
    tag = f"{job['strategy']}__{job['block']}_{job['parameter']}_{job['level']}".replace("|", "-")
    outdir = HERE / job["dataset"] / tag
    cmd = [str(PY), "main.py", "--strategy", job["strategy"], "--no-plot",
           "--data-dir", f"./DATA/{job['dataset']}", "--s-mult", str(job["s_mult"]),
           "--output-dir", str(outdir)]
    pstr = []
    for k, v in job["params"].items():
        pstr.append(f"{k}={fmt(v)}")
        cmd += ["--param", pstr[-1]]
    row = {k: job[k] for k in ["dataset", "strategy", "block", "parameter", "level", "s_mult"]}
    row["params"] = " ".join(pstr) or "(defaults)"
    proc = subprocess.run(cmd, cwd=PROJECT, capture_output=True, text=True)
    if proc.returncode != 0 or not (outdir / "run_summary.json").exists():
        msg = (proc.stderr or proc.stdout)[-300:].replace("\n", " ")
        row["status"] = "invalid_params" if "Error" in msg and "param" in msg.lower() else "error"
        row["error"] = msg
        return row, []
    s = json.loads((outdir / "run_summary.json").read_text())
    per = json.loads((outdir / "pd_results.json").read_text())["per_instrument"]
    fills = json.loads((outdir / "fills.json").read_text())
    row.update(net_profit=round(s["net_profit"], 2), pd_ratio=s["pd_ratio"], pd_status=s["pd_status"],
               max_drawdown=round(s["max_drawdown"], 2), slippage_paid=round(s["slippage_paid"], 2),
               fills=len(fills), activity_pct=round(s["activity_pct"], 2),
               profitable_series=sum(1 for r in per.values() if r["net_profit"] > 0),
               bankrupt=s["bankrupt"], status="ok")
    series = [{**{k: row[k] for k in ["dataset", "strategy", "block", "parameter", "level", "s_mult"]},
               "series": k, "net_profit": round(v["net_profit"], 2), "pd_ratio": v["pd_ratio"],
               "max_drawdown": round(v["max_drawdown"], 2), "slippage": round(v["slippage"], 2)}
              for k, v in per.items()]
    return row, series


if __name__ == "__main__":
    all_jobs = list(jobs())
    print(f"{len(all_jobs)} runs", flush=True)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        out = list(ex.map(run, all_jobs))
    cols = ["dataset", "strategy", "block", "parameter", "level", "params", "s_mult", "net_profit",
            "pd_ratio", "pd_status", "max_drawdown", "slippage_paid", "fills", "activity_pct",
            "profitable_series", "bankrupt", "status", "error"]
    with (HERE / "results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row, _ in out:
            w.writerow(row)
    scols = ["dataset", "strategy", "block", "parameter", "level", "s_mult", "series", "net_profit",
             "pd_ratio", "max_drawdown", "slippage"]
    with (HERE / "per_series.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=scols)
        w.writeheader()
        for _, series in out:
            w.writerows(series)
    bad = [r for r, _ in out if r["status"] != "ok"]
    print(f"done: {len(out) - len(bad)} ok, {len(bad)} failed")
    for r in bad:
        print("FAILED", r["dataset"], r["strategy"], r["parameter"], r["level"], r.get("error", "")[:200])
