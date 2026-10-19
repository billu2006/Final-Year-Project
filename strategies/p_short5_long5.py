# Filename: strategies/p_short5_long5.py
# Name: p_short5_long5
# Type: strategy
# Summary:
#   Two-phase leveraged portfolio: short series 1–5 on day one, then go long
#   series 6–10 on day two.
#
# Description:
# - Day 1: SHORT series 1–5 equally so total short exposure = leverage.
# - Day 2: LONG series 6–10 equally using (cash − cash_buffer).
#
# Example usage: python main.py --strategy p_short5_long5

import math
import backtrader as bt


class TeamStrategy(bt.Strategy):
    # Two-phase leveraged portfolio: short series 1–5 on day one, then go long
    # series 6–10 on day two.

    params = dict(
        leverage=40_000_000,   # total short exposure across series 1–5
        cash_buffer=1_000_000, # reserve cash before long phase
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

        # Require ≥10 data feeds
        if len(self.datas_list) < 10:
            raise ValueError(
                f"p_short5_long5 expects at least 10 data feeds; got {len(self.datas_list)}. "
                "Use --data-dir with at least 10 CSV files."
            )

    def log(self, txt, dt=None):
        if self.p.printlog:
            dt = dt or (self.datas[0].datetime.date(0) if len(self.datas[0]) else "SETUP")
            print(f"{dt} {txt}")

    def next(self):
        if self._phase_orders:
            return
        # --- Phase 1: Day 1 SHORTS across 1–5 ---
        if not self._did_shorts:
            exposure_total = float(self.p.leverage)
            per_series_exposure = exposure_total / 5.0
            intents = []

            for i in range(5):
                d = self.datas_list[i]
                if not len(d) or d.datetime[0] != self.datetime[0]:
                    continue
                opx = float(d.open[0])
                if opx <= 0:
                    continue
                size = - per_series_exposure / opx  # negative = short
                intents.append((d, size))

            # Cash forecast check before placing all shorts
            if not self.overspend_guard(intents):
                self.log("OVRSPEND: cancelling short basket (Day 1)")
                return

            self._phase = "short"
            self._phase_failed = False
            for i, (d, size) in enumerate(intents):
                order = self.place_market(d, size)
                self._phase_orders[d] = True
                self.log(f"SHORT data[{i}] @open≈{float(d.open[0]):.2f} size={size:.2f}")

            # Short phase completes only after confirmed executions.
            return  # next day handles longs

        # --- Phase 2: Day 2 LONGS across 6–10 ---
        if self._did_shorts and not self._did_longs:
            cash = float(self.broker.getcash())
            to_spend = max(0.0, cash - float(self.p.cash_buffer))
            per_series_exposure = to_spend / 5.0 if to_spend > 0 else 0.0

            intents = []
            for i in range(5, 10):
                d = self.datas_list[i]
                if not len(d) or d.datetime[0] != self.datetime[0]:
                    continue
                opx = float(d.open[0])
                if opx <= 0:
                    continue
                size = per_series_exposure / opx  # positive = long
                intents.append((d, size))

            if not self.overspend_guard(intents):
                self.log("OVRSPEND: cancelling long basket (Day 2)")
                return

            self._phase = "long"
            self._phase_failed = False
            for i, (d, size) in enumerate(intents, start=5):
                order = self.place_market(d, size)
                self._phase_orders[d] = True
                self.log(f"LONG  data[{i}] @open≈{float(d.open[0]):.2f} size={size:.2f}")

            # Long phase completes only after confirmed executions.
            return

        # --- Phase 3: Hold thereafter ---
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
