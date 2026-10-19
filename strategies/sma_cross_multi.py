# Filename: strategies/sma_cross_multi.py
# Name: sma_cross_multi
# Type: strategy
# Summary:
#   Simple SMA crossover strategy on all user-selected series.
#
# Description:
# - Set series to a list or tuple of integers from 1 to 10.
#   For example, series=(1, 3, 7) trades series 1, 3 and 7.
# - Supports feed names series_1 ... series_10 and 01 ... 10.
# - Each selected series has its own crossover and position.
# - Enters long when fast SMA crosses above slow SMA.
# - Exits when fast SMA crosses below slow SMA.
# - Uses the same fast, slow and stake settings for every series.
# - Orders use BT396's place_market() helper for next-open fills.
# - Optional overspend_guard checks the whole day's proposed batch.
#   If it fails, the entire batch is skipped. The broker enforces
#   actual cash limits when orders execute.

import math
import backtrader as bt


class TeamStrategy(bt.Strategy):
    """SMA crossovers on selected series using BT396-safe orders."""

    params = dict(
        series=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10),  # series numbers to trade
        fast=10,          # fast SMA period for every selected series
        slow=30,          # slow SMA period for every selected series
        stake=1.0,        # position size per series, not a portfolio total
        precheck=True,    # check affordability of the whole order batch
        printlog=False,   # verbose diagnostics
    )

    def __init__(self):
        if not math.isfinite(float(self.p.stake)) or float(self.p.stake) <= 0:
            raise ValueError("stake must be finite and positive.")
        if type(self.p.fast) is not int or self.p.fast < 1:
            raise ValueError("fast must be an integer >= 1.")
        if type(self.p.slow) is not int or self.p.slow < 1:
            raise ValueError("slow must be an integer >= 1.")
        if self.p.fast >= self.p.slow:
            raise ValueError("fast must be less than slow.")

        numbers = self.p.series
        if not isinstance(numbers, (list, tuple)) or not numbers:
            raise ValueError("series must be a non-empty list or tuple, e.g. (1, 3, 7).")
        if any(type(n) is not int or not 1 <= n <= 10 for n in numbers):
            raise ValueError("Each series number must be an integer from 1 to 10.")
        if len(set(numbers)) != len(numbers):
            raise ValueError("series must not contain duplicate numbers.")

        # Resolve numbers to feed names, independently of loading order.
        self.trade_datas = []
        self.crossovers = {}
        self.last_seen = {}
        for number in numbers:
            names = (f"series_{number}", f"{number:02d}")
            matches = [d for d in self.datas if d._name in names]
            if len(matches) != 1:
                available = ", ".join(repr(d._name) for d in self.datas)
                raise ValueError(
                    f"Series {number} requires exactly one loaded feed named "
                    f"{names[0]!r} or {names[1]!r}. "
                    f"Available series: {available}"
                )
            d = matches[0]
            self.trade_datas.append(d)
            sma_fast = bt.indicators.SMA(d.close, period=self.p.fast)
            sma_slow = bt.indicators.SMA(d.close, period=self.p.slow)
            self.crossovers[d] = bt.indicators.CrossOver(sma_fast, sma_slow)
            self.last_seen[d] = 0

    # --- Logging helper -----------------------------------------------------
    # Use a distinct name so BT396's own log() cannot shadow this helper.
    def log_sma(self, txt, dt=None, data=None):
        if self.p.printlog:
            d = data if data is not None else self.trade_datas[0]
            dt = dt or (d.datetime.date(0) if len(d) else "SETUP")
            print(f"{dt} {txt}")

    # --- Core trading logic -------------------------------------------------
    def next(self):
        exits = []
        entries = []

        for d in self.trade_datas:
            # Do not repeat a signal if this feed has not advanced.
            if len(d) <= self.last_seen[d]:
                continue
            self.last_seen[d] = len(d)

            position = self.getposition(d)
            crossover = self.crossovers[d][0]
            if not position and crossover > 0:
                entries.append((d, float(self.p.stake)))
            elif position and crossover < 0:
                exits.append((d, -float(position.size)))

        # Submit exits first; all series share the same broker cash balance.
        intents = exits + entries
        if not intents:
            return
        if self.p.precheck and not self.overspend_guard(intents):
            names = ", ".join(d._name for d, size in intents)
            self.log_sma(f"OVRSPEND: skipping order batch for series {names}")
            return

        for d, size in intents:
            self.place_market(d, size)
            side = "BUY" if size > 0 else "SELL"
            self.log_sma(
                f"[{d._name}] {side} signal — placing market order size={size:+.2f}",
                data=d,
            )

    # --- Order notifications ------------------------------------------------
    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return

        d = order.data
        if order.status == order.Completed:
            side = "BUY" if order.isbuy() else "SELL"
            self.log_sma(
                f"[{d._name}] {side} filled "
                f"@{order.executed.price:.4f} "
                f"size={order.executed.size:+.2f} "
                f"value={order.executed.value:.2f}",
                data=d,
            )
        elif order.status in (order.Canceled, order.Margin, order.Rejected):
            self.log_sma(f"[{d._name}] ORDER {order.getstatusname().upper()}", data=d)
