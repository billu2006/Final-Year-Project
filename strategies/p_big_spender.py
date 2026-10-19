# Filename: strategies/p_big_spender.py
# Name: p_big_spender
# Type: portfolio strategy
# Summary:
#   Every bar, submits one MARKET order per feed using the configured sizes.
#
# Description:
# Big Spender — BT396 demonstration strategy
# -------------------------------------------------
# - Every bar, submits one MARKET order per feed using the configured sizes.
# - All orders route through COMP396Base.place_market(), not raw buy/sell.
# - Optionally pre-screens the day’s basket with overspend_guard() using known closing prices.
#   The broker checks actual fills and costs at execution.
# - The BT396 engine then buffers, applies slippage, and atomically accepts/
#   rejects the basket as a whole.
#
# Example usage: python main.py --strategy p_big_spender --param sizes=[1,1,1,0,0,0,0,0,0,0]


import backtrader as bt


class TeamStrategy(bt.Strategy):
    params = dict(
        sizes=None,       # list[float] per feed; + = buy, − = sell
        precheck=True,    # run overspend_guard before queuing
        printlog=False,   # verbose CLI logging
    )

    # ---------------- Logging helper ----------------
    def _log(self, msg: str) -> None:
        """Prints timestamped debug lines when printlog=True."""
        if self.p.printlog and self.datas:
            dt = self.datas[0].datetime.date(0) if len(self.datas[0]) else "SETUP"
            print(f"{dt} {msg}")

    # ---------------- Lifecycle ----------------
    def __init__(self):
        self.datas_list = list(self.datas)
        self._sizes = None  # resolved in start()

    def start(self):
        n = len(self.datas_list)
        if n == 0:
            raise ValueError("No data feeds. Use --data-dir with at least 10 CSV files.")

        # Resolve per-feed sizes
        if self.p.sizes is None:
            self._sizes = [1.0] * n
        else:
            if len(self.p.sizes) != n:
                raise ValueError(f"len(sizes) must equal number of feeds ({n}), got {len(self.p.sizes)}")
            self._sizes = [float(x) for x in self.p.sizes]

        self._log("=== p_big_spender (BT396) initialised ===")
        self._log(f"feeds={n} names={[d._name for d in self.datas_list]}")
        self._log(f"sizes={self._sizes}")
        self._log(f"precheck={self.p.precheck}")

    # ---------------- Core trading logic ----------------
    def next(self):
        """Submit a fixed-size MARKET order on every feed each bar."""
        intents = [(d, float(self._sizes[i])) for i, d in enumerate(self.datas_list) if self._sizes[i] != 0.0]

        if not intents:
            self._log("[SKIP] Nothing to do (all sizes are zero)")
            return

        # Optional pre-trade cash forecast check
        if self.p.precheck and not self.overspend_guard(intents):
            self._log("[SKIP] optional cash estimate blocked submissions")
            return

        # Queue buffered MARKET orders (executed next open with slippage)
        for d, qty in intents:
            self.place_market(d, qty)
            self._log(f"[ORDER QUEUED] {d._name} size={qty:+.4f}")

    # ---------------- Order / trade notifications ----------------
    def notify_order(self, order):
        """Verbose order lifecycle tracing for diagnostics."""
        d = order.data
        st = order.getstatusname()

        if order.status in (order.Submitted, order.Accepted):
            self._log(f"[ORDER {st.upper()}] {d._name} type={order.exectype} size={order.size:+.4f}")
        elif order.status == order.Completed:
            side = "BUY" if order.isbuy() else "SELL"
            self._log(
                f"[FILL] {side} {d._name} px={order.executed.price:.6f} "
                f"size={order.executed.size:+.4f} value={order.executed.value:.2f} "
                f"comm={order.executed.comm:.2f}"
            )
        elif order.status in (order.Canceled, order.Rejected, order.Margin):
            self._log(f"[ORDER {st.upper()}] {d._name} size={order.size:+.4f}")

    def notify_trade(self, trade):
        """Report trade PnL updates for transparency."""
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
