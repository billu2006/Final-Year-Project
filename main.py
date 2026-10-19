#!/usr/bin/env python3
# =============================================================================
# main.py — BT396 Backtrader harness entrypoint
# =============================================================================
# This is the primary executable script for the BT396 framework.
# It acts as the main CLI interface for running trading backtests.
#
# Responsibilities:
#   - Parse command-line arguments and configuration files.
#   - Load 10 aligned CSV data feeds via the framework’s data loader.
#   - Dynamically load and wrap a user strategy with COMP396Base (rules engine).
#   - Configure Backtrader’s Cerebro engine, broker, and analyzers.
#   - Run the backtest, collect results, and output analytics + plots.
#   - Generate summary JSON and diagnostic figures in an output directory.
# =============================================================================

import argparse
import json
import os
import sys
import math
import traceback
from framework.errors import UserInputError, StrategySetupError
from pathlib import Path
from datetime import datetime

# -----------------------------------------------------------------------------
# Framework plotting utilities
# These functions are responsible for producing the output plots and summaries
# after a backtest completes. All images and tables are written to output_dir.
# -----------------------------------------------------------------------------
# Plotting utilities are imported inside main() so import failures are reported.


# -----------------------------------------------------------------------------
# Default configuration used when no config.yaml/json is found.
# This ensures consistent baseline behavior even without external config.
# -----------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "starting_cash": 1_000_000,            # initial portfolio value
    "commission": 0.0,                     # commission rate per trade (fractional)
    "s_mult": 1.0,                         # multiplier for 20% gap slippage model
    "plot": True,                          # enable plotting by default
    "data_dir": "./DATA/PART1",            # default path for 10 CSVs
    "output_dir": "./output",              # directory to save reports/plots
    "end_policy": "liquidate",             # final-day liquidation behavior
    "strategy": "example_buy_and_hold",    # default strategy module
    "strategy_class": None,                # explicitly specify class if needed
    "strategy_params": {},                 # deprecated; CLI params override instead
    "debug": True,                         # enables verbose logging in the framework
}

# -----------------------------------------------------------------------------
# Config loader (YAML preferred, JSON fallback)
# This function attempts to read a config file and merge it into DEFAULT_CONFIG.
# YAML is used first for readability, falling back to JSON for compatibility.
# -----------------------------------------------------------------------------
def load_config(path: Path, *, allow_missing=False) -> dict:
    cfg = DEFAULT_CONFIG.copy()
    if not path.exists():
        if allow_missing:
            return cfg
        raise UserInputError(f"Configuration file not found: {path.resolve()}")
    try:
        import yaml  # type: ignore
    except ImportError:
        try:
            with path.open("r", encoding="utf-8-sig") as f:
                loaded = json.load(f)
        except json.JSONDecodeError as exc:
            raise UserInputError(
                f"Cannot read {path}: install PyYAML for YAML files, "
                "or supply a valid JSON configuration."
            ) from exc
    else:
        try:
            with path.open("r", encoding="utf-8-sig") as f:
                loaded = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise UserInputError(f"Invalid configuration in {path}: {exc}") from exc
    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise UserInputError(f"Configuration in {path} must contain key: value settings.")
    unknown = set(loaded) - set(DEFAULT_CONFIG)
    if unknown:
        raise UserInputError(f"Unknown configuration keys: {', '.join(map(str, unknown))}")
    if loaded.get("strategy_params"):
        raise UserInputError("Use --param key=value for strategy parameters; strategy_params in YAML is unsupported.")
    cfg.update(loaded)
    return cfg

# -----------------------------------------------------------------------------
# CLI parameter coercion helpers
# These handle dynamic typing for strategy parameter overrides.
# -----------------------------------------------------------------------------
TRUE_SET = {"true", "yes", "on"}
FALSE_SET = {"false", "no", "off"}

def _coerce_value(s: str):
    s = s.strip()
    # Try JSON first for lists/dicts/null/bools
    try:
        if s.startswith("[") or s.startswith("{"):
            return json.loads(s)
    except json.JSONDecodeError as exc:
        raise UserInputError(
            f"Invalid JSON parameter value {s!r}. "
            'For a list, use e.g. --param "sizes=[1,1,1,0,0,0,0,0,0,0]".'
        ) from exc
    # Booleans
    low = s.strip().lower()
    if low in TRUE_SET:
        return True
    if low in FALSE_SET:
        return False
    if low == "null":
        return None
    # Int / float
    try:
        if low.startswith("0") and low != "0" and not low.startswith("0."):
            # keep leading-zero strings as-is
            raise ValueError
        return int(s)
    except Exception:
        try:
            return float(s)
        except Exception:
            pass
    # Comma-separated list -> try to coerce each item
    if "," in s:
        parts = [p.strip() for p in s.split(",")]
        return [_coerce_value(p) for p in parts]
    return s

def parse_param_args(param_items: list[str]) -> dict:
    params = {}
    for item in param_items or []:
        if "=" not in item:
            raise UserInputError(f"Invalid --param {item!r}; expected key=value.")
        k, v = item.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k.isidentifier() or not v:
            raise UserInputError(f"Invalid --param {item!r}; supply a parameter name and value.")
        if k in params:
            raise UserInputError(f"Parameter '{k}' was supplied more than once.")
        params[k] = _coerce_value(v)
    return params

# -----------------------------------------------------------------------------
# Directory utility
# -----------------------------------------------------------------------------
def validate_config(cfg: dict) -> None:
    for name in ("starting_cash", "commission", "s_mult"):
        value = cfg[name]
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0 or (name == "starting_cash" and value == 0)):
            relation = "greater than zero" if name == "starting_cash" else "zero or greater"
            raise UserInputError(f"{name} must be a finite number {relation}; got {value!r}.")
    if cfg["end_policy"] not in ("liquidate", "hold"):
        raise UserInputError("end_policy must be 'liquidate' or 'hold'.")
    if not isinstance(cfg["plot"], bool):
        raise UserInputError("plot must be true or false.")
    for name in ("data_dir", "output_dir"):
        if not isinstance(cfg[name], str) or not cfg[name].strip():
            raise UserInputError(f"{name} must be a non-empty folder path.")


def ensure_dir(p: Path):
    # Creates directory recursively if not present.
    p.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------------------------------
# Argument parser definition
# This CLI mirrors Backtrader’s general structure but adds COMP396 extensions.
# -----------------------------------------------------------------------------
def parse_args():
    ap = argparse.ArgumentParser(description="BT396 Backtrader harness")

    # Basic configuration options
    ap.add_argument("--config", default=None,
                    help="Path to YAML/JSON config; defaults to config.yaml when present.")
    ap.add_argument("--strategy", help="Strategy module name (in /strategies).")
    ap.add_argument("--strategy-class", help="Explicit class name (optional).")

    # Simulation-level overrides
    ap.add_argument("--cash", type=float, help="Starting cash (default 1,000,000).")
    ap.add_argument("--commission", type=float, help="Broker commission (e.g. 0.001).")
    ap.add_argument("--s-mult", type=float, help="Slippage multiplier for gap model.")
    ap.add_argument("--no-plot", action="store_true", help="Disable plotting outputs.")
    ap.add_argument("--data-dir", help="Path to folder containing 10 CSV files.")
    ap.add_argument("--output-dir", help="Folder for logs, plots, summaries.")
    ap.add_argument("--end-policy", choices=["liquidate", "hold"],
                    help="Final-day behavior for open positions.")

    # Strategy parameters (CLI only; replaces YAML per-strategy configs)
    ap.add_argument("--param", action="append", default=[],
                    help=("Strategy parameter override (key=value). Repeatable. "
                          "Values auto-parsed as int/float/bool/JSON/list."))

    # Logging / debugging / date filtering
    ap.add_argument("--debug", action="store_true",
                    help="Enable verbose framework logs (orders, fills, etc).")
    ap.add_argument("--diagnostics", action="store_true",
                    help="Also write gross Open-to-Open and closed-trade diagnostic curves.")
    ap.add_argument("--traceback", action="store_true",
                    help="Show the full Python traceback when a run fails.")
    ap.add_argument("--fromdate", type=str, help="Start date YYYY-MM-DD.")
    ap.add_argument("--todate", type=str, help="End date YYYY-MM-DD.")

    return ap.parse_args()

# -----------------------------------------------------------------------------
# Main execution entrypoint
# -----------------------------------------------------------------------------
def main(args=None):
    # Parse CLI args and config
    if args is None:
        args = parse_args()
    cfg = load_config(Path(args.config or "config.yaml"),
                      allow_missing=args.config is None)

    # Merge CLI overrides (priority over file-based config)
    if args.strategy:                cfg["strategy"] = args.strategy
    if args.strategy_class:          cfg["strategy_class"] = args.strategy_class
    if args.cash is not None:        cfg["starting_cash"] = args.cash
    if args.commission is not None:  cfg["commission"] = args.commission
    if args.s_mult is not None:      cfg["s_mult"] = args.s_mult
    if args.no_plot:                 cfg["plot"] = False
    if args.data_dir:                cfg["data_dir"] = args.data_dir
    if args.output_dir:              cfg["output_dir"] = args.output_dir
    if args.end_policy:              cfg["end_policy"] = args.end_policy
    validate_config(cfg)

    # Determine debug mode:
    # Enabled explicitly via --debug or automatically when under pytest.
    debug_flag = bool(args.debug or os.environ.get("PYTEST_CURRENT_TEST"))

    # Add project root to sys.path so that framework/ and strategies/ are importable.
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))

    # Lazy imports keep dependency failures inside the CLI error handler.
    import backtrader as bt
    from framework.plotting import save_per_series_pd
    from framework.data_loader import add_10_csv_feeds
    from framework.strategies_loader import load_strategy_class, validate_strategy_params
    from framework.analyzers import NetPnL, PDRatio, Activity, OpenOpenPnL, RealizedPnL
    from framework.broker import BT396Broker
    from framework.reporting import write_json, json_safe
    from framework.strategy_base import COMP396BrokerConfig

    # Resolve I/O directories
    data_dir = (root / cfg["data_dir"]).resolve()
    output_dir = (root / cfg["output_dir"]).resolve()
    args._error_output_dir = output_dir

    # Validate strategy selection and parameter names before loading CSVs.
    StrategyClass = load_strategy_class(cfg["strategy"], cfg["strategy_class"])
    params = parse_param_args(args.param)
    validate_strategy_params(StrategyClass, params)

    # -------------------------------------------------------------------------
    # Configure Backtrader’s Cerebro engine
    # -------------------------------------------------------------------------
    # Cerebro orchestrates the broker, strategies, data feeds, and analyzers.
    cerebro = bt.Cerebro(stdstats=False, preload=True, runonce=True)
    cerebro.setbroker(BT396Broker(s_mult=cfg["s_mult"], debug=debug_flag))
    cerebro.broker.setcash(cfg["starting_cash"])
    if cfg["commission"] and cfg["commission"] > 0:
        cerebro.broker.setcommission(commission=cfg["commission"])

    # -------------------------------------------------------------------------
    # Parse optional date filters (applied to CSV feed loading)
    # -------------------------------------------------------------------------
    fromdate = None
    todate = None
    if args.fromdate:
        try:
            fromdate = datetime.strptime(args.fromdate, "%Y-%m-%d").date()
        except ValueError:
            raise UserInputError("--fromdate must be in YYYY-MM-DD format.")
    if args.todate:
        try:
            todate = datetime.strptime(args.todate, "%Y-%m-%d").date()
        except ValueError:
            raise UserInputError("--todate must be in YYYY-MM-DD format.")
    if fromdate and todate and fromdate > todate:
        raise UserInputError("--fromdate must be on or before --todate.")

    # -------------------------------------------------------------------------
    # Add 10 CSV data feeds
    # -------------------------------------------------------------------------
    # The data loader detects OHLCV columns and applies date filtering.
    # Supply the aligned daily feeds required by the project brief.
    try:
        datas = add_10_csv_feeds(cerebro, data_dir, fromdate=fromdate, todate=todate)
    except ValueError as exc:
        raise UserInputError(f"Could not load data: {exc}") from exc

    # -------------------------------------------------------------------------
    # Validate feed-dependent strategy parameters
    # -------------------------------------------------------------------------
    # Optional classmethod: validate_parameters(params, nfeeds).
    validator = getattr(StrategyClass, "validate_parameters", None)
    if callable(validator):
        try:
            validator(params, len(datas))
        except (ValueError, TypeError) as exc:
            raise UserInputError(
                f"Invalid parameters for '{cfg['strategy']}': {exc}"
            ) from exc
    ensure_dir(output_dir)
    strategy_name = args.strategy or cfg["strategy"]

    # Display active configuration for reproducibility
    print("\n=== Backtest Configuration ===")
    print(f"Strategy: {strategy_name}")
    print("Parameters (CLI overrides):")
    if params:
        for k, v in params.items():
            print(f"  {k}: {v}")
    else:
        print("  <using strategy defaults>")
    print("================================\n")

    # -------------------------------------------------------------------------
    # Build COMP396 broker configuration object
    # -------------------------------------------------------------------------
    # This structure carries simulation settings to all strategy instances.
    # It is passed via the special '_comp396' param merged into bt.Strategy params.
    params["_comp396"] = COMP396BrokerConfig(
        s_mult=float(cfg["s_mult"]),
        end_policy=str(cfg["end_policy"]).lower(),
        output_dir=str(output_dir),
        debug=debug_flag,
    )

    if debug_flag:
        print("Debug logging ENABLED (orders, fills, slippage, trade PnL)")

    # -------------------------------------------------------------------------
    # Register strategy and analyzers with Cerebro
    # -------------------------------------------------------------------------
    cerebro.addstrategy(StrategyClass, **params)
    cerebro.addanalyzer(NetPnL, _name="netpnl")
    cerebro.addanalyzer(PDRatio, _name="pd")
    cerebro.addanalyzer(Activity, _name="activity")
    if args.diagnostics:
        cerebro.addanalyzer(OpenOpenPnL, _name="oopnl")
        cerebro.addanalyzer(RealizedPnL, _name="realpnl")

    strat = cerebro.run(maxcpus=1)[0]
    final_positions = {data._name: cerebro.broker.getposition(data).size for data in datas}
    if cfg["end_policy"] == "liquidate" and any(final_positions.values()):
        raise RuntimeError(
            f"Final liquidation failed; positions remain open: {final_positions}. "
            "No performance summary was written."
        )
    net = strat.analyzers.netpnl.get_analysis()
    pdres = strat.analyzers.pd.get_analysis()
    activity = strat.analyzers.activity.get_analysis()
    portfolio = pdres["portfolio"]
    summary = {
        "metric_version": "net_pd_v1",
        "pd_ratio": portfolio["pd_ratio"],
        "pd_status": portfolio["pd_status"],
        "net_profit": portfolio["net_profit"],
        "max_drawdown": portfolio["max_drawdown"],
        "max_drawdown_duration_bars": portfolio["max_drawdown_duration_bars"],
        "starting_cash": net["start_equity"],
        "final_equity": net["final_equity"],
        "final_value": net["final_equity"],  # compatibility for existing grading scripts
        "commission_paid": portfolio["commission"],
        "slippage_paid": portfolio["slippage"],
        "bankrupt": net["bankrupt"],
        "bankrupt_date": net["bankrupt_date"],
        "activity_pct": activity["activity_pct"],
        "valuation": "daily_close",
        "framework_version": "0.1.5",
        "execution_model": "comp396_legacy_v5_9",
        "end_policy": cfg["end_policy"],
        "liquidation_policy": "each_series_final_open" if cfg["end_policy"] == "liquidate" else None,
        "final_positions": final_positions,
        "s_mult": cfg["s_mult"],
    }
    write_json(output_dir / "run_summary.json", summary)
    write_json(output_dir / "pd_results.json", pdres)
    write_json(output_dir / "net_profit_curves.json", net)
    write_json(output_dir / "fills.json", cerebro.broker.fills)
    save_per_series_pd(pdres, output_dir)
    if cfg["plot"]:
        from framework.plotting import save_performance_plots
        save_performance_plots(net, pdres, activity, output_dir)
    if args.diagnostics:
        gross = strat.analyzers.oopnl.get_analysis()
        closed = strat.analyzers.realpnl.get_analysis()
        write_json(output_dir / "diagnostic_open_open.json", gross)
        write_json(output_dir / "diagnostic_closed_trades.json", closed)
        if cfg["plot"]:
            from framework.plotting import save_diagnostic_plot
            save_diagnostic_plot(gross, output_dir, "diagnostic_open_open.png",
                                 "Gross Open-to-Open P&L: excludes execution costs; not official PD")
            save_diagnostic_plot(closed, output_dir, "diagnostic_closed_trades.png",
                                 "Closed-trade P&L after commission: excludes custom slippage; not official PD")
    print(json.dumps(json_safe(summary), indent=2, allow_nan=False))

# -----------------------------------------------------------------------------
# Entrypoint guard
# -----------------------------------------------------------------------------
def configure_console_output() -> None:
    """Keep the console encoding; escape characters it cannot represent.

    Windows redirected stdout may use a legacy code page. A decorative
    arrow, student log message or Unicode path must not abort a backtest.
    Report files continue to be written as UTF-8.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(errors="backslashreplace")


def run_cli() -> int:
    configure_console_output()
    args = parse_args()
    try:
        main(args)
        return 0
    except Exception as exc:
        if isinstance(exc, UserInputError):
            label, status = "Input error", 2
        elif isinstance(exc, StrategySetupError):
            label, status = "Strategy setup error", 1
        else:
            label, status = "Run failed", 1
        print(f"\nBT396 {label}: {exc}", file=sys.stderr)
        # Give an immediate source location, including for chained exceptions.
        original = exc
        while original.__cause__ is not None:
            original = original.__cause__
        frames = traceback.extract_tb(original.__traceback__)
        if frames and not isinstance(exc, UserInputError):
            frame = frames[-1]
            print(f"Location: {frame.filename}:{frame.lineno} in {frame.name}", file=sys.stderr)
        report = traceback.format_exc()
        output_dir = getattr(args, "_error_output_dir", Path(__file__).resolve().parent / "output")
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            log_path = output_dir / "last_error.log"
            log_path.write_text(report, encoding="utf-8")
            print(f"Full error details: {log_path}", file=sys.stderr)
        except OSError as log_error:
            print(f"Could not save error details: {log_error}", file=sys.stderr)
        if args.traceback:
            print(report, file=sys.stderr, end="")
        else:
            print("Add --traceback to show the full traceback.", file=sys.stderr)
        return status


if __name__ == "__main__":
    configure_console_output()
    # If run without arguments, print framework version and exit
    if len(sys.argv) <= 1:
        from framework import __version__ as BT396_VERSION, __release_date__ as BT396_DATE
        print(f"{BT396_VERSION} ({BT396_DATE})")
    else:
        sys.exit(run_cli())
