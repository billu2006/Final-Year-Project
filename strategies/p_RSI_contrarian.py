# Filename: strategies/p_RSI_contrarian.py
# Name: p_RSI_contrarian
# Type: Portfolio strategy
# Summary: Portfolio contrarian strategy that targets long when RSI < 50−threshold
#     and short when RSI > 50+threshold on selected series
#
#
# Description:
# - Goes long when RSI < 50 − threshold, short when RSI > 50 + threshold.
# - Trades only selected feeds (1-based indices).
#
# Example usage: python main.py --strategy p_RSI_contrarian --param series=[1,3,5,7,9]

import math
import backtrader as bt


class TeamStrategy(bt.Strategy):
    """Portfolio contrarian strategy that targets long when RSI < 50−threshold
    and short when RSI > 50+threshold on selected series (BT396-safe)."""

    params = dict(
        lookback=14,          # RSI window
        threshold=5.0,        # 0..50 band around 50
        series=None,          # 1-based feed indices to trade; default = all
        posSizes=None,        # per-feed sizes
        default_size=1.0,     # fallback
        printlog=False,
    )

    def __init__(self):
        if not math.isfinite(float(self.p.default_size)) or float(self.p.default_size) <= 0:
            raise ValueError("default_size must be finite and positive.")
        if type(self.p.lookback) is not int or self.p.lookback < 2:
            raise ValueError("lookback must be an integer >= 2.")
        self.datas_list = list(self.datas)
        nfeeds = len(self.datas_list)
        if nfeeds == 0:
            raise ValueError("No data feeds. Use --data-dir with at least 10 CSV files.")

        # Validate threshold range
        if not (0 <= float(self.p.threshold) <= 50):
            raise ValueError("threshold must be between 0 and 50.")

        # Convert 1-based to 0-based indices
        if self.p.series is None:
            self.series_idx = list(range(nfeeds))
        else:
            if (not isinstance(self.p.series, (list, tuple)) or not self.p.series
                    or any(type(i) is not int or not 1 <= i <= nfeeds for i in self.p.series)
                    or len(set(self.p.series)) != len(self.p.series)):
                raise ValueError("series must contain distinct valid 1-based feed numbers.")
            self.series_idx = [i - 1 for i in self.p.series]
            if not self.series_idx:
                raise ValueError("params.series produced no valid indices for available feeds.")

        # Per-feed target sizes
        if self.p.posSizes is None:
            self.pos_sizes = [float(self.p.default_size)] * nfeeds
        else:
            if len(self.p.posSizes) != nfeeds:
                raise ValueError(
                    f"posSizes length {len(self.p.posSizes)} must match number of feeds {nfeeds}."
                )
            self.pos_sizes = [float(x) for x in self.p.posSizes]
            if any(not math.isfinite(x) for x in self.pos_sizes):
                raise ValueError("Position sizes must be finite.")

        # Build RSI indicators
        self.rsi = [bt.indicators.RSI(d.close, period=int(self.p.lookback), safediv=True) for d in self.datas_list]

    def log(self, txt, dt=None):
        if self.p.printlog:
            dt = dt or (self.datas[0].datetime.date(0) if len(self.datas[0]) else "SETUP")
            print(f"{dt} {txt}")

    def next(self):
        # Wait until enough bars for RSI
        if len(self) < int(self.p.lookback) + 2:
            return

        up_lvl = 50.0 + float(self.p.threshold)
        dn_lvl = 50.0 - float(self.p.threshold)

        intents = []  # collect (data, delta) for overspend_guard

        # ---  Determine targets per feed ---
        for i in self.series_idx:
            d = self.datas_list[i]
            if not len(d) or d.datetime[0] != self.datetime[0]:
                continue
            r = float(self.rsi[i][0])

            # Contrarian signal: +1 long, -1 short, 0 flat
            if r > up_lvl:
                dir_signal = -1
            elif r < dn_lvl:
                dir_signal = +1
            else:
                dir_signal = 0

            target = dir_signal * self.pos_sizes[i]
            current = self.getposition(d).size
            delta = target - current

            if abs(delta) > 1e-8:
                intents.append((d, delta))

            if self.p.printlog:
                self.log(
                    f"[data[{i}]={d._name}] RSI={r:.2f} "
                    f"(>{up_lvl:.2f} short / <{dn_lvl:.2f} long) "
                    f"target={target:+.2f} current={current:+.2f} delta={delta:+.2f}"
                )

        # --- Run overspend guard before sending any orders ---
        if intents and not self.overspend_guard(intents):
            self.log("OVRSPEND: skipping all proposed market orders today")
            return

        # --- Queue safe market orders for next-open fill ---
        for d, delta in intents:
            self.place_market(d, delta)
