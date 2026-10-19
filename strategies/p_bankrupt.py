# Filename: strategies/p_bankrupt.py
# Name: p_bankrupt
# Type: portfolio strategy
# Summary: portfolio strategy that probably goes bankrupt.
#
# Description:
# - Day 1: SHORT series 1–5 equally so total short exposure = `leverage`.
# - Day 2: LONG the remaining series (6..N), spending (cash - cash_buffer) equally.
#
# Intentional “blow-up” demo: very high gearing (e.g., 40:1) and asymmetric
# allocation make this likely to go bankrupt—useful for teaching risk.
#

import math
import backtrader as bt

class TeamStrategy(bt.Strategy):
    """Two-phase portfolio demo designed to illustrate bankruptcy risk:
    short first five series on day one, then go long the rest on day two."""

    params = dict(
        leverage=40_000_000,    # total short exposure across series 1–5
        cash_buffer=1_000_000,  # keep £1M unspent before going long
        printlog=False,
    )

    def __init__(self):
        if not math.isfinite(float(self.p.leverage)) or float(self.p.leverage) <= 0:
            raise ValueError("leverage must be finite and positive.")
        if not math.isfinite(float(self.p.cash_buffer)) or float(self.p.cash_buffer) < 0:
            raise ValueError("cash_buffer must be finite and non-negative.")
        self._phase_orders = {}
        self._phase_failed = False
        self._phase = None
        self._did_shorts = False
        self._did_longs = False
        self.datas_list = list(self.datas)

        if len(self.datas_list) < 6:
            raise ValueError(
                f"p_bankrupt expects at least 6 data feeds (got {len(self.datas_list)}). "
                "Use --data-dir with at least 10 CSV files."
            )

    def log(self, txt, dt=None):
        if self.p.printlog:
            dt = dt or (self.datas[0].datetime.date(0) if len(self.datas[0]) else "SETUP")
            print(f"{str(dt)} {txt}")

    def next(self):
        if self._phase_orders:
            return
        # --- Phase 1: Day 1 → SHORT series 1..5 ---
        if not self._did_shorts:
            exposure_total = float(self.p.leverage)
            per_series_exposure = exposure_total / 5.0
            intents = []  # for overspend pre-check

            for i in range(5):
                d = self.datas_list[i]
                if not len(d) or d.datetime[0] != self.datetime[0]:
                    continue
                opx = float(d.open[0])
                if opx <= 0:
                    continue
                size = - per_series_exposure / opx  # negative = short
                intents.append((d, size))

            # overspend guard before submitting all orders
            if not self.overspend_guard(intents):
                self.log("OVRSPEND: cancelling short orders (Day 1)")
                return

            self._phase = "short"
            self._phase_failed = False
            for i, (d, size) in enumerate(intents):
                order = self.place_market(d, size)
                self._phase_orders[d] = True
                self.log(f"SHORT data[{i}] @open≈{float(d.open[0]):.2f} size={size:.2f}")

            # Short phase completes only after confirmed executions.
            return  # one phase per day

        # --- Phase 2: Day 2 → LONG series 6..N ---
        if self._did_shorts and not self._did_longs:
            cash = float(self.broker.getcash())
            to_spend = max(0.0, cash - float(self.p.cash_buffer))

            longs = self.datas_list[5:]
            if not longs or to_spend <= 0:
                self.log("Skipping longs — no cash or insufficient data.")
                self._did_longs = True
                return

            per_series_exposure = to_spend / float(len(longs))
            intents = []

            for j, d in enumerate(longs, start=5):
                opx = float(d.open[0])
                if opx <= 0:
                    continue
                size = per_series_exposure / opx  # positive = long
                intents.append((d, size))

            if not self.overspend_guard(intents):
                self.log("OVRSPEND: cancelling long orders (Day 2)")
                return

            self._phase = "long"
            self._phase_failed = False
            for j, (d, size) in enumerate(intents, start=5):
                order = self.place_market(d, size)
                self._phase_orders[d] = True
                self.log(f"LONG data[{j}] @open≈{float(d.open[0]):.2f} size={size:.2f}")

            # Long phase completes only after confirmed executions.
            return

        # --- After both phases: hold positions to the end ---
        return

    def notify_order(self, order):
        if order.data not in self._phase_orders:
            return
        if order.status not in (order.Completed, order.Canceled, order.Margin,
                                order.Rejected, order.Expired):
            return
        self._phase_failed |= order.status != order.Completed
        self._phase_orders.pop(order.data)
        if not self._phase_orders and not self._phase_failed:
            if self._phase == "short":
                self._did_shorts = True
            elif self._phase == "long":
                self._did_longs = True
