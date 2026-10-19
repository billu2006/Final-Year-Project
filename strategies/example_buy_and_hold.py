# Filename: strategies/example_buy_and_hold.py
# Name: example_buy_and_hold
# Type: strategy
# Summary: buy-and-hold a single instrument
#
# Description:
#   buy-and-hold a single instrument (data0, i.e. series1).
# - Buys once (size units) after the BT396 engine runs.
#
# Example usage: python main.py --strategy example_buy_and_hold --param size=100

import math
import backtrader as bt


class ExampleBuyAndHold(bt.Strategy):
    """Wrapped example strategy that buys a single instrument once and then holds it for the rest of the backtest."""
    params = dict(
        size=1,        # default units to buy on first opportunity
        printlog=True, # set False to silence logs
    )

    def __init__(self):
        if not math.isfinite(float(self.p.size)) or float(self.p.size) <= 0:
            raise ValueError("size must be finite and positive.")
        self._did_buy = False
        self._entry = None

    # Optional banner
    def start(self):
        if getattr(self.p, "printlog", False):
            names = [d._name for d in self.datas]
            dt0 = self.datas[0].datetime.date(0) if len(self.datas[0]) else "SETUP"
            print(f"{dt0} === ExampleBuyAndHold (wrapped) wired ===")
            print(f"feeds={len(self.datas)} names={names} size={self.p.size}")

    def _log(self, msg):
        if getattr(self.p, "printlog", False) and len(self.datas):
            dt = self.datas[0].datetime.date(0) if len(self.datas[0]) else "SETUP"
            print(f"{dt} {msg}")

    def next(self):
        # COMP396Base.next() has already run (by the wrapper), so:
        # - Bankruptcy/final-day logic already applied
        # - Limit cancels handled
        # - We'll queue market orders here and the wrapper will flush same bar
        if self._did_buy or self._entry:
            return

        d = self.data0
        intents = [(d, self.p.size)]
        if not self.overspend_guard(intents):
            self._log("OVRSPEND: skipping proposed buy")
            return

        self._entry = True
        self.place_market(d, self.p.size)  # buffered; filled next open with slippage model
        self._log(f"[ORDER QUEUED] {d._name} buy size={self.p.size:+.4f}")

    # ---- logging hooks ----
    def notify_order(self, order):
        if self._entry and order.data is self.datas[0] and order.isbuy():
            if order.status == order.Completed:
                self._did_buy = True
                self._entry = None
            elif order.status in (order.Canceled, order.Margin, order.Rejected, order.Expired):
                self._entry = None  # Retry on a later decision day.

        d = order.data
        st = order.getstatusname().upper()
        if order.status == order.Submitted:
            self._log(f"[ORDER SUBMITTED] {d._name} type={order.exectype} size={order.size:+.4f}")
        elif order.status == order.Accepted:
            self._log(f"[ORDER ACCEPTED]  {d._name} type={order.exectype} size={order.size:+.4f}")
        elif order.status == order.Completed:
            side = "BUY" if order.isbuy() else "SELL"
            self._log(
                f"[FILL] {side} {d._name} px={order.executed.price:.4f} "
                f"size={order.executed.size:+.4f} value={order.executed.value:.2f} "
                f"comm={order.executed.comm:.2f}"
            )
        elif order.status in [order.Canceled, order.Rejected, order.Margin]:
            self._log(f"[ORDER {st}] {d._name} size={order.size:+.4f}")

    def notify_trade(self, trade):
        if trade.isclosed:
            self._log(
                f"[TRADE CLOSED] {trade.data._name} pnl={trade.pnl:.2f} "
                f"pnl_comm={trade.pnlcomm:.2f} size={trade.size:+.4f}"
            )
        else:
            self._log(
                f"[TRADE UPDATE] {trade.data._name} size={trade.size:+.4f} "
                f"pnl={trade.pnl:.2f} pnl_comm={trade.pnlcomm:.2f}"
            )
