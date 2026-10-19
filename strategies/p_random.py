# Filename: strategies/p_random.py
# Name: p_random
# Type: portfolio strategy
# Summary:
#   Random portfolio stress-test strategy
#
# Description:
# - Each day submits one random MARKET order per feed with integer size
#   in [-maxLots, +maxLots].
# - Orders go through place_market() so fills occur at the
#   next open with framework slippage.
# - The broker checks actual basket affordability; this does not cap short exposure.

import math
import backtrader as bt
import random


class TeamStrategy(bt.Strategy):
    """Portfolio demo strategy that submits random market orders each day
    across all feeds (BT396-safe version)."""

    params = dict(
        maxLots=10,       # maximum absolute order size
        precheck=True,    # optional overspend guard
        printlog=False,
        seed=396,         # local random generator for reproducible comparisons
    )

    def __init__(self):
        if type(self.p.maxLots) is not int or self.p.maxLots < 0:
            raise ValueError("maxLots must be an integer >= 0.")
        self.datas_list = list(self.datas)
        self.rng = random.Random(self.p.seed)
        if not self.datas_list:
            raise ValueError("No data feeds provided. Use --data-dir with at least 10 CSV files.")

    def log(self, txt, dt=None):
        if self.p.printlog:
            dt = dt or (self.datas[0].datetime.date(0) if len(self.datas[0]) else "SETUP")
            print(f"{str(dt)} {txt}")

    def next(self):
        m = int(self.p.maxLots)
        if m <= 0:
            return

        intents = []  # collect (data, qty) pairs

        # --- 1) Build today's random basket ---
        for i, d in enumerate(self.datas_list):
            if not len(d) or d.datetime[0] != self.datetime[0]:
                continue
            qty = self.rng.randint(-m, m)  # random int in [-m, +m]
            if qty == 0:
                continue
            intents.append((d, float(qty)))
            if self.p.printlog:
                self.log(f"[data[{i}]={d._name}] random intent size={qty:+d}")

        if not intents:
            return  # nothing to do

        # --- 2) Optional pre-trade overspend guard ---
        if self.p.precheck and not self.overspend_guard(intents):
            self.log("OVRSPEND: skipping all proposed random orders today")
            return

        # --- 3) Queue safe market orders for next-open fill ---
        for d, qty in intents:
            self.place_market(d, qty)
            if self.p.printlog:
                side = "BUY" if qty > 0 else "SELL"
                self.log(f"[ORDER QUEUED] {side} {d._name} size={qty:+.0f}")
