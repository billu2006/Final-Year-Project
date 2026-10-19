# Filename: strategies/copycat.py
# Name: copycat
# Type: strategy
# Summary: Copies the completed day’s price direction by targeting a
#   fixed long position if the close exceeded the open, otherwise a
#   fixed short position, with adjustments executed at the next market open.
#   It applies its trading rule to all ten series, using the same stake for each
#
# Description:
#  For each instrument (data feed):
#       - If the completed current bar's Close > the completed current bar's Open: target position = +stake
#       - Else:                                    target position = -stake
#     We place a single market order for the delta so the next-open fill
#     adjusts the position to the desired target.
#
# example : python main.py --strategy copycat --param stake=100 --param printlog=true

import math
import backtrader as bt

class TeamStrategy(bt.Strategy):
    """
    For each instrument (data feed):
      - If the completed current bar's Close > the completed current bar's Open: target position = +stake
      - Else:                                      target position = -stake
    We place a single market order for the delta so the next-open fill
    adjusts the position to the desired target.

    """
    params = dict(
        stake=1,          # size (+/-) to target per instrument
        printlog=False,
    )

    def __init__(self):
        if not math.isfinite(float(self.p.stake)) or float(self.p.stake) <= 0:
            raise ValueError("stake must be finite and positive.")

    def log(self, txt):
        if self.p.printlog:
            dt = self.datas[0].datetime.date(0) if len(self.datas[0]) else "SETUP"
            print(f"{dt} | {txt}")

    def next(self):
        # Build intents across all series first -> single overspend check
        intents = []
        deltas = []  # (data, delta) we will place if guard passes

        for d in self.datas:
            if not len(d) or d.datetime[0] != self.datetime[0]:
                continue
            # Compare the latest completed bar; fills use the following open.
            if len(d) < 1:
                continue

            y_open  = float(d.open[0])
            y_close = float(d.close[0])

            target = self.p.stake if (y_close > y_open) else -self.p.stake

            pos = self.getposition(d)
            current = pos.size if pos else 0.0
            delta = target - current

            if abs(delta) > 0:  # only if we need to adjust
                deltas.append((d, delta))
                # For the guard: buys are positive, sells negative
                intents.append((d, delta))

        # Optional estimate: strategy may choose not to submit a costly basket.
        # The broker checks all actual market and limit fills together next day.
        if intents and not self.overspend_guard(intents):
            self.log("OVRSPEND: skipping all proposed market orders today")
            return

        # Place the queued market orders
        for d, delta in deltas:
            self.place_market(d, delta)
            side = "BUY" if delta > 0 else "SELL"
            self.log(f"{side} {abs(delta):.0f} → target {self.getposition(d).size + delta} on {getattr(d, '_name', 'data')}")

    def notify_order(self, order):
        if order.status == order.Completed:
            act = "BUY" if order.isbuy() else "SELL"
            self.log(f"{act} filled @ {order.executed.price:.4f} size {order.executed.size:.0f}")
