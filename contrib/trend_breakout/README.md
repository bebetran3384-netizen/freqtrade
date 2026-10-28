# TrendBreakoutStrategy

Long-only trend-following strategy (Donchian channel breakout) for spot crypto, with dry-run
configs for OKX and Coinbase and the walk-forward test used to evaluate it.

**This is a research result, not a recommendation to trade it.** See [Caveats](#caveats).

## Files

| File | What it is |
| --- | --- |
| `trend_breakout_strategy.py` | The strategy (`TrendBreakoutStrategy`, 4h candles by default) |
| `config_dryrun_okx.example.json` | Dry-run config: OKX, 15 USDT pairs, 4h |
| `config_dryrun_coinbase.example.json` | Dry-run config: Coinbase, 14 USD pairs, **6h** (Coinbase has no 4h candles) |
| `walkforward.py` | Rolling walk-forward test (12 months train / 6 months test) |

## Rules

- **Market filter:** the pair and BTC must both close above their daily EMA50, and the pair above
  its EMA200 on the trading timeframe.
- **Entry:** close above the highest high of the previous `breakout_len` candles (default 60).
- **Exit:** close below the lowest low of the previous `exit_len` candles (default 18).
- A fixed -15% stoploss only as a catastrophe guard. No ROI target, so winners can run.

An earlier version also had an ATR trailing stop and a volume filter. A walk-forward test showed
they added nothing, so they were removed.

## Results

All backtests use 100 per trade, max 5 open trades, a 1000 starting wallet.

**Walk-forward** (parameters re-selected each window from the past 12 months only, then traded
for the next 6 months; Sep 2024 - Oct 2026, stitched test windows):

| Pair set | Strategy | Market | Worst window drawdown |
| --- | --- | --- | --- |
| Original 15 pairs (BTC, ETH, SOL, XRP, BNB, DOGE, ADA, AVAX, LINK, DOT, LTC, TRX, BCH, NEAR, UNI) | +37% | ~+22% | 9.6% |
| 15 different pairs never used in development (ATOM, FIL, OP, ARB, APT, INJ, AAVE, ETC, XLM, HBAR, ICP, SUI, PEPE, CRV, SAND) | +81% | ~-36% | 12.1% |

On Coinbase data (6h candles, 14 pairs, Jan 2024 - Oct 2026) the defaults made +55% with fees
at 0.6% per side, against a market of about -6%. On 2h candles Coinbase fees ate most of the
edge.

## Caveats

- **Few trades, fat tails.** Roughly 200 trades over almost 3 years. Profits depend on a few large
  winners: on the second pair set, two trades (XLM +352%, CRV +246%) made about 60 of the 81 points.
- **Individual 6-month windows are close to a coin flip.** The edge is losing little in crashes
  (-11% while the market fell 64%) and catching some big trends, not steady returns.
- **It lags strong bull markets** (e.g. +25% vs +50% for the market in late 2024).
- **Best parameters do not transfer between pair sets.** The approach does; the exact numbers don't.
- **Only half the wallet is ever used** with these position sizes, so percentage returns are on
  the full 1000.
- Coinbase is not officially supported by freqtrade (it works, with a warning at startup).
  Its order book pricing isn't available, so the Coinbase config prices from the ticker.

## Usage

Run from the repo root. Both configs have no API keys and `dry_run: true`, so no real orders can
be placed.

```bash
# Data (OKX: 4h + 1d; Coinbase: 6h + 1d). BTC daily data is needed for the market filter.
freqtrade download-data -c contrib/trend_breakout/config_dryrun_okx.example.json -t 4h 1d --timerange 20230601-
freqtrade download-data -c contrib/trend_breakout/config_dryrun_coinbase.example.json -t 6h 1d --timerange 20230601-

# Backtest
freqtrade backtesting -c contrib/trend_breakout/config_dryrun_okx.example.json \
    --strategy-path contrib/trend_breakout --timerange 20240101-

# Dry run (keep it running for a few weeks on a machine that stays on)
freqtrade trade -c contrib/trend_breakout/config_dryrun_okx.example.json --strategy-path contrib/trend_breakout

# Walk-forward test (about 10-20 minutes)
python contrib/trend_breakout/walkforward.py contrib/trend_breakout/config_dryrun_okx.example.json wf_results.json
```

To use the web UI / REST API, first copy the config to a name without `.example`
(e.g. `config_dryrun_okx.json`, which git ignores), then set `api_server.enabled` to `true` and
replace every `CHANGE_ME...` value with a long random string. Do the same before adding API keys.

Behind an HTTPS proxy, add to the `exchange` section:
`"ccxt_config": {"requests_trust_env": true}, "ccxt_async_config": {"aiohttp_trust_env": true}`.
