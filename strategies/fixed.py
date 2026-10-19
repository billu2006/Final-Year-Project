# Filename: strategies/fixed.py
# Name: fixed
# Type: strategy
# Summary: establishes fixed target positions on the first bar and then holds without further trades
#
# Description:
# - On the first iteration, submit MARKET orders to reach a fixed position per feed.
# - Afterwards, submit no further orders; positions are held until the harness
#   liquidates at the end of the backtest.
#
# Params:
#   sizes: list[float]   Fixed per-feed positions (+ long / - short). Default = [1.0]*nfeeds
#   printlog: bool       Enable console logging

import backtrader as bt


class TeamStrategy(bt.Strategy):
    """Wrapped strategy that establishes fixed target positions on the first bar and then holds without further trades."""
    params = dict(
        sizes=None,
        printlog=False,
    )

    # ---------- utilities ----------
    def _log(self, msg):
        if self.p.printlog and len(self.datas) > 0:
            dt = self.datas[0].datetime.date(0) if len(self.datas[0]) else "SETUP"
            print(f"{dt} {msg}")

    # ---------- lifecycle ----------
    def __init__(self):
        self.datas_list = list(self.datas)
        self._sizes = None          # resolved in start()
        self._took_positions = False

    def start(self):
        n = len(self.datas_list)
        if n == 0:
            raise ValueError("No data feeds. Use --data-dir with at least 10 CSV files.")

        # Default sizes if none provided
        if self.p.sizes is None:
            self._sizes = [1.0] * n
        else:
            if len(self.p.sizes) != n:
                raise ValueError(f"len(sizes) must equal number of feeds ({n}), got {len(self.p.sizes)}")
            self._sizes = [float(x) for x in self.p.sizes]

        self._log("=== fixed (wrapped) wired ===")
        self._log(f"feeds={n} names={[d._name for d in self.datas_list]}")
        self._log(f"sizes={self._sizes}")

    def next(self):
        # Take positions only once (first iteration we see)
        if self._took_positions:
            return

        if all(self.getposition(d).size == qty for d, qty in zip(self.datas_list, self._sizes)):
            self._took_positions = True
            return

        # Submit net adjustments; retry a rejected initial basket.
        for d, qty in zip(self.datas_list, self._sizes):
            qty = float(qty) - self.getposition(d).size
            if qty == 0.0:
                continue
            # Routed via wrapper: buffered, overspend-guarded, and filled next open
            self.place_market(d, qty)
            self._log(f"[ORDER QUEUED] {d._name} target add={qty:+.4f}")

        # Confirm the holdings on the next decision day before marking done.

    # ---------- logging hooks ----------
    def notify_order(self, order):
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
                f"[TRADE CLOSED] {trade.data._name} pnl={trade.pnl:.2f} pnl_comm={trade.pnlcomm:.2f} "
                f"size={trade.size:+.4f}"
            )
        else:
            self._log(
                f"[TRADE UPDATE] {trade.data._name} size={trade.size:+.4f} "
                f"pnl={trade.pnl:.2f} pnl_comm={trade.pnlcomm:.2f}"
            )
