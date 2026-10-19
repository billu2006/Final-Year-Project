# Filename: strategies/condpr.py
# Name: Conditional-Probability Direction Strategy
# Type: strategy
# Summary:
#
# Description:
# - Uses the completed day k move with response_to_up/response_to_dn.
# - Submits one net target adjustment for the next open.
# - A zero response requests a flat position; repeated targets can persist.
#
# Example usage:
# python main.py --strategy condpr \
#   --param response_to_up=[1,1,1,1,1,-1,-1,-1,-1,-1] \
#   --param response_to_dn=[-1,-1,-1,-1,-1,1,1,1,1,1] \
#   --param printlog=True \
#   --data-dir ./DATA/PART1
#
#

import math
import backtrader as bt


class TeamStrategy(bt.Strategy):
    # Conditional-probability direction strategy (BT396-safe, fixed timing).""

    params = dict(
        response_to_up=None,
        response_to_dn=None,
        stake_policy="max_over_close",  # "fixed" or "max_over_close"
        fixed_stake=1.0,
        printlog=False,
    )

    def __init__(self):
        if not math.isfinite(float(self.p.fixed_stake)) or float(self.p.fixed_stake) <= 0:
            raise ValueError("fixed_stake must be finite and positive.")
        if self.p.stake_policy not in ('fixed', 'max_over_close'):
            raise ValueError("Invalid stake_policy.")

    def log(self, txt):
        if self.p.printlog and len(self.datas) > 0:
            dt = self.datas[0].datetime.date(0) if len(self.datas[0]) else "SETUP"
            print(f"{dt} | {txt}")

    def start(self):
        n = len(self.datas)
        if n == 0:
            raise ValueError("No data feeds loaded for condpr strategy.")

        # Ensure response arrays exist and are correct length
        if self.p.response_to_up is None:
            self.p.response_to_up = [0] * n
        if self.p.response_to_dn is None:
            self.p.response_to_dn = [0] * n
        if len(self.p.response_to_up) < n:
            self.p.response_to_up = list(self.p.response_to_up) + [0] * (n - len(self.p.response_to_up))
        if len(self.p.response_to_dn) < n:
            self.p.response_to_dn = list(self.p.response_to_dn) + [0] * (n - len(self.p.response_to_dn))


        self.log(f"Initialised condpr strategy with {n} feeds.")

    def _stake(self, d):
        if self.p.stake_policy == "fixed":
            return float(self.p.fixed_stake)
        close_px = float(d.close[0])
        if close_px <= 0:
            return 0.0
        closes_now = [float(di.close[0]) for di in self.datas if len(di)]
        return max(closes_now) / close_px

    def next(self):
        # Day k's completed move chooses a target for the open on k+1.
        # One net adjustment per series, including closing a zero target.
        for i, d in enumerate(self.datas):
            if not len(d) or d.datetime[0] != self.datetime[0]:
                continue
            if not len(d):
                continue
            went_up = float(d.close[0]) > float(d.open[0])
            response = self.p.response_to_up[i] if went_up else self.p.response_to_dn[i]
            target = self._stake(d) * response
            delta = target - self.getposition(d).size
            if delta:
                self.place_market(d, delta)
                self.log(f"{d._name} target={target:+.2f}, order={delta:+.2f}")

    def notify_order(self, order):
        if order.status == order.Completed:
            side = "BUY" if order.isbuy() else "SELL"
            self.log(
                f"{getattr(order.data, '_name', 'series')} "
                f"{side} filled size={order.executed.size:+.2f} @ {order.executed.price:.2f}"
            )
        elif order.status in (order.Canceled, order.Margin, order.Rejected):
            self.log(
                f"{getattr(order.data, '_name', 'series')} "
                f"ORDER {order.getstatusname().upper()}"
            )
