# Filename: strategies/bbands_holding_period.py
# Name: bbands_holding_period
# Type: portfolio strategy
# Summary: Bollinger Bands strategy that opens positions on band breaches
#          and closes on a neutral signal or after a maximum holding period.
#
# Description:
# Bollinger Bands contrarian strategy with a per-series max holding period.
# - Trades ONLY the 1-based series in params.series
# - If Close < lower band => LONG; if Close > upper band => SHORT; else => FLAT.
# - Tracks how many bars we’ve been in a trade and exits when the count hits holdPeriod.
#
# Params
#   lookback:    int, Bollinger window
#   sdParam:     float, stddev multiplier
#   holdPeriod:  int, max number of bars to remain in a position
#   series:      list[int], 1-based series indices to trade; default = all feeds
#   posSizes:    list[float], per-feed position sizes (len == n_feeds)
#   default_size:float, used if posSizes is None
#   printlog:    bool, verbose per-bar logging
#
# Notes
# - Uses order_target_size(...) → market orders at next bar with framework slippage.
# - Holding age starts at a confirmed fill; rejected entries do not start a clock.
#
# example usage: python main.py --strategy bbands_holding_period --param series=[1,2] --param holdPeriod=5 --debug

import math
import backtrader as bt


class TeamStrategy(bt.Strategy):
    """Bollinger Bands strategy that opens positions on band breaches and closes on a neutral signal or after a maximum holding period."""
    params = dict(
        lookback=20,
        sdParam=2.0,
        holdPeriod=5,
        series=None,          # 1-based list; None = all series
        posSizes=None,        # len == n_feeds; else fallback to default_size
        default_size=1.0,
        printlog=False,
    )

    def __init__(self):
        if not math.isfinite(float(self.p.default_size)) or float(self.p.default_size) <= 0:
            raise ValueError("default_size must be finite and positive.")
        if not math.isfinite(float(self.p.sdParam)) or float(self.p.sdParam) <= 0:
            raise ValueError("sdParam must be finite and positive.")
        if type(self.p.lookback) is not int or self.p.lookback < 2:
            raise ValueError("lookback must be an integer >= 2.")
        if type(self.p.holdPeriod) is not int or self.p.holdPeriod < 1:
            raise ValueError("holdPeriod must be an integer >= 1.")
        self.datas_list = list(self.datas)
        nfeeds = len(self.datas_list)
        if nfeeds == 0:
            raise ValueError("No data feeds. Use --data-dir with at least 10 CSV files.")

        # Convert 1-based series → 0-based indices
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

        # Position sizes (per feed)
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

        # Bollinger indicators for each feed (we’ll consult only selected ones)
        self.bbands = []
        for d in self.datas_list:
            bb = bt.indicators.BollingerBands(
                d.close, period=int(self.p.lookback), devfactor=float(self.p.sdParam)
            )
            self.bbands.append(bb)

        self.entry_bar = {}

    # Optional: echo params at start
    def start(self):
        if self.p.printlog:
            print(f"[{self.__class__.__name__}] parameters:")
            for k, v in self.p._getitems():
                print(f"  {k}: {v}")

    def log(self, txt, dt=None):
        if self.p.printlog:
            dt = dt or (self.datas[0].datetime.date(0) if len(self.datas[0]) else "SETUP")
            print(f"{str(dt)} {txt}")

    def next(self):
        # Need enough history for Bollinger window
        if len(self) <= int(self.p.lookback):
            return

        for i in self.series_idx:
            d = self.datas_list[i]
            if not len(d) or d.datetime[0] != self.datetime[0]:
                continue
            bb = self.bbands[i]

            close = float(d.close[0])
            up = float(bb.lines.top[0])
            dn = float(bb.lines.bot[0])
            size_base = self.pos_sizes[i]

            # Raw direction: +1 long, -1 short, 0 flat
            dir_signal = 0
            if close < dn:
                dir_signal = +1
            elif close > up:
                dir_signal = -1
            else:
                dir_signal = 0

            # Count observed bars from the actual fill, rather than submission.
            position = self.getposition(d).size
            entered = self.entry_bar.get(d)
            age = len(d) - entered + 1 if position and entered is not None else 0
            if position and age >= int(self.p.holdPeriod):
                dir_signal = 0

            # Target position for this instrument
            target = float(dir_signal) * float(size_base)
            curr = self.getposition(d).size
            delta = float(target) - float(curr)
            if abs(delta) > 0:
                # (optional) single-instrument overspend check
                if self.overspend_guard([(d, delta)]):
                    self.place_market(d, delta)  # goes through COMP396 buffer + flush correctly
                else:
                    self.log(f"OVRSPEND guard tripped on {d._name}; skipping")

            if self.p.printlog:
                self.log(
                    f"[data[{i}]] close={close:.4f} dn={dn:.4f} up={up:.4f} "
                    f"dir={dir_signal:+d} holding_age={age:d} target={target:.2f}"
                )

    def notify_order(self, order):
        if order.status != order.Completed:
            return
        before = order.executed.psize - order.executed.size
        after = order.executed.psize
        if after == 0:
            self.entry_bar.pop(order.data, None)
        elif before == 0 or before * after < 0:
            self.entry_bar[order.data] = len(order.data)
