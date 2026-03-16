TRADING ALGO IMPROVEMENTS
=========================

POSITION SIZING
---------------
- Kelly Criterion: size each trade based on win rate and avg win/loss ratio
- Volatility-based sizing: larger position on low-volatility coins, smaller on high-volatility
- ATR (Average True Range) based stop distances instead of fixed percentages

DCA / ENTRY LOGIC
-----------------
- Grid DCA: fixed buy levels at -3%, -6%, -9%, -12% from entry instead of just "below avg buy"
- Increasing position size per grid level (e.g. $8, $13, $21 — Fibonacci sizing)
- Max grid levels per coin to cap downside exposure
- Separate entry thresholds per market regime (trending vs ranging)

EXIT LOGIC
----------
- Partial take profit: sell 50% at +5%, let the rest ride with trailing stop
- Time-based exit: sell if position hasn't moved in X days (dead money)
- Re-entry logic after stop loss: don't re-buy same coin for 24-48h after being stopped out

MARKET REGIME DETECTION
------------------------
- Trending vs ranging detection using ADX (Average Directional Index)
- Adjust DIP_THRESHOLD and TAKE_PROFIT dynamically based on regime
- Bear market mode: tighten all thresholds or pause buying entirely

RISK MANAGEMENT
---------------
- Correlation filtering: skip buy if highly correlated coin already held
  (e.g. don't buy both ETH and SOL if correlation > 0.85)
- Portfolio heat: pause all buying if total unrealized loss > X% of portfolio
- Per-sector exposure cap: limit total allocation to L1s, memes, DeFi tokens

INDICATORS
----------
- MACD crossover as additional buy confirmation
- Bollinger Bands: only buy near lower band
- On-chain volume validation (separate from Binance volume)
- Funding rate filter: avoid longs when perpetual funding rate is very negative

BACKTESTING
-----------
- Backtest all strategy params against 1-2 years of historical OHLCV data
- Walk-forward optimization to avoid overfitting
- Validate DIP_THRESHOLD, TAKE_PROFIT, TRAILING_STOP_PCT, DCA_DROP_PCT per coin

EXECUTION
---------
- Limit orders instead of market orders to avoid slippage on small caps
- Spread monitoring: skip trade if bid/ask spread > threshold
- Fee-adjusted profit targets: account for 0.1% Binance fee on entry + exit
