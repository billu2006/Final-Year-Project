# Filename: strategies/p_bbands_trend_following.py
# Name: p_bbands_trend_following
# Type: Portfolio strategy
# Summary:
#  Portfolio Bollinger Bands breakout (trend-following) strategy that goes
#     long above the upper band and short below the lower band.
#
# params: see below
#
# example usage: python main.py --strategy p_bbands_trend_following

import math
import backtrader as bt


class TeamStrategy(bt.Strategy):
    """Portfolio Bollinger Bands breakout (trend-following) strategy that goes
    long above the upper band and short below the lower band.
    All orders go through COMP396Base-safe methods (overspend_guard + place_market).
    """

    params = dict(
        lookback=20,           # Bollinger window length
        sdParam=2.0,           # std dev multiplier
        series=None,           # 1-based feed indices to trade; default = all
        posSizes=None,         # per-feed target sizes
        default_size=1.0,      # used if posSizes is None
        exit_on_mid=False,     # if True, exit to flat when crossing the middle band
        printlog=False,
    )

    def __init__(self):
        if not math.isfinite(float(self.p.default_size)) or float(self.p.default_size) <= 0:
            raise ValueError("default_size must be finite and positive.")
        if not math.isfinite(float(self.p.sdParam)) or float(self.p.sdParam) <= 0:
            raise ValueError("sdParam must be finite and positive.")
        if type(self.p.lookback) is not int or self.p.lookback < 2:
            raise ValueError("lookback must be an integer >= 2.")
        self.datas_list = list(self.datas)
        nfeeds = len(self.datas_list)
        if nfeeds == 0:
            raise ValueError("No data feeds. Use --data-dir with at least 10 CSV files.")

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

        # Per-feed position sizes
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

        # Create Bollinger bands per feed
        self.bbands = []
        for d in self.datas_list:
            bb = bt.indicators.BollingerBands(
                d.close, period=int(self.p.lookback), devfactor=float(self.p.sdParam)
            )
            self.bbands.append(bb)

    def log(self, txt, dt=None):
        if self.p.printlog:
            dt = dt or (self.datas[0].datetime.date(0) if len(self.datas[0]) else "SETUP")
            print(f"{str(dt)} {txt}")

    def next(self):
        # Wait until Bollinger bands have enough history
        if len(self) <= int(self.p.lookback):
            return

        intents = []  # collect all (data, delta) pairs for overspend_guard

        for i in self.series_idx:
            d = self.datas_list[i]
            if not len(d) or d.datetime[0] != self.datetime[0]:
                continue
            bb = self.bbands[i]

            close = float(d.close[0])
            up = float(bb.lines.top[0])
            mid = float(bb.lines.mid[0])
            dn = float(bb.lines.bot[0])

            size_base = self.pos_sizes[i]
            current = self.getposition(d).size
            target = None  # None → hold

            if close > up:
                target = +size_base
            elif close < dn:
                target = -size_base
            else:
                if self.p.exit_on_mid:
                    prev_close = float(d.close[-1]) if len(d) > 1 else close
                    prev_mid = float(bb.lines.mid[-1]) if len(d) > 1 else mid
                    crossed_mid = ((current > 0 and prev_close >= prev_mid and close < mid)
                                   or (current < 0 and prev_close <= prev_mid and close > mid))
                    if crossed_mid:
                        target = 0.0

            # If no change in position target, skip
            if target is None or abs(target - current) < 1e-8:
                continue

            delta = target - current
            intents.append((d, delta))

            if self.p.printlog:
                self.log(
                    f"[data[{i}]={d._name}] close={close:.4f} dn={dn:.4f} mid={mid:.4f} up={up:.4f} "
                    f"→ target={target:.2f} (delta={delta:+.2f})"
                )

        # Pre-check all orders for overspend
        if intents and not self.overspend_guard(intents):
            self.log("OVRSPEND: skipping all proposed market orders today")
            return

        # Submit buffered market orders (executed next open)
        for d, delta in intents:
            self.place_market(d, delta)
