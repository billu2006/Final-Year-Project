# Filename: strategies/template_strategy.py
# Name: template_strategy
# Type: strategy
# Summary:
#    This file is designed to show the structure and typical
#    components of a BT396-compatible strategy.
#
# Description:
#   - Buys 1 unit of the first data series on Day 1.
#   - Does nothing afterwards.
#
# Example usage: python main.py --strategy template_strategy
#
import backtrader as bt

# --------------------------------------------------------------
# `TeamStrategy` is the recommended class name. The loader wraps it
# with the course rules automatically.
# --------------------------------------------------------------
class TeamStrategy(bt.Strategy):
    """
    Very simple "buy-once" example strategy.
    Demonstrates the structure of a BT396 strategy file.
    """

    # ----------------------------------------------------------
    # 1. Parameters section
    # ----------------------------------------------------------
    # The `params` dict defines configurable values that can be
    # overridden with --param key=value on the command line.
    # Every parameter here becomes self.p.<name> inside the code.
    params = dict(
        printlog=True,  # if True, show diagnostic output
    )

    # ----------------------------------------------------------
    # 2. __init__() — called once at the start
    # ----------------------------------------------------------
    # Use this for setting up indicators or internal variables.
    def __init__(self):
        # Internal flag so we only buy once
        self._did_buy = False
        self._entry = None

        # In more complex strategies, this is where you'd create
        # indicators such as:
        #   self.sma = bt.indicators.SMA(self.datas[0].close, period=20)
        #
        # In this simple demo we don't need any indicators.
        pass

    # ----------------------------------------------------------
    # 3. log() — helper for formatted output
    # ----------------------------------------------------------
    # Optional but common in all BT396 strategies. It makes
    # diagnostic printing easier and consistent.
    def log(self, txt, dt=None):
        if self.p.printlog:
            dt = dt or (self.datas[0].datetime.date(0) if len(self.datas[0]) else "SETUP")
            print(f"{dt} {txt}")

    # ----------------------------------------------------------
    # 4. next() — core trading logic
    # ----------------------------------------------------------
    # This method runs once per bar (typically one day).
    # This is where the strategy decides what to do: buy, sell,
    # hold, place limit orders, etc.
    #
    # In BT396, you should place orders via the safe
    # wrappers (place_market, place_limit1, place_limit2, etc.)
    # provided by the framework. Standard self.buy()/self.sell() calls
    # inside BT396 pass through the same course checks.
    #
    # The framework executes all market orders at the NEXT bar's
    # open, applying slippage and overspend checks automatically.
    def next(self):
        d = self.datas[0]  # the first of the ten loaded data feeds

        # Check if we've already bought — we only want to buy once
        if not self._did_buy and not self._entry:
            size = 1.0  # number of units to buy

            # Before sending orders, we can use overspend_guard()
            # as an optional estimate based on known closing prices.
            # Actual affordability, including costs, is enforced at execution.
            intents = [(d, size)]
            if not self.overspend_guard(intents):
                self.log("OVRSPEND: skipping initial buy (not enough cash)")
                return

            # Place a buffered market order.
            # This will execute at *next bar open* with slippage applied.
            self._entry = True
            self.place_market(d, size)
            self.log(f"Submitting initial BUY for {d._name} size={size:.2f}")

            # Set flag so we don't buy again
    
        else:
            # After the first buy, we do nothing else.
            self.log("Holding position; no further action.")

    # ----------------------------------------------------------
    # 5. notify_order() — optional feedback when orders fill
    # ----------------------------------------------------------
    # This function is called automatically whenever the broker
    # reports a change in order status (Submitted, Completed, etc.)
    def notify_order(self, order):
        if self._entry and order.data is self.datas[0] and order.isbuy():
            if order.status == order.Completed:
                self._did_buy = True
                self._entry = None
            elif order.status in (order.Canceled, order.Margin, order.Rejected, order.Expired):
                self._entry = None  # Retry on a later decision day.

        d = order.data
        st = order.getstatusname()

        # Only log completed fills to keep it clean
        if order.status == order.Completed:
            side = "BUY" if order.isbuy() else "SELL"
            self.log(
                f"[{d._name}] {side} filled "
                f"@{order.executed.price:.4f} "
                f"size={order.executed.size:+.2f} "
                f"value={order.executed.value:.2f}"
            )
        elif order.status in (order.Canceled, order.Margin, order.Rejected):
            self.log(f"[{d._name}] ORDER {st.upper()}")
