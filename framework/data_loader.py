# framework/data_loader.py
# loads the data feeds

from pathlib import Path
import glob
import pandas as pd
import backtrader as bt

# Accept common column aliases (case-insensitive)
ALIASES = {
    "date": {"date", "datetime", "timestamp", "time", "index", "unnamed: 0"},
    "open": {"open", "o"},
    "high": {"high", "h"},
    "low": {"low", "l"},
    "close": {"close", "adjclose", "adj_close", "c"},
    "volume": {"volume", "vol", "v", "turnover"},
}

def _find_col(cols, targets):
    # cols: list of column names; targets: set of acceptable names (lowercased)
    low = {c.lower(): c for c in cols}
    for t in targets:
        if t in low:
            return low[t]
    return None

def _read_csv_safely(path: Path) -> pd.DataFrame:
    """
    Read a CSV with robust defaults:
    - auto-detect separator,
    - parse date/datetime,
    - find OHLCV columns by common aliases,
    - drop rows with missing required fields,
    - ensure Date is monotonic increasing and set as index.
    """
    # Auto-detect separator with python engine
    try:
        df = pd.read_csv(path, engine="python", sep=None)
    except Exception as e:
        raise ValueError(f"Failed to read CSV {path}: {e}")

    if df.empty:
        raise ValueError(f"CSV {path} is empty.")

    # Normalize column names: keep original, but search case-insensitively
    cols = list(df.columns)

    c_date = _find_col(cols, ALIASES["date"])
    c_open = _find_col(cols, ALIASES["open"])
    c_high = _find_col(cols, ALIASES["high"])
    c_low  = _find_col(cols, ALIASES["low"])
    c_close= _find_col(cols, ALIASES["close"])
    c_vol  = _find_col(cols, ALIASES["volume"])

    missing = [n for n,c in [("Date", c_date),("Open", c_open),("High", c_high),
                             ("Low", c_low),("Close", c_close),("Volume", c_vol)] if c is None]
    if missing:
        raise ValueError(
            f"{path.name}: could not find required columns {missing}. "
            f"Found columns: {cols}"
        )

    # Parse dates
    df[c_date] = pd.to_datetime(df[c_date], errors="coerce", utc=False)
    df = df.dropna(subset=[c_date, c_open, c_high, c_low, c_close])  # volume can be NaN -> fill with 0
    if c_vol is None:
        df["__Volume__"] = 0
        c_vol = "__Volume__"

    # Keep only needed columns in expected names
    out = df[[c_date, c_open, c_high, c_low, c_close, c_vol]].copy()
    out.columns = ["Date", "Open", "High", "Low", "Close", "Volume"]

    # Clean types
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["Open", "High", "Low", "Close"])  # allow Volume NaN -> 0
    out["Volume"] = out["Volume"].fillna(0)

    # Sort & de-dup
    out = out.sort_values("Date").drop_duplicates(subset=["Date"])
    out = out.set_index("Date")

    # Ensure daily frequency (Backtrader is tolerant; this just documents intent)
    return out

def _mk_pandas_feed(df: pd.DataFrame, name: str):
    # Let Backtrader read OHLCV from dataframe index/columns
    data = bt.feeds.PandasData(
        dataname=df,
        datetime=None,  # index is datetime
        open="Open",
        high="High",
        low="Low",
        close="Close",
        volume="Volume",
        openinterest=-1,
        timeframe=bt.TimeFrame.Days,
        compression=1,
    )
    data._name = name
    return data

def add_10_csv_feeds(cerebro, data_dir: Path, fromdate=None, todate=None):
    csvs = sorted(glob.glob(str(data_dir / "*.csv")))
    if len(csvs) < 10:
        raise ValueError(f"Expected at least 10 CSV files in {data_dir}, found {len(csvs)}.")
    datas = []
    start_dates = []
    end_dates = []

    for i, fp in enumerate(csvs[:10]):
        df = _read_csv_safely(Path(fp))

        # Apply date filtering if provided
        if fromdate or todate:
            mask = pd.Series(True, index=df.index)
            if fromdate:
                mask &= df.index.date >= fromdate
            if todate:
                mask &= df.index.date <= todate
            df = df.loc[mask]
            if df.empty:
                raise ValueError(f"{Path(fp).name}: No data in selected date range.")
        # Record available date range
        start_dates.append(df.index[0].date())
        end_dates.append(df.index[-1].date())

        print(f"Loaded {Path(fp).name:<20} | {df.index[0].date()} → {df.index[-1].date()} "
              f"({len(df)} bars)")
        feed = _mk_pandas_feed(df, name=f"series_{i + 1}")
        cerebro.adddata(feed)
        datas.append(feed)

    # --- Global overlap range summary ---
    global_start = max(start_dates)
    global_end = min(end_dates)
    print("\n=== Data Range Summary ===")
    print(f"Earliest CSV start date : {min(start_dates)}")
    print(f"Latest CSV end date     : {max(end_dates)}")
    print(f"Common overlap range    : {global_start} → {global_end}")
    if fromdate or todate:
        print(f"User-specified filter   : {fromdate or '-∞'} → {todate or '+∞'}")
    print("===========================\n")

    return datas
