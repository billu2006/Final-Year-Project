# Filename: strategies/simple_limit.py
# Name: simple_limit
# Type: strategy
# Summary:
#
#
# Description:
#        Each day:
#       • spread = spreadPercentage * range_source(High - Low)
#       • BUY limit  at center − 0.5 * spread
#       • SELL limit at center + 0.5 * spread
#       • If |position| > inventoryLimits → flatten (market)
#       • Acts on all or rotating series.
#
#
# Simple daily limit-quote strategy (BT396-safe)
# ----------------------------------------------
# - The broker expires each limit after one eligible feed bar.
# - Computes daily bid/ask around a chosen center.
# - Flattens positions if inventory exceeds limits.
# - Places limit orders through place_limit1()/place_limit2() wrappers.
# - Optionally rotates which series trades each day.
#
# example usage: python main.py --strategy simple_limit --param spreadPercentage=0.10 --param inventoryLimits=1000
#


import math
import backtrader as bt
from math import isfinite


class TeamStrategy(bt.Strategy):
    """
    BT396 market-making style strategy.

    Each day:
      • spread = spreadPercentage * range_source(High - Low)
      • BUY limit  at center − 0.5 * spread
      • SELL limit at center + 0.5 * spread
      • If |position| > inventoryLimits → flatten (market)
      • Acts on all or rotating series.

    Framework provides: place_limit1/2, place_market, overspend_guard.
    """

    params = dict(
        size=1,
        spreadPercentage=0.30,
        inventoryLimits=50,
        center_on="close",         # 'close' | 'open' | 'prev_close'
        range_source="today",      # completed day k; 'yesterday' also supported
        series_mode="all",         # 'all' | 'rotate'
        rotate_start=0,
        log_debug=True,
    )

    def __init__(self):
        if not math.isfinite(float(self.p.size)) or float(self.p.size) <= 0:
            raise ValueError("size must be finite and positive.")
        if not math.isfinite(float(self.p.inventoryLimits)) or float(self.p.inventoryLimits) < 0:
            raise ValueError("inventoryLimits must be finite and non-negative.")
        if not math.isfinite(float(self.p.spreadPercentage)) or float(self.p.spreadPercentage) < 0:
            raise ValueError("spreadPercentage must be finite and non-negative.")
        if self.p.series_mode not in ('all', 'rotate'):
            raise ValueError("Invalid series_mode.")
        if self.p.center_on not in ('close', 'open', 'prev_close'):
            raise ValueError("Invalid center_on.")
        if self.p.range_source not in ('today', 'yesterday'):
            raise ValueError("Invalid range_source.")
        self._last_clock_date = None
        self._day_index = -1  # for rotation across series

    # --- helpers -------------------------------------------------------------
    def log(self, txt, dt=None):
        """Conditional diagnostic logging."""
        if self.p.log_debug:
            dt = dt or (self.datas[0].datetime.date(0) if len(self.datas[0]) else "SETUP")
            print(f"{dt} {txt}")

    def _targets_today(self):
        """Select which feeds to act on today based on mode."""
        if self.p.series_mode.lower() == "rotate":
            i = (self.p.rotate_start + self._day_index) % len(self.datas)
            return [self.datas[i]]
        return list(self.datas)

    def _center_price(self, d):
        if self.p.center_on.lower() == "prev_close":
            if len(d) < 2:
                return None
            return float(d.close[-1])
        if self.p.center_on.lower() == "close":
            return float(d.close[0])
        return float(d.open[0])

    def _range_value(self, d):
        if self.p.range_source.lower() == "today":
            hi, lo = float(d.high[0]), float(d.low[0])
        else:
            if len(d) < 2:
                return None
            hi, lo = float(d.high[-1]), float(d.low[-1])
        rng = hi - lo
        return rng if isfinite(rng) and rng > 0 else None

    # --- main loop -----------------------------------------------------------
    def next(self):
        # Run once per calendar day using data0 as clock
        clock_today = self.datetime.date(0)
        if self._last_clock_date == clock_today:
            return
        self._last_clock_date = clock_today
        self._day_index += 1

        self.log(f"SimpleLimit.next() clock={clock_today} mode={self.p.series_mode}")

        # Verify that wrappers exist
        required = ("place_limit1", "place_limit2", "place_market", "overspend_guard")
        if not all(hasattr(self, n) for n in required):
            self.log("FATAL: wrapper not injected; aborting today")
            return

        targets = self._targets_today()

        for d in targets:
            if not len(d) or d.datetime[0] != self.datetime[0]:
                continue
            # --- 0) Inventory control ---
            pos = self.getposition(d).size
            if abs(pos) > self.p.inventoryLimits:
                delta = -pos
                if delta > 0 and not self.overspend_guard([(d, delta)]):
                    self.log(f"{getattr(d, '_name', 'series')} OVRSPEND: skip flatten BUY")
                else:
                    self.place_market(d, delta)
                    self.log(f"{getattr(d, '_name', 'series')} flatten delta={delta:+.2f}")
                continue  # Do not reopen inventory with fresh limits on the exit day.

            # --- 1) Compute today's quote levels ---
            center = self._center_price(d)
            rng = self._range_value(d)
            if center is None or rng is None:
                continue

            spread = float(self.p.spreadPercentage) * rng
            buy_px = round(center - 0.5 * spread, 6)
            sell_px = round(center + 0.5 * spread, 6)

            # Submit both independent quotes. The broker checks actual eligible
            # fills jointly across all series, including sale proceeds.
            self.place_limit1(d, size=+abs(self.p.size), price=buy_px)
            self.place_limit2(d, size=-abs(self.p.size), price=sell_px)

            # --- 3) Log diagnostics ---
            lo0 = float(d.low[0])
            hi0 = float(d.high[0])
            self.log(
                f"{getattr(d, '_name', 'series')} rng={rng:.4f} spread={spread:.4f} center={center:.4f} "
                f"buy@{buy_px:.4f} sell@{sell_px:.4f} "
                f"lo0={lo0:.4f} hi0={hi0:.4f} "
                f"reference bar only; execution uses the following bar"
            )

    # --- optional fill logging ----------------------------------------------
    def notify_order(self, order):
        if order.status == order.Completed:
            side = "BUY" if order.isbuy() else "SELL"
            self.log(
                f"{side} filled @{order.executed.price:.6f} "
                f"size={order.executed.size:+.2f} value={order.executed.value:.2f}"
            )
