# Project Proposal: Data Collection Experiment

## 1. Purpose

This experiment collects performance data for every strategy in the `strategies/` folder.
The data will be used to understand which ideas work, why they work, and how sensitive they are to their settings.
That understanding is the starting point for developing new algorithms.

Each strategy is first run at a fixed **baseline** configuration.
Each parameter is then moved **below and above** the baseline, one at a time, while everything else stays fixed.
Comparing each run with the baseline shows how much each parameter matters and in which direction it pushes the result.

### Research questions

1. Which strategies make money at their baseline settings, and on which series?
2. For each strategy, which parameters have the largest effect on profit, drawdown and PD ratio?
3. Is each parameter's effect monotonic (more is always better or worse), peaked (there is a sweet spot) or flat (it barely matters)?
4. How much of each strategy's result is eaten by execution costs (`s_mult`)?
5. Do the parameter effects found on `DATA/PART1` hold on `DATA/PART1_UPDATED`, or are they specific to one dataset?
6. Which series reward trend-following and which reward mean-reversion? This directly guides the design of new algorithms.

## 2. Test environment

All runs use the BT396 0.1.5 framework through `main.py`, following the rules in `TRADING_RULES.txt`.

### Fixed conditions (held constant for every run unless the factor is being tested)

| Setting | Value | Source |
|---|---|---|
| Starting cash | 1,000,000 | `config.yaml` |
| Commission | 0.0 | `config.yaml` |
| Slippage multiplier `s_mult` | 1.0 | `config.yaml`, standard course value |
| End policy | `liquidate` | `config.yaml`, standard assessment setting |
| Plotting | off (`--no-plot`) | for speed |
| Date range | full file | no `--fromdate` / `--todate` |
| Development dataset | `DATA/PART1` (10 series) | |
| Validation dataset | `DATA/PART1_UPDATED` (10 series) | |

### Command template

```bash
venv/bin/python main.py --strategy <name> --no-plot \
  --data-dir ./DATA/PART1 --s-mult 1.0 \
  --output-dir experiments/proposal_sweep/PART1/<name>__<variant> \
  --param key=value --param key=value
```

## 3. Experimental design

### 3.1 Method: one-factor-at-a-time (OFAT) around a baseline

For every strategy:

1. **Baseline run.** All parameters at the baseline value listed in Section 4.
2. **Parameter sweep.** For each parameter, run two levels below and two levels above the baseline, holding all other parameters at baseline.
   - Numeric parameters use five levels: `low2, low1, BASELINE, high1, high2`.
   - Pure position-size parameters use three levels (×0.5, ×1, ×2). Earlier runs showed `copycat` results scale exactly linearly with `stake`, so extra levels add no information.
   - Boolean and categorical parameters are run at every other value.
3. **Cost sweep.** The baseline configuration is rerun at `s_mult` = 0, 0.5, 1.5 and 2.0. This separates the signal's raw edge from the cost of trading it.
4. **Validation.** Every run above is repeated on `DATA/PART1_UPDATED`.

### 3.2 Interaction grids

OFAT cannot detect parameters that interact, for example a fast and slow moving average that only work as a pair.
For the six strategies with the strongest paired parameters, a full 5×5 grid is also run on both datasets (Section 5).

### 3.3 Noise floor

`p_random` is run at its baseline with 30 different seeds (`seed=1..30`, plus the default `396`).
The spread of these results is a measure of how much profit or loss can be produced by chance on this data.
A parameter change in any other strategy is only treated as meaningful if its effect is larger than this spread.

### 3.4 Validity rules

- A parameter level that is invalid is skipped and logged, never silently changed. For example, `fast` must stay below `slow`, and `allocation` must be in (0, 1].
- Any run that errors, is rejected by the framework, or goes bankrupt is still recorded, with its status.
- No result from `PART1_UPDATED` is used to choose parameters. It is only used to confirm or reject what `PART1` showed.

## 4. Strategies and parameter levels

Baseline values are the defaults in each strategy file, except where a default would make the strategy do nothing.
Those exceptions are marked **(set)**.

### 4.1 Signal-based strategies

**`sma_cross`** — SMA crossover on series 1 only.

| Parameter | low2 | low1 | **Baseline** | high1 | high2 |
|---|---|---|---|---|---|
| `fast` | 5 | 7 | **10** | 15 | 20 |
| `slow` | 15 | 20 | **30** | 45 | 60 |
| `stake` | | 0.5 | **1.0** | 2.0 | |

**`sma_cross_multi`** — the same rule on all 10 series. Same levels as `sma_cross`.

**`p_trend_demo`** — long above / short below a fast and slow moving-average trend.

| Parameter | low2 | low1 | **Baseline** | high1 | high2 |
|---|---|---|---|---|---|
| `fast` | 10 | 15 | **20** | 30 | 40 |
| `slow` | 50 | 75 | **100** | 150 | 200 |
| `allocation` | 0.1 | 0.25 | **0.5** | 0.75 | 1.0 |
| `allow_short` | | False | **True** | | |

**`p_bbands_trend_following`** — buys breakouts above the upper Bollinger band, sells below the lower.

| Parameter | low2 | low1 | **Baseline** | high1 | high2 |
|---|---|---|---|---|---|
| `lookback` | 10 | 15 | **20** | 30 | 40 |
| `sdParam` | 1.0 | 1.5 | **2.0** | 2.5 | 3.0 |
| `exit_on_mid` | | | **False** | True | |
| `default_size` | | 0.5 | **1.0** | 2.0 | |

**`p_bbands_contrarian`** — buys below the lower band, sells above the upper.

| Parameter | low2 | low1 | **Baseline** | high1 | high2 |
|---|---|---|---|---|---|
| `lookback` | 10 | 15 | **20** | 30 | 40 |
| `sdParam` | 1.0 | 1.5 | **2.0** | 2.5 | 3.0 |
| `default_size` | | 0.5 | **1.0** | 2.0 | |

**`bbands_holding_period`** — the contrarian band rule with a maximum holding period.

| Parameter | low2 | low1 | **Baseline** | high1 | high2 |
|---|---|---|---|---|---|
| `lookback` | 10 | 15 | **20** | 30 | 40 |
| `sdParam` | 1.0 | 1.5 | **2.0** | 2.5 | 3.0 |
| `holdPeriod` | 1 | 3 | **5** | 10 | 20 |
| `default_size` | | 0.5 | **1.0** | 2.0 | |

**`p_RSI_contrarian`** — long when RSI is below 50 − threshold, short when above 50 + threshold.

| Parameter | low2 | low1 | **Baseline** | high1 | high2 |
|---|---|---|---|---|---|
| `lookback` | 7 | 10 | **14** | 21 | 28 |
| `threshold` | 0 | 2.5 | **5** | 10 | 20 |
| `default_size` | | 0.5 | **1.0** | 2.0 | |

**`copycat`** — follows the direction of the completed day on all 10 series.

| Parameter | low2 | low1 | **Baseline** | high1 | high2 |
|---|---|---|---|---|---|
| `stake` | 0.25 | 0.5 | **1** | 2 | 4 |

**`condpr`** — targets a position based on whether the completed day went up or down.
Its default responses are all zero, so it never trades. A baseline must be set.

| Variant | `response_to_up` | `response_to_dn` | Meaning |
|---|---|---|---|
| **Baseline (set)** | `[1]*10` | `[-1]*10` | momentum on every series |
| contrarian | `[-1]*10` | `[1]*10` | reversal on every series |
| long-only | `[1]*10` | `[0]*10` | buy after up days, flat after down |
| short-only | `[0]*10` | `[-1]*10` | sell after down days, flat after up |
| split | `[1,1,1,1,1,-1,-1,-1,-1,-1]` | `[-1,-1,-1,-1,-1,1,1,1,1,1]` | example from the file header |

The baseline is also run with `stake_policy=fixed` at `fixed_stake` = 0.5, 1 and 2, against the default `max_over_close`.

### 4.2 Limit-order (market-making) strategies

**`p_mm_spread`** — daily buy and sell limits around the close.

| Parameter | low2 | low1 | **Baseline** | high1 | high2 |
|---|---|---|---|---|---|
| `spreadPercentage` | 0.025 | 0.05 | **0.10** | 0.20 | 0.40 |
| `inventoryLimits` | 100 | 500 | **1000** | 2000 | 5000 |
| `quote_size` | | 0.5 | **1.0** | 2.0 | |

**`simple_limit`** — limit quotes with forced flattening above an inventory limit.

| Parameter | low2 | low1 | **Baseline** | high1 | high2 |
|---|---|---|---|---|---|
| `spreadPercentage` | 0.10 | 0.20 | **0.30** | 0.45 | 0.60 |
| `inventoryLimits` | 10 | 25 | **50** | 100 | 200 |
| `size` | | 0.5 | **1** | 2 | |
| `center_on` | | open | **close** | prev_close | |
| `range_source` | | | **today** | yesterday | |
| `series_mode` | | | **all** | rotate | |

`log_debug` is set to False for all runs to keep output small. It does not affect trading.

### 4.3 Static and benchmark strategies

These have little or no signal logic. They provide reference points that the signal strategies must beat.

| Strategy | Parameter | low | **Baseline** | high | Other variants |
|---|---|---|---|---|---|
| `example_buy_and_hold` | `size` | 0.5 | **1** | 2 | |
| `fixed` | `sizes` | `[0.5]*10` | **`[1]*10`** | `[2]*10` | `[-1]*10` (all short), `[1,-1]*5` (alternating) |
| `p_big_spender` | `sizes` | `[0.5]*10` | **`[1]*10`** | `[2]*10`, `[5]*10` | `precheck=False` |
| `p_random` | `maxLots` | 1, 5 | **10** | 20, 40 | 30 seeds at baseline (Section 3.3) |
| `template_strategy` | none | | **default** | | control run only |

### 4.4 Leveraged stress-test strategies

These are expected to approach or reach bankruptcy.
The aim is to find where the bankruptcy boundary lies, not to find profit.

| Strategy | Parameter | low2 | low1 | **Baseline** | high1 | high2 |
|---|---|---|---|---|---|---|
| `p_bankrupt` | `leverage` | 10M | 20M | **40M** | 60M | 80M |
| | `cash_buffer` | 0 | 0.5M | **1M** | 2M | 4M |
| `p_short5_long5` | `leverage` | 10M | 20M | **40M** | 60M | 80M |
| | `cash_buffer` | 0 | 0.5M | **1M** | 2M | 4M |
| `s_short_then_long` | `leverage` | 2M | 4M | **8M** | 12M | 16M |
| | `cash_buffer` | 0 | 0.5M | **1M** | 2M | 4M |

## 5. Interaction grids

Each grid crosses all five levels of two parameters. All other parameters stay at baseline.

| Strategy | Parameter A | Parameter B | Valid runs |
|---|---|---|---|
| `sma_cross_multi` | `fast` | `slow` | 22 (pairs with fast ≥ slow skipped) |
| `p_trend_demo` | `fast` | `slow` | 25 |
| `p_bbands_trend_following` | `lookback` | `sdParam` | 25 |
| `p_bbands_contrarian` | `lookback` | `sdParam` | 25 |
| `p_RSI_contrarian` | `lookback` | `threshold` | 25 |
| `p_mm_spread` | `spreadPercentage` | `inventoryLimits` | 25 |

## 6. Run budget

| Block | Runs per dataset |
|---|---|
| Baselines and OFAT sweeps (19 strategies) | 170 |
| Cost sweep (4 `s_mult` levels × 19 strategies) | 76 |
| `p_random` extra seeds | 29 |
| Interaction grids | 147 |
| **Total per dataset** | **422** |
| **Total, both datasets** | **844** |

Each run takes about two seconds. The full sweep took under five minutes with 10 runs in parallel.
It is implemented in `experiments/proposal_sweep/run_proposal.py`.

## 7. Data collected

Each run writes `run_summary.json`, `pd_results.json` and `fills.json` to its own output folder.
A collector script combines them into one row per run.

### Run-level table (`results.csv`)

| Column | Meaning |
|---|---|
| `dataset` | PART1 or PART1_UPDATED |
| `strategy` | strategy name |
| `block` | baseline, ofat, cost, seed or grid |
| `parameter` | the parameter changed, or blank for baseline |
| `level` | low2, low1, baseline, high1, high2, or the categorical value |
| `params` | full parameter string passed to `main.py` |
| `s_mult` | slippage multiplier used |
| `net_profit` | final portfolio net profit after costs |
| `pd_ratio` | portfolio profit / maximum drawdown |
| `pd_status` | framework PD status (e.g. loss, finite, infinite) |
| `max_drawdown` | maximum monetary drawdown |
| `slippage_paid` | total market-order execution cost |
| `fills` | number of executed orders |
| `activity_pct` | percentage of days with an open position |
| `profitable_series` | number of the 10 series with positive net profit |
| `bankrupt` | True or False |
| `status` | ok, invalid_params or error |

### Series-level table (`per_series.csv`)

One row per run per series, holding net profit, PD and drawdown for that series.
This is the table that shows which series suit which kind of strategy.

### Storage layout

```
experiments/proposal_sweep/
  PART1/<strategy>__<parameter>_<level>/   raw framework output
  PART1_UPDATED/...
  results.csv
  per_series.csv
```

## 8. Analysis plan

1. **Baseline league table.** Rank all strategies by PD ratio and net profit on each dataset.
2. **Response curves.** For every strategy and parameter, plot net profit, PD ratio and max drawdown against the five levels. Mark the baseline.
3. **Sensitivity ranking.** For each parameter, compute the change in PD ratio from `low2` to `high2`. Present the results as a tornado chart per strategy, so the most influential parameters stand out.
4. **Shape classification.** Label each response curve as monotonic up, monotonic down, peaked or flat. A peaked curve suggests an optimum worth refining.
5. **Cost decomposition.** Compare net profit at `s_mult` = 0 against `s_mult` = 1. The difference shows how much of each strategy's edge is lost to trading costs. Strategies with a positive raw edge but negative net profit are candidates for lower-turnover versions.
6. **Noise test.** Compare each parameter's effect with the spread of the 30 `p_random` seeds. Effects smaller than that spread are reported as not significant.
7. **Robustness check.** A finding is only accepted if the parameter pushes the result in the same direction on both datasets.
8. **Series profiling.** Use the series-level table to label each series as trend-friendly, reversal-friendly or neither. Compare trend strategies (SMA, trend demo, band breakout, momentum `condpr`) against reversal strategies (band contrarian, RSI, contrarian `condpr`).
9. **Heatmaps.** Plot each interaction grid as a heatmap of PD ratio, to show stable regions rather than single best points.

## 9. How the data feeds new algorithm development

The results are expected to point toward new algorithms such as:

- **Per-series strategy selection.** Run trend rules on trend-friendly series and reversal rules on reversal-friendly series.
- **Cost-aware signals.** Add a minimum-signal threshold or holding period where the cost decomposition shows turnover destroying the edge.
- **Hybrid market-making.** Combine limit quoting, which avoids market slippage, with a trend filter that limits inventory against the trend.
- **Risk sizing.** Use the drawdown data and bankruptcy boundary to set position sizes that keep drawdown within a chosen limit.

## 10. Known risks and notes

- **Overfitting.** Choosing parameters on the same data used to judge them inflates results. This is why `PART1_UPDATED` is held back for validation only.
- **OFAT limits.** One-at-a-time changes miss interactions. The grids in Section 5 cover the most likely ones.
- **Older sweep script.** `experiments/strategy_sweep/run_experiments.py` points to a different project folder (`/Users/billu/Desktop/BT396_version_0_1_5s`). The new runner, `experiments/proposal_sweep/run_proposal.py`, replaces it for this experiment.
- **Single-series strategies.** `sma_cross`, `example_buy_and_hold` and `template_strategy` only trade series 1, so their results should not be compared directly with 10-series portfolios.
- **Leveraged strategies.** Bankruptcy stops trading early, so profit and PD from those runs are not comparable with the others. They are analysed separately.

## 11. Results: what the data shows

The full sweep was run on 26 October 2026. All 844 runs completed without errors.
Raw results are in `experiments/proposal_sweep/results.csv` and `experiments/proposal_sweep/per_series.csv`.

### 11.1 Summary

1. **No signal strategy has a reliable edge after costs.** Every signal strategy loses money at baseline on at least one dataset, and most lose on both.
2. **Trading less is the most consistent way to improve results.** Wider bands, higher RSI thresholds and longer lookbacks cut the number of trades and improve profit on both datasets.
3. **Execution costs decide most outcomes.** Removing slippage turns several losing strategies into break-even or small winners.
4. **The predictable part of the price move happens overnight.** On `PART1`, prices reverse strongly from one day to the next, but almost all of that reversal happens between the close and the next open. Market orders fill at that open, so they arrive too late and also pay slippage on the gap.
5. **The two datasets behave differently.** `PART1` reverses day to day on every series. `PART1_UPDATED` has two series that rise roughly tenfold and trend. Parameter settings that win on one dataset often lose on the other.
6. **Position size scales results but does not create an edge.** Doubling size doubles both profit and drawdown, so the PD ratio does not change.

### 11.2 Baseline results

| Strategy | Net profit PART1 | Net profit UPDATED | Fills PART1 | Activity % PART1 |
|---|---|---|---|---|
| `s_short_then_long` | 49,309 | −355,597 | 3 | 99.4 |
| `p_trend_demo` | 12,808 | −62,749 | 205 | 93.0 |
| `p_mm_spread` | 830 | −785 | 22,052 | 99.6 |
| `p_random` | 625 | −163,484 | 14,113 | 99.6 |
| `sma_cross` (series 1 only) | 42 | 45 | 58 | 44.9 |
| `example_buy_and_hold` / `template_strategy` | −18 | 43 | 2 | 99.4 |
| `p_bbands_trend_following` | −335 | −445 | 338 | 98.2 |
| `sma_cross_multi` | −743 | 59 | 624 | 96.8 |
| `fixed` | −821 | 957 | 20 | 99.6 |
| `p_bbands_contrarian` | −865 | −708 | 1,885 | 62.1 |
| `bbands_holding_period` | −991 | −842 | 1,901 | 61.9 |
| `p_RSI_contrarian` | −1,005 | −1,048 | 4,036 | 98.6 |
| `simple_limit` | −8,198 | −12,337 | 20,564 | 99.6 |
| `copycat` | −9,331 | −10,037 | 7,434 | 99.6 |
| `condpr` | −20,092 | −27,895 | 14,338 | 99.6 |
| `p_big_spender` | −115,138 | 153,627 | 5,988 | 99.6 |
| `p_bankrupt` / `p_short5_long5` | −1,479,031 (bankrupt) | −2,374,077 (bankrupt) | 20 | 75.0 |

Only `sma_cross` is profitable on both datasets, and its profit is under 50 on a 1,000,000 account.
`p_bankrupt` and `p_short5_long5` contain the same trading logic, so they produce identical results.
`example_buy_and_hold` and `template_strategy` both buy one unit of series 1, so they also match.

### 11.3 What helps profit

**Being more selective helps the band and RSI strategies on both datasets.**
Raising the entry threshold means fewer, stronger signals and far fewer trades.

| `p_bbands_contrarian` `sdParam` | 1.0 | 1.5 | **2.0** | 2.5 | 3.0 |
|---|---|---|---|---|---|
| Net profit PART1 | −1,543 | −1,275 | **−865** | −282 | 17 |
| Net profit UPDATED | −989 | −639 | **−708** | −158 | −94 |
| Fills PART1 | 4,548 | 3,393 | **1,885** | 628 | 160 |

| `p_RSI_contrarian` `threshold` | 0 | 2.5 | **5** | 10 | 20 |
|---|---|---|---|---|---|
| Net profit PART1 | −1,655 | −1,359 | **−1,005** | −216 | −68 |
| Net profit UPDATED | −1,526 | −1,172 | **−1,048** | −629 | 391 |

The same pattern holds for `p_bbands_trend_following` (`sdParam` = 3.0 gives +527 and +260, from about 50 trades), and for `bbands_holding_period`.
Longer lookbacks also help the reversal strategies. RSI with `lookback` = 28 improves from −1,005 to −444 on `PART1` and reaches +13 on `PART1_UPDATED`.
The interaction grids mostly confirm this. For `p_bbands_contrarian`, the best cell on both datasets is the longest lookback with the widest band. For `p_RSI_contrarian`, the best region on both datasets is the highest threshold with a medium or long lookback. The `p_bbands_trend_following` grid has no stable best cell.

**Forcing early exits hurts.** `bbands_holding_period` with a one-day holding period is its worst setting on both datasets. Holding periods of 10 or more never trigger and give the same result as `p_bbands_contrarian`.

**Trend-following parameters are unstable.** The `p_trend_demo` and `sma_cross_multi` grids have no consistent winning region. The best `PART1` cell for `p_trend_demo` is fast 40 / slow 75, but the best `PART1_UPDATED` cell is fast 40 / slow 200. Neighbouring cells often swing from large profit to large loss. These results should not be used to pick parameters.

**Turning off shorting helped the trend strategy on both datasets.** `p_trend_demo` with `allow_short=False` made 13,323 on `PART1` and 22,477 on `PART1_UPDATED`, against 12,808 and −62,749 at baseline.

**Market-making results depend on the dataset.** A wider `p_mm_spread` spread raised profit steadily on `PART1`, from −316 to 6,977. On `PART1_UPDATED` there was no clear pattern. Drawdown stayed around 15,000 to 23,000 in every case, far larger than any profit.

**`simple_limit` improved when it traded less.** Rotating through one series per day (`series_mode=rotate`) cut fills by 90% and moved the result from −8,198 to −1,521 on `PART1` and from −12,337 to 1,235 on `PART1_UPDATED`. Using yesterday's range also improved both datasets.

**`condpr` loses under every response pattern.** Momentum, reversal, long-only, short-only and split responses all lose on both datasets. With a fixed stake, its momentum version produces exactly the same trades and results as `copycat`.

### 11.4 How the trading constraints shape performance

**Next-open execution and gap slippage.**
Market orders fill at the next open and pay 0.2 × the overnight gap × quantity.
The cost sweep shows how much this matters.

| Strategy | Net profit, `s_mult` = 0 | Net profit, `s_mult` = 1 | Net profit, `s_mult` = 2 |
|---|---|---|---|
| `p_RSI_contrarian` (PART1) | 808 | −1,005 | −2,818 |
| `p_bbands_contrarian` (PART1) | 80 | −865 | −1,809 |
| `copycat` (PART1) | −2,165 | −9,331 | −16,497 |
| `condpr` (PART1) | −3,300 | −20,092 | −36,885 |
| `p_trend_demo` (PART1) | 67,179 | 12,808 | −41,563 |
| `p_mm_spread` (PART1) | 1,097 | 830 | 562 |

The reversal strategies have a small raw edge on `PART1` that slippage more than removes.
Profit falls in a straight line as `s_mult` rises, so cost per trade is the key quantity.
The limit-order strategies are barely affected, because limit fills pay no slippage.

**Why the overnight gap matters.** On `PART1`, today's return is negatively correlated with tomorrow's return on every series (−0.08 to −0.48). Splitting tomorrow's move into the overnight gap and the open-to-close move shows where the reversal happens.

| Correlation of today's return with... | PART1, typical series | PART1_UPDATED, typical series |
|---|---|---|
| tomorrow's close-to-close return | about −0.15 | about 0 to +0.2 |
| tomorrow's overnight gap | about −0.15 | about +0.1 |
| tomorrow's open-to-close return | about 0 | about −0.1 |

On `PART1` the reversal is almost entirely in the gap, which a market order cannot capture. On `PART1_UPDATED` the gap continues the move and the reversal happens during the next trading day. This explains why `copycat` and `condpr` lose on both datasets, and why reversal strategies only work before costs.

**Cash and affordability limits.** `p_big_spender` buys every day until its cash runs out. After that, the broker rejects every basket. As size grows from 0.5 to 5 units, the number of trading days on `PART1` falls from 1,290 to 129. Its result is then simply the market's direction on the stock it has already bought: −115,138 on `PART1` and +153,627 on `PART1_UPDATED`. The optional overspend check made almost no difference, because the broker enforces the limit anyway.

**Bankruptcy and leverage.** `p_bankrupt` and `p_short5_long5` went bankrupt at every leverage level tested, from 10 million to 80 million. A bigger cash buffer reduced the loss but did not prevent bankruptcy. `s_short_then_long` shows how a single gap can decide a leveraged trade. On `PART1_UPDATED` it shorted about 38,000 units, and the price opened 4% higher the next day. The loss and slippage left the account below its cash buffer, so it could not take the long position and finished at −355,597.

**Inventory limits on limit-order strategies.** In `p_mm_spread` at the baseline spread, inventory never went above 94 units on any series. Limits of 500 and above never triggered at any spread tested. A limit of 100 with a wide spread did trigger, and the forced market exits turned a +3,899 result into −7,739. Forced flattening at a bad moment costs more than it saves.

**Units, not money.** Positions are set in units, and series prices range from under 1 to over 800. On `PART1`, one unit of series 2 is worth about 0.7, so it contributes almost nothing. Series 3 and 9 are worth about 400 each and dominate every portfolio result. Equal unit sizes give very unequal risk.

**Scale of the baseline strategies.** Most demo strategies trade one unit per series on a 1,000,000 account, so they use less than 0.1% of capital. Their profits and losses are in the hundreds. Scaling up is only worthwhile once a strategy has a positive PD ratio, and cash and bankruptcy limits then cap how far it can go.

**Activity.** Strategies that always hold a position score about 99% activity. The band contrarian strategies score about 60%, and `sma_cross` about 45%, because they spend time flat. The settings that improve profit (wider bands, higher thresholds) lower activity further. If activity is assessed, this trade-off has to be managed.

**End-of-run liquidation** has little effect. Buy-and-hold results change by about 2 between `s_mult` = 0 and 2.

### 11.5 How much of this is noise

`p_random` with 30 seeds shows how much a strategy with no edge can make or lose.

| Dataset | Worst seed | Median seed | Best seed | Seeds in profit |
|---|---|---|---|---|
| PART1 | −111,110 | −42,008 | 59,904 | 8 of 30 |
| PART1_UPDATED | −172,408 | −20,759 | 155,162 | 12 of 30 |

These swings come from holding large random positions while prices drift, and are much larger than any signal strategy's profit.
Single large results from leveraged or position-building strategies, such as `p_trend_demo` and `p_big_spender`, should therefore be treated with caution.
Findings are only reported above when they point in the same direction on both datasets.

### 11.6 Which series suit which approach

With costs removed, trend strategies did best on `PART1` series 1 and 8, and on `PART1_UPDATED` series 2, 6 and 9.
Reversal strategies did best on `PART1` series 3, 4 and 9, and on `PART1_UPDATED` series 3, 4, 5 and 10.
`PART1_UPDATED` series 2 and 9 rose from about 46 to 538 and from about 97 to 936. They are the only series with clearly positive day-to-day correlation, and simple long positions in them earned most of `fixed`'s profit.
`PART1` series 2 and 10 trade at prices around 1 and 10, so unit-sized strategies barely move on them.

### 11.7 Implications for new algorithms

1. **Reduce trading.** Every consistent improvement came from fewer trades. New algorithms should require strong signals and hold positions longer.
2. **Use limit orders where possible.** Limit fills pay no slippage. A limit order placed at the close can also catch the overnight gap that market orders miss.
3. **Size by money, not units.** Target a fixed amount of money or a fixed volatility per series, so that cheap series are not ignored and expensive ones do not dominate.
4. **Pick the approach per series.** Measure each series' recent day-to-day correlation, and use trend rules where it is positive and reversal rules where it is negative.
5. **Avoid forced exits at fixed limits.** Use gradual inventory reduction instead of a single market order to flatten.
6. **Scale up only after the edge is proven.** Increase size once the PD ratio is positive on both datasets, and stay well clear of the leverage levels that caused bankruptcy here.
