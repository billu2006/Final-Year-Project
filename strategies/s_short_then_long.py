# Filename: strategies/s_short_then_long.py
# Name: s_short_then_long
# Type: single series strategy
# Summary:
#
# Description:
#   Single-series two-phase demo: short on day one by fixed notional amount,
#     then target a long holding using account wealth less the cash buffer
#
#
# Single-series “short then long” strategy
# -----------------------------------------------------
# - Day 1: SHORT the instrument with notional exposure = leverage.
# - After the short fills: cover it and target a long holding using account wealth less cash_buffer.
# - If wealth does not exceed cash_buffer, the second target is flat.
# - Then hold until liquidation.
#
# Example usage: python main.py --strategy s_short_then_long


import math
import backtrader as bt


class TeamStrategy(bt.Strategy):
    """Single-series two-phase demo: short on day one by fixed notional amount,
    then target a long holding using account wealth less the cash buffer (BT396-safe version)."""

    params = dict(
        leverage=8_000_000,    # notional to short on Day 1 (per feed)
        cash_buffer=1_000_000, # reserve £1M of wealth; a smaller reserve permits a long
        printlog=False,
    )

    def __init__(self):
        if not math.isfinite(float(self.p.leverage)) or float(self.p.leverage) <= 0:
            raise ValueError("leverage must be finite and positive.")
        if not math.isfinite(float(self.p.cash_buffer)) or float(self.p.cash_buffer) < 0:
            raise ValueError("cash_buffer must be finite and non-negative.")
        # Track progress per feed
        self._shorted = {d: False for d in self.datas}
        self._longed  = {d: False for d in self.datas}

    def log(self, txt, dt=None):
        if self.p.printlog:
            dt = dt or (self.datas[0].datetime.date(0) if len(self.datas[0]) else "SETUP")
            print(f"{dt} {txt}")

    def next(self):
        d = self.datas[0]  # Single-series example: trade only the first feed.
        if not len(d) or d.datetime[0] != self.datetime[0]:
            return
        if getattr(self, "_pending", False):
            return
        close = float(d.close[0])
        if close <= 0:
            return
        current = self.getposition(d).size
        if not self._shorted[d]:
            target = -float(self.p.leverage) / close
            self._phase = "short"
        elif not self._longed[d]:
            # Account wealth sets the desired long holding. Delta also covers
            # the existing short; cash proceeds from shorting are not profit.
            budget = max(0.0, self.broker.getvalue() - float(self.p.cash_buffer))
            target = budget / close
            self._phase = "long"
        else:
            return
        delta = target - current
        if not delta:
            self._longed[d] = True
            return
        if self.overspend_guard([(d, delta)]):
            self._pending = True
            self.place_market(d, delta)
            self.log(f"{d._name}: target {target:+.2f}, adjustment {delta:+.2f}")

    def notify_order(self, order):
        pending = getattr(self, "_pending", None)
        if not pending or order.data is not self.datas[0]:
            return
        if order.status == order.Completed:
            if self._phase == "short":
                self._shorted[order.data] = True
            else:
                self._longed[order.data] = True
            self._pending = None
        elif order.status in (order.Canceled, order.Margin, order.Rejected, order.Expired):
            self._pending = None
