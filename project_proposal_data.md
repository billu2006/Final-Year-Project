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
| Baselines and OFAT sweeps (19 strategies) | 171 |
| Cost sweep (4 `s_mult` levels × 19 strategies) | 76 |
| `p_random` extra seeds | 29 |
| Interaction grids | 147 |
| **Total per dataset** | **423** |
| **Total, both datasets** | **846** |

The first baseline runs will be timed to estimate total wall-clock time.
`p_mm_spread` is the slowest strategy because it produces roughly 22,000 fills per run.
Runs are independent and can be executed in parallel.

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
- **Existing sweep script.** `experiments/strategy_sweep/run_experiments.py` points to a different project folder (`/Users/billu/Desktop/BT396_version_0_1_5s`). Its project path must be changed to this repository before it is reused for this experiment.
- **Single-series strategies.** `sma_cross`, `example_buy_and_hold` and `template_strategy` only trade series 1, so their results should not be compared directly with 10-series portfolios.
- **Leveraged strategies.** Bankruptcy stops trading early, so profit and PD from those runs are not comparable with the others. They are analysed separately.
