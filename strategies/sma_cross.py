# Filename: strategies/sma_cross.py
# Name: sma_cross
# Type: strategy
# Summary:
#   Simple SMA crossover strategy.
#
# Description:
#
# Simple moving average crossover strategy
# -----------------------------------------------------
# - Enters long when fast SMA crosses above slow SMA.
# - Exits (sells) when fast SMA crosses below slow SMA.
# - All orders route through COMP396Base.place_market() for
#   next-open buffered fills with slippage.
# - Optional overspend_guard estimates affordability; the broker enforces actual cash limits.

import math
import backtrader as bt


class TeamStrategy(bt.Strategy):
    """Simple SMA crossover strategy using BT396-safe order handling."""

    params = dict(
        fast=10,           # fast SMA period
        slow=30,           # slow SMA period
        stake=1.0,         # position size per trade
        precheck=True,     # run overspend_guard before entering
        printlog=False,    # verbose diagnostics
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
        sma_fast = bt.indicators.SMA(self.datas[0].close, period=int(self.p.fast))
        sma_slow = bt.indicators.SMA(self.datas[0].close, period=int(self.p.slow))
        self.crossover = bt.indicators.CrossOver(sma_fast, sma_slow)

    # --- Logging helper -----------------------------------------------------
    def log(self, txt, dt=None):
        if self.p.printlog:
            dt = dt or (self.datas[0].datetime.date(0) if len(self.datas[0]) else "SETUP")
            print(f"{dt} {txt}")

    # --- Core trading logic -------------------------------------------------
    def next(self):
        d = self.datas[0]

        # BUY signal: fast crosses above slow
        if not self.position and self.crossover > 0:
            size = float(self.p.stake)
            intents = [(d, size)]
            if self.p.precheck and not self.overspend_guard(intents):
                self.log("OVRSPEND: skipping BUY signal")
                return
            self.place_market(d, size)
            self.log(f"BUY signal — placing market order size={size:+.2f}")

        # SELL signal: fast crosses below slow
        elif self.position and self.crossover < 0:
            size = -float(self.getposition(d).size)
            intents = [(d, size)]
            if self.p.precheck and not self.overspend_guard(intents):
                self.log("OVRSPEND: skipping SELL signal")
                return
            self.place_market(d, size)
            self.log(f"SELL signal — placing market order size={size:+.2f}")

    # --- Order notifications ------------------------------------------------
    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return

        d = order.data
        if order.status == order.Completed:
            side = "BUY" if order.isbuy() else "SELL"
            self.log(
                f"[{d._name}] {side} filled "
                f"@{order.executed.price:.4f} "
                f"size={order.executed.size:+.2f} "
                f"value={order.executed.value:.2f}"
            )
        elif order.status in (order.Canceled, order.Margin, order.Rejected):
            self.log(f"[{d._name}] ORDER {order.getstatusname().upper()}")
