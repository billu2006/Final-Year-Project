# Fill-level cash accounting for the COMP396 cash-funded stock-like model.
# Orders use the original COMP396 market/limit prices and atomic cash check.
# Market gap slippage is
# treated as an immediate cash expense and deducted synchronously right
# before the broker’s daily valuation.

import math
import backtrader as bt


class BT396Broker(bt.brokers.BackBroker):
    params = (("s_mult", 1.0), ("debug", False))

    def start(self):
        super().start()
        self._multiplier = float(self.p.s_mult)
        if not math.isfinite(self._multiplier) or self._multiplier < 0:
            raise ValueError("s_mult must be finite and non-negative.")
        self.ledger = {}
        self.fills = []
        self._owners = {}
        self.bankrupt = False
        self.bankrupt_date = None

    def market_cost(self, gap, size):
        return self._multiplier * 0.2 * abs(float(gap)) * abs(float(size))

    def _gap(self, data):
        if len(data) < 2:
            return 0.0
        return abs(float(data.open[0]) - float(data.close[-1]))

    def _execute(self, order, ago=None, price=None, cash=None, position=None,
                 dtcoc=None):
        count = len(order.executed.exbits)
        result = super()._execute(order, ago=ago, price=price, cash=cash,
                                  position=position, dtcoc=dtcoc)
        if ago is None:
            if result is not None and order.exectype == bt.Order.Market:
                result -= self.market_cost(self._gap(order.data), order.executed.remsize)
            return result

        data = order.data
        for bit in list(order.executed.exbits)[count:]:
            info = self.getcommissioninfo(data)
            if not info.stocklike or info.get_leverage() != 1.0 or not self.p.shortcash:
                raise ValueError("Net PD accounting requires stock-like instruments, leverage=1 and shortcash=True.")
            slip = self.market_cost(self._gap(data), bit.size) if order.exectype == bt.Order.Market else 0.0
            # Avoid add_cash(): its queued adjustment would miss this valuation.
            self.cash -= slip
            if self.p.debug and order.exectype == bt.Order.Market:
                print(f"{data.datetime.date(0)} | SLIPPAGE {data._name} charged={slip:.6g} "
                      f"size={bit.size} s_mult={self._multiplier}")
            entry = self.ledger.setdefault(data, {"cash_flow": 0.0,
                                                   "commission": 0.0,
                                                   "slippage": 0.0})
            entry["cash_flow"] -= bit.size * bit.price + bit.comm + slip
            entry["commission"] += bit.comm
            entry["slippage"] += slip
            self._owners[data] = order.owner
            self.fills.append({"date": bt.num2date(bit.dt).date().isoformat(),
                               "series": data._name, "order_ref": order.ref,
                               "order_type": order.getordername(), "size": bit.size,
                               "price": bit.price, "commission": bit.comm,
                               "slippage": slip})
        return result

    def cancel_outstanding(self, data=None):
        """Cancel all outstanding orders, or only orders on one feed."""
        for order in list(self.pending):
            if order is not None and (data is None or order.data is data):
                self.cancel(order)
        for order in list(self.submitted):
            if data is not None and order.data is not data:
                continue
            self.submitted.remove(order)
            order.cancel()
            self.notify(order)

    def _liquidate_if_bankrupt(self):
        if self.bankrupt:
            return True
        worth = self.cash + sum(pos.size * float(data.open[0])
                                for data, pos in self.positions.items() if pos.size)
        if worth >= 0:
            return False
        self.bankrupt = True
        positioned = [(data, pos.size) for data, pos in self.positions.items() if pos.size]
        self.bankrupt_date = max((data.datetime.date(0) for data in self.ledger), default=None)
        self.cancel_outstanding()
        # Forced closing orders must execute even when available cash is negative.
        for data, size in positioned:
            place = self.sell if size > 0 else self.buy
            order = place(owner=self._owners[data], data=data, size=abs(size),
                          exectype=bt.Order.Market, _checksubmit=False)
            self.pending.remove(order)
            self._execute(order, ago=0, price=float(data.open[0]))
        self._get_value()
        return True

    @staticmethod
    def legacy_limit_price(size, limit, high, low):
        # R v5.9 deliberately requires penetration beyond a 0.0001 offset.
        if size > 0 and low < limit - 0.0001:
            return min(limit, high)
        if size < 0 and high > limit + 0.0001:
            return max(limit, low)
        return None

    def _day_price(self, order):
        if order.exectype == bt.Order.Market:
            return float(order.data.open[0])
        if order.exectype == bt.Order.Limit:
            return self.legacy_limit_price(order.executed.remsize,
                float(order.created.price), float(order.data.high[0]),
                float(order.data.low[0]))
        raise ValueError("COMP396 permits only Market and Limit orders.")

    def _spend(self, order, price):
        size = order.executed.remsize
        commission = self.getcommissioninfo(order.data).getcommission(size, price)
        cost = self.market_cost(self._gap(order.data), size) if order.exectype == bt.Order.Market else 0.0
        return size * price + commission + cost

    def _commit(self, fills):
        # Funding is assessed jointly. Settle receipts before purchases so native
        # sequential cash checks cannot reject an already-funded basket leg.
        for order, price in sorted(fills, key=lambda item: self._spend(*item)):
            self._execute(order, ago=0, price=price)
            if order.status != order.Completed:
                raise RuntimeError("A funded COMP396 basket failed to execute completely.")

    def next(self):
        if self._liquidate_if_bankrupt():
            return
        if self.p.filler is not None:
            raise ValueError("COMP396 legacy rules do not support volume partial fills.")
        # Defer cash acceptance until actual execution-day OHLC is available.
        # No individual pseudo-fill check: the course rule is a portfolio batch.
        while self.submitted:
            order = self.submitted.popleft()
            if self._take_children(order) is not None:
                self.submit_accept(order)
        ordinary, forced, waiting = [], [], []
        while self.pending:
            order = self.pending.popleft()
            if order is None or not order.alive():
                continue
            if order.created.dt >= order.data.datetime[0]:
                waiting.append(order)
                continue
            if order.info.get('comp396_forced', False):
                forced.append((order, float(order.data.open[0])))
            else:
                ordinary.append(order)
        self.pending.extend(waiting)
        # Mandatory final exits retain the repaired final-open policy.
        self._commit(forced)
        if self._liquidate_if_bankrupt():
            for order in ordinary:
                order.cancel()
                self.notify(order)
            return
        fills = [(order, self._day_price(order)) for order in ordinary]
        fills = [(order, price) for order, price in fills if price is not None]
        spend = math.fsum(self._spend(order, price) for order, price in fills)
        if spend > self.cash:
            if self.p.debug:
                print("OVERSPEND: no ordinary trades execute today")
            for order in ordinary:
                order.cancel()
                self.notify(order)
        else:
            self._commit(fills)
            # Unfilled day-only limits are discarded after this eligible bar.
            for order in ordinary:
                if order.alive():
                    order.cancel()
                    self.notify(order)
        self._get_value()
        self._liquidate_if_bankrupt()

    def net_by_series(self, datas):
        result = {}
        for data in datas:
            entry = self.ledger.get(data, {})
            position = self.getposition(data)
            holding = position.size * float(data.close[0]) if position.size else 0.0
            result[data._name] = entry.get("cash_flow", 0.0) + holding
        return result
