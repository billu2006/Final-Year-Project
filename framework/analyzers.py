# Official net-profit PD plus optional diagnostic analysers.
import math
import collections
import backtrader as bt

def pd_metrics(cumulative_profit):
    # The lecture definition; include the initial zero-profit baseline.
    values = [float(v) for v in cumulative_profit]
    if any(not math.isfinite(v) for v in values):
        raise ValueError("PD requires finite net-profit observations.")
    peak = 0.0
    drawdown = 0.0
    duration = longest = 0
    for value in values:
        peak = max(peak, value)
        drawdown = max(drawdown, peak - value)
        duration = duration + 1 if value < peak else 0
        longest = max(longest, duration)
    profit = values[-1] if values else 0.0
    if profit <= 0:
        score, status = round(profit, 2), "loss" if profit < 0 else "break_even"
    elif drawdown == 0:
        score, status = float("inf"), "no_drawdown"
    else:
        score, status = round(profit / drawdown, 2), "profitable"
    return {"pd_ratio": score, "pd_status": status, "net_profit": profit,
            "max_drawdown": drawdown, "max_drawdown_duration_bars": longest}


class NetPnL(bt.Analyzer):
    # Daily closing net profit, with fill-level costs attributed to each series.
    def start(self):
        if not hasattr(self.strategy.broker, "net_by_series"):
            raise ValueError("Net PD requires framework.broker.BT396Broker.")
        self._initial = float(self.strategy.broker.startingcash)
        self._dates = []
        self._values = []
        self._portfolio = []
        self._per = {d._name: [] for d in self.datas}

    def next(self):
        broker = self.strategy.broker
        per = broker.net_by_series(self.datas)
        equity = float(broker.getvalue())
        profit = equity - self._initial
        if not math.isclose(sum(per.values()), profit, rel_tol=1e-10, abs_tol=1e-6):
            raise ValueError("Per-series net profit does not reconcile with broker equity. "
                             "Use the standard cash-funded stock-like broker configuration.")
        self._dates.append(self.strategy.datetime.date(0))
        self._values.append(equity)
        self._portfolio.append(profit)
        for name, value in per.items():
            self._per[name].append(value)

    def get_analysis(self):
        broker = self.strategy.broker
        return {"dates": self._dates, "values": self._values,
                "start_equity": self._initial,
                "final_equity": self._values[-1] if self._values else self._initial,
                "portfolio_cum": self._portfolio, "per_instrument_cum": self._per,
                "bankrupt": broker.bankrupt, "bankrupt_date": broker.bankrupt_date,
                "valuation": "daily_close"}


class PDRatio(bt.Analyzer):
    # The official PD calculation, for portfolio and each instrument.
    def start(self):
        self._res = {}

    def stop(self):
        net = self.strategy.analyzers.netpnl.get_analysis()
        broker = self.strategy.broker
        portfolio = pd_metrics(net["portfolio_cum"])
        portfolio.update(start_equity=net["start_equity"], final_equity=net["final_equity"])
        per = {}
        for data in self.datas:
            result = pd_metrics(net["per_instrument_cum"][data._name])
            costs = broker.ledger.get(data, {})
            result.update(commission=costs.get("commission", 0.0),
                          slippage=costs.get("slippage", 0.0))
            per[data._name] = result
        portfolio["commission"] = sum(row["commission"] for row in per.values())
        portfolio["slippage"] = sum(row["slippage"] for row in per.values())
        self._res = {"metric_version": "net_pd_v1", "valuation": "daily_close",
                     "portfolio": portfolio, "per_instrument": per}

    def get_analysis(self):
        return self._res


class TruePortfolioPD(PDRatio):
    # Deprecated import alias. Use PDRatio with a NetPnL analyser named netpnl.
    # ignore
    pass


class RealizedPnL(bt.Analyzer):
    # Optional closed-trade diagnostic after commission, excluding separate slippage.
    # This is not the official net-profit curve and is not used to calculate PD.

    def start(self):
        self._dates = []
        self._per = {d._name: [] for d in self.datas}
        self._portfolio = []
        self._today = collections.defaultdict(float)

    def notify_trade(self, trade):
        if trade.isclosed:
            self._today[trade.data._name] += float(trade.pnlcomm)

    def next(self):
        self._dates.append(self.strategy.datetime.date(0))
        for name, values in self._per.items():
            values.append((values[-1] if values else 0.0) + self._today[name])
        self._portfolio.append(sum(values[-1] for values in self._per.values()))
        self._today.clear()

    def get_analysis(self):
        return {"dates": self._dates, "portfolio_cum": self._portfolio,
                "per_instrument_cum": self._per,
                "description": "Closed-trade P&L after commission, excluding custom slippage"}

class OpenOpenPnL(bt.Analyzer):
    # Computes per-series and portfolio Open->Open P&L, cumulative PnL, and
    # carries a 'bankrupt' flag read from strategy._comp396_state.

    def start(self):
        self._dates = []
        self._per_inst_daily = {}   # name -> [pnls...]
        self._per_inst_cum   = {}
        self._portfolio_daily = []
        self._portfolio_cum   = []
        self._bankrupt = False

    def next(self):
        # Append date for this bar
        dt = self.datas[0].datetime.date(0)
        self._dates.append(dt)
        port_pnl = 0.0

        for d in self.datas:
            name = d._name or "data"
            if name not in self._per_inst_daily:
                self._per_inst_daily[name] = []
                self._per_inst_cum[name] = []

            # position held today
            pos = self.strategy.getposition(d)
            size = pos.size if pos else 0.0

            # Open→Open P&L requires look-ahead; if unavailable (last bar), treat as 0 P&L for this day
            try:
                o0 = float(d.open[0])
                o1 = float(d.open[1])  # may raise IndexError on the last bar
                pnl = (o1 - o0) * size
            except IndexError:
                pnl = 0.0

            self._per_inst_daily[name].append(pnl)
            cum = (self._per_inst_cum[name][-1] + pnl) if self._per_inst_cum[name] else pnl
            self._per_inst_cum[name].append(cum)
            port_pnl += pnl

        self._portfolio_daily.append(port_pnl)
        cum = (self._portfolio_cum[-1] + port_pnl) if self._portfolio_cum else port_pnl
        self._portfolio_cum.append(cum)

        # bankrupt flag from strategy
        self._bankrupt = bool(getattr(self.strategy, "_comp396_state", {}).get("bankrupt", False))

        # record bankruptcy date if first detected
        if self._bankrupt and not hasattr(self, "_bankrupt_date"):
            self._bankrupt_date = dt  # record the first day bankruptcy occurs

    def get_analysis(self):
        return {
            "dates": self._dates,
            "per_instrument_daily": self._per_inst_daily,
            "per_instrument_cum": self._per_inst_cum,
            "portfolio_daily": self._portfolio_daily,
            "portfolio_cum": self._portfolio_cum,
            "bankrupt": self._bankrupt,
            "bankrupt_date": getattr(self, "_bankrupt_date", None),
        }


class Activity(bt.Analyzer):
    # % of days with any non-zero position across the portfolio.
    def start(self):
        self._days = 0
        self._active = 0

    def next(self):
        if len(self.datas[0]) < 1:
            return
        self._days += 1
        active = False
        for d in self.datas:
            if self.strategy.getposition(d).size != 0:
                active = True
                break
        if active:
            self._active += 1

    def get_analysis(self):
        pct = (100.0 * self._active / self._days) if self._days else 0.0
        return {"activity_pct": pct, "days": self._days, "active_days": self._active}

