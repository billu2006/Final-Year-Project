# Filename: strategies/p_trend_demo.py
# Name: p_trend_demo
# Type: portfolio strategy
# Summary: Follow 20/100-bar moving-average trends, going long above and short below.
# Example: python main.py --strategy p_trend_demo

import math
import backtrader as bt


class TeamStrategy(bt.Strategy):
    """A teaching example: fixed entry budgets, no daily size rebalancing.

    Signals use closing prices available on the current bar. Orders go through
    BT396's guard and execute at the next open. Final liquidation is left to
    the framework. Historical profitability is not a promise of future profit.
    """

    params = dict(
        fast=20,
        slow=100,
        allocation=0.5,     # fraction of initial equity split across selected feeds
        series=None,        # None = all; otherwise a list of 1-based feed numbers
        allow_short=True,
        printlog=False,
    )

    def __init__(self):
        fast, slow = self.p.fast, self.p.slow
        if (type(fast) is not int or type(slow) is not int
                or not 1 <= fast < slow):
            raise ValueError("fast and slow must be integers with 1 <= fast < slow.")
        allocation = float(self.p.allocation)
        if not math.isfinite(allocation) or not 0 < allocation <= 1:
            raise ValueError("allocation must be greater than 0 and at most 1.")
        if type(self.p.allow_short) is not bool or type(self.p.printlog) is not bool:
            raise ValueError("allow_short and printlog must be true or false.")
        selected = self.p.series
        if selected is None:
            selected = list(range(1, len(self.datas) + 1))
        if (not isinstance(selected, (list, tuple)) or not selected
                or any(type(i) is not int or not 1 <= i <= len(self.datas)
                       for i in selected)
                or len(set(selected)) != len(selected)):
            raise ValueError("series must contain distinct valid 1-based feed numbers.")
        self.selected = [self.datas[i - 1] for i in selected]
        self.averages = {
            data: (bt.ind.SMA(data.close, period=fast),
                   bt.ind.SMA(data.close, period=slow))
            for data in self.selected
        }
        self.last_bar = {data: 0 for data in self.selected}

    def start(self):
        self.entry_budget = (
            float(self.broker.getvalue()) * float(self.p.allocation)
            / len(self.selected)
        )

    def next(self):
        intents = []
        for data in self.selected:
            if len(data) == self.last_bar[data] or len(data) < self.p.slow:
                continue
            self.last_bar[data] = len(data)
            fast, slow = self.averages[data]
            direction = 1 if fast[0] > slow[0] else -1 if fast[0] < slow[0] else 0
            if direction < 0 and not self.p.allow_short:
                direction = 0
            current = float(self.getposition(data).size)
            current_direction = 1 if current > 0 else -1 if current < 0 else 0
            if direction == current_direction:
                continue
            close = float(data.close[0])
            if not math.isfinite(close) or close <= 0:
                continue
            units = math.floor(self.entry_budget / close)
            target = direction * units
            delta = target - current
            if delta:
                intents.append((data, delta))

        if intents and self.overspend_guard(intents):
            for data, delta in intents:
                self.place_market(data, delta)
                if self.p.printlog:
                    print(f"{data.datetime.date(0)} {data._name}: order {delta:+g}")
