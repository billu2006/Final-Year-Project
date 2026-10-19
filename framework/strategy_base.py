# framework/strategy_base.py
import os
import backtrader as bt
from dataclasses import dataclass
from datetime import date

@dataclass
class COMP396BrokerConfig:
    """Holds framework-wide broker/config options used by the COMP396 engine (slippage scale, end-of-test policy, output paths, debug)."""
    s_mult: float = 1.0              # scales the 20% gap model
    end_policy: str = "liquidate"    # or "hold"
    output_dir: str = "./output"
    debug: bool = False              # verbose CLI logs (auto-on under pytest)


class COMP396Base:
    """
    Mixin for COMP396 rule enforcement:
    - Gap slippage (20% of overnight gap) on MARKET orders only.
    - Overspend guard: if actual next-day fills would overspend (including costs),
      cancel all ordinary orders for the day, market and limit together.
    - Max 2 independent limit orders per series per day (either direction).
    - Bankruptcy: if net worth < 0, force-liquidate all at current open (w/ slippage) and stop.
    - Final-day policy: close each series at its own last open under 'liquidate'.
    - Official PD uses daily closing net profit, including fill-level costs.
    """

    def __init__(self, *args, **kwargs):
        # The child Strategy (bt.Strategy subclass) must declare _comp396 in its params.
        self._cfg = getattr(self.p, '_comp396', None)
        if self._cfg is None:
            raise ValueError("Strategy must declare params with ('_comp396', None) and main.py must pass it.")

        self._today: date | None = None
        self._limit_counts = {}  # data -> number submitted today
        self._market_counts = {}

        self._bankrupt = False
        self._all_datas = list(self.datas)

        # let analyzers read this
        self._comp396_state = {"bankrupt": False}

        # --- Debug / Verbose logging control ---
        # On if config.debug OR running under pytest (PYTEST_CURRENT_TEST env var present)
        cfg_debug = bool(getattr(self._cfg, "debug", False))
        self._debug = cfg_debug or bool(os.environ.get("PYTEST_CURRENT_TEST"))

    # ---------- Helpers: date handling ----------
    def _d(self, data):
        return data.datetime.date(0)

    def _is_new_day(self):
        d = self.datetime.date(0)
        if self._today != d:
            self._today = d
            self._limit_counts = {}
            self._market_counts = {}
            self._today_market_orders = []
            self._today_intents = []
            self._pending_market_orders = []
            if self._debug:
                self.dlog("NEW DAY: reset counters / buffers")
            return True
        return False

    # ---------- Helpers: order placement ----------
    def place_market(self, data, size):
        """Queue a market order (executed next open)."""
        if not size:
            return None
        return self.buy(data=data, size=size) if size > 0 else self.sell(data=data, size=abs(size))

    def place_limit1(self, data, size, price):
        return self._place_limit(data, size, price)

    def place_limit2(self, data, size, price):
        return self._place_limit(data, size, price)

    def place_limit(self, data, size, price):
        return self._place_limit(data, size, price)

    def _place_limit(self, data, size, price):
        """
        Single source-of-truth enforcement:
        - Do NOT pre-increment caps here.
        - Delegate to buy/sell (which enforce and increment exactly once).
        """
        if not size:
            return None
        ex = bt.Order.Limit
        side = "BUY" if size > 0 else "SELL"
        self.dlog(f"LIMIT {side} queued {data._name} @ {price:.6g} size={abs(size)}")
        if size > 0:
            return self.buy(data=data, size=abs(size), price=price, exectype=ex)
        else:
            return self.sell(data=data, size=abs(size), price=price, exectype=ex)

    def _cancel_all_todays_market_orders(self):
        # Cancel orders we tracked
        self.dlog("OVRSPEND: cancelling ALL queued market orders for today")
        for o in list(getattr(self, "_today_market_orders", [])):
            try:
                self.cancel(o)
            except Exception:
                pass
        self._today_market_orders = []
        self._today_intents = []

        # Defensive sweep: cancel any still-open MARKET orders at the broker for this strategy
        try:
            for o in list(self.broker.get_orders_open()):
                if o.exectype == bt.Order.Market and o.owner is self:
                    try:
                        self.cancel(o)
                    except Exception:
                        pass
        except Exception:
            # some brokers may not expose get_orders_open; fail-quiet
            pass

    # ---------- Safe wrapper for order_target_size ----------

    def order_target_size(self, data=None, target=None, size=None, **kwargs):
        """
        BT396-safe override of Backtrader's order_target_size().

        Adjusts the position on 'data' to reach the desired target size,
        routing the order through the BT396 buffered market-order system.
        Accepts either 'target=' or 'size=' keyword for compatibility.
        """
        # Resolve argument naming differences
        if target is None and size is not None:
            target = size
        if target is None:
            self.log("order_target_size() called without a 'target' or 'size' argument — ignoring")
            return None

        if data is None:
            data = self.data0  # default to primary data feed

        current = self.getposition(data).size
        diff = target - current
        if abs(diff) < 1e-8:
            return None  # already at target

        return self.place_market(data, diff)

    def _flush_pending_market_orders(self):
        # Build combined intents (ignore entries without size/data)
        intents = [(pm["data"], pm["signed"]) for pm in self._pending_market_orders
                   if pm["data"] is not None and pm["signed"] is not None]

        if self._pending_market_orders:
            pretty = ", ".join(
                f"{('BUY' if pm['is_buy'] else 'SELL')} {pm['data']._name} size={abs(pm['signed'])}"
                for pm in self._pending_market_orders if pm["data"] is not None and pm["signed"] is not None
            )
            self.dlog(f"FLUSH market orders: [{pretty}]")

        # Actual affordability is checked atomically by the broker on the
        # next eligible bar, including all market and limit fills.

        # Submit buffered orders to broker; track for analysis
        for pm in self._pending_market_orders:
            if pm["is_buy"]:
                o = super(COMP396Base, self).buy(*pm["args"], **pm["kwargs"])
            else:
                o = super(COMP396Base, self).sell(*pm["args"], **pm["kwargs"])

            if o is not None and pm["data"] is not None and pm["signed"] is not None:
                # Track for cash forecast
                self._today_market_orders.append(o)
                self._today_intents.append((pm["data"], pm["signed"]))
                self.dlog(f"SUBMIT {('BUY' if pm['is_buy'] else 'SELL')} MARKET {pm['data']._name} size={abs(pm['signed'])}")

        self._pending_market_orders.clear()

    # These overrides intercept raw buy / sell and route them through the rules:
    def _is_market_ex(self, kwargs):
        ex = kwargs.get('exectype', bt.Order.Market)
        return ex in (bt.Order.Market, None)

    def _is_limit_ex(self, kwargs):
        return kwargs.get('exectype', None) == bt.Order.Limit

    def _extract_order_intent(self, is_buy, args, kwargs):
        data = kwargs.get('data', args[0] if args else (self.data0 if len(self.datas) else None))
        size = kwargs.get('size', None)
        if size is None:
            side = "BUY" if is_buy else "SELL"
            self.log(f"WARNING: raw {side} called without explicit 'size'. "
                     f"Use explicit size for clear budgeting; the broker checks actual fills.")
            return data, None
        signed = +abs(size) if is_buy else -abs(size)
        return data, signed

    def _enforce_limit_cap(self, is_buy, data) -> bool:
        count = self._limit_counts.get(data, 0)
        if count >= 2:
            self.log(f"Limit rejected (max 2 independent limits/day) on {data._name}")
            return False
        self._limit_counts[data] = count + 1
        return True

    def _enforce_market_cap(self, data) -> bool:
        count = self._market_counts.get(data, 0)
        if count >= 1:
            self.log(f"Market rejected (max 1 market/day) on {data._name}")
            return False
        self._market_counts[data] = count + 1
        return True

    def _trading_closed(self, data):
        """Reserve each feed's penultimate decision and final open for closing.

        Called in buy/sell as well as next(), so notification callbacks cannot
        reopen a terminal feed before the strategy's daily hook runs.
        """
        if self._cfg.end_policy != "liquidate" or data is None or not len(data):
            return False
        return data in self._terminal_datas or len(data) >= data.buflen() - 1

    def buy(self, *args, **kwargs):
        if "comp396_forced" in kwargs or "_checksubmit" in kwargs:
            raise ValueError("Mandatory execution flags are reserved for the framework.")
        if kwargs.get("size") == 0:
            return None
        if kwargs.get("parent") is not None or kwargs.get("oco") is not None or kwargs.get("transmit") is False:
            raise ValueError("COMP396 requires independent orders; brackets/OCO are not supported.")
        data, _ = self._extract_order_intent(True, args, kwargs)
        if data is not None and (not len(data) or data.datetime.date(0) != self.datetime.date(0)):
            return None
        if self._trading_closed(data):
            self.dlog(f"Order ignored: final liquidation reserved for {data._name}")
            return None
        # LIMITs: enforce two independent daily slots and place immediately
        if self._is_limit_ex(kwargs):
            data, _ = self._extract_order_intent(True, args, kwargs)
            if data is not None and not self._enforce_limit_cap(True, data):
                return None
            return super().buy(*args, **kwargs)

        # MARKETs: buffer for end-of-bar overspend check
        if self._is_market_ex(kwargs):
            data, signed = self._extract_order_intent(True, args, kwargs)
            if data is not None and not self._enforce_market_cap(data):
                return None
            if data is not None and signed is not None:
                self.dlog(f"QUEUE BUY  MARKET {data._name} size={abs(signed)}")
            self._pending_market_orders.append(
                {"is_buy": True, "args": args, "kwargs": kwargs, "data": data, "signed": signed}
            )
            return None

        raise ValueError("COMP396 permits only Market and Limit orders.")

    def sell(self, *args, **kwargs):
        if "comp396_forced" in kwargs or "_checksubmit" in kwargs:
            raise ValueError("Mandatory execution flags are reserved for the framework.")
        if kwargs.get("size") == 0:
            return None
        if kwargs.get("parent") is not None or kwargs.get("oco") is not None or kwargs.get("transmit") is False:
            raise ValueError("COMP396 requires independent orders; brackets/OCO are not supported.")
        data, _ = self._extract_order_intent(False, args, kwargs)
        if data is not None and (not len(data) or data.datetime.date(0) != self.datetime.date(0)):
            return None
        if self._trading_closed(data):
            self.dlog(f"Order ignored: final liquidation reserved for {data._name}")
            return None
        if self._is_limit_ex(kwargs):
            data, _ = self._extract_order_intent(False, args, kwargs)
            if data is not None and not self._enforce_limit_cap(False, data):
                return None
            return super().sell(*args, **kwargs)

        if self._is_market_ex(kwargs):
            data, signed = self._extract_order_intent(False, args, kwargs)
            if data is not None and not self._enforce_market_cap(data):
                return None
            if data is not None and signed is not None:
                self.dlog(f"QUEUE SELL MARKET {data._name} size={abs(signed)}")
            self._pending_market_orders.append(
                {"is_buy": False, "args": args, "kwargs": kwargs, "data": data, "signed": signed}
            )
            return None

        raise ValueError("COMP396 permits only Market and Limit orders.")

    # ---------- Overspend guard for market orders ----------
    def overspend_guard(self, intents):
        """Optional estimate from known closing prices, not a fill guarantee.

        The broker checks actual next-day market and limit fills together.
        Strategies must not obtain future opening prices through this helper.
        """
        cash = self.broker.getcash()
        for data, size in intents:
            if not self._trading_closed(data):
                price = float(data.close[0])
                cash -= size * price
                cash -= self.broker.getcommissioninfo(data).getcommission(size, price)
        return cash >= 0

    # ---------- Slippage application (post-fill) ----------
    def notify_order(self, order):
        # lifecycle logs
        if order.status == order.Submitted:
            self.dlog(f"ORDER Submitted id={order.ref} {order.data._name} type={order.exectype} size={order.created.size}")
        elif order.status == order.Accepted:
            self.dlog(f"ORDER Accepted  id={order.ref} {order.data._name}")
        elif order.status in [order.Canceled, order.Rejected]:
            self.dlog(f"ORDER {('Canceled' if order.status==order.Canceled else 'Rejected')} id={order.ref} {order.data._name}")

        if order.status in [order.Completed]:
            data = order.data
            action = "BUY" if order.isbuy() else "SELL"
            self.dlog(f"FILL {action} {data._name} px={order.executed.price:.6g} size={order.executed.size}")
            # Execution costs were charged synchronously by BT396Broker.
            return

    def notify_trade(self, trade):
        """Log realized PnL when a position is closed/updated."""
        if not self._debug:
            return
        dname = trade.data._name if trade.data else "data"
        if trade.isclosed:
            self.dlog(f"TRADE CLOSED {dname} pnl_gross={trade.pnl:.6g} pnl_net={trade.pnlcomm:.6g} size={trade.size}")
        else:
            self.dlog(f"TRADE UPDATE {dname} size={trade.size} price={getattr(trade, 'price', 'NA')}")

    # ---------- Bankruptcy & final-day enforcement ----------

    def _schedule_final_liquidation(self, data):
        """Close this series at its next (final) open; other feeds continue."""
        self._terminal_datas.add(data)
        self.broker.cancel_outstanding(data=data)
        self._pending_market_orders[:] = [
            order for order in self._pending_market_orders if order["data"] is not data
        ]
        size = self.getposition(data).size
        if size:
            place = super(COMP396Base, self).sell if size > 0 else super(COMP396Base, self).buy
            # Mandatory closing trades bypass ordinary basket affordability.
            # Actual closing costs are still charged by the broker; bankruptcy
            # remains checked at every open before normal execution.
            order = place(data=data, size=abs(size), exectype=bt.Order.Market,
                          _checksubmit=False)
            order.addinfo(comp396_forced=True)
        self.dlog(f"Scheduled {data._name} liquidation for its final open")

    def start(self):
        # Ensure config is present (Strategy must declare ('_comp396', None) in params)
        self._cfg = getattr(self.p, '_comp396', None)
        if self._cfg is None:
            raise ValueError("Strategy must declare params with ('_comp396', None) and main.py must pass it.")

        # (Re)initialize per-run state here because Backtrader *always* calls start()
        self._today = None  # current date marker
        self._limit_counts = {}
        self._market_counts = {}
        self._bankrupt = False
        self._all_datas = list(self.datas)
        self._comp396_state = {"bankrupt": False}
        self._terminal_datas = set()
        self._pending_market_orders = []  # list of dicts: {"is_buy": bool, "args": args, "kwargs": kwargs, "data": data, "signed": +/-size}

        # recompute debug flag in case config changed between init/start
        cfg_debug = bool(getattr(self._cfg, "debug", False))
        self._debug = cfg_debug or bool(os.environ.get("PYTEST_CURRENT_TEST"))
        if self._debug:
            self.dlog("DEBUG logging enabled")

    def next(self):
        """Return whether student trading is allowed on this bar."""
        is_new = self._is_new_day()
        # Broker expires a limit after its eligible feed bar, including feeds
        # with missing calendar dates; the global clock must not cancel it early.
        if self.broker.bankrupt:
            self._bankrupt = True
            self._comp396_state["bankrupt"] = True
            self._comp396_state["bankrupt_date"] = self.broker.bankrupt_date
            self.env.runstop()
            return False
        if self._cfg.end_policy == "liquidate":
            for data in self._all_datas:
                if len(data) and data not in self._terminal_datas and self._trading_closed(data):
                    self._schedule_final_liquidation(data)
            # A shorter first feed must not halt trading on longer feeds.
            if len(self._terminal_datas) == len(self._all_datas):
                return False
        return True


        # >>> NOTE: _flush_pending_market_orders() should be called from the wrapper
        # after student next() so that market orders queued this bar are sent this bar.

    # ---------- Logging ----------
    def log(self, txt):
        dt = self.datetime.date(0) if len(self.datetime) else "SETUP"
        print(f"{dt} | {txt}")

    def dlog(self, txt):
        """Debug log (prints only when debug mode is on)."""
        if self._debug:
            self.log(txt)
