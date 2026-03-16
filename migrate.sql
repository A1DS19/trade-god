INSERT INTO positions (coin, avg_buy, qty, last_buy, peak_price)
VALUES ('TAO', 284.59999999999997, 0.0281, '2026-03-15T19:25:11.820465+00:00', 284.59999999999997)
ON CONFLICT (coin) DO UPDATE SET
    avg_buy    = EXCLUDED.avg_buy,
    qty        = EXCLUDED.qty,
    last_buy   = EXCLUDED.last_buy,
    peak_price = EXCLUDED.peak_price;

INSERT INTO daily_spend (date, amount)
VALUES ('2026-03-15', 8)
ON CONFLICT (date) DO UPDATE SET amount = EXCLUDED.amount;

INSERT INTO coin_list (date, coins)
VALUES ('2026-03-15', '["BTC","ETH","BNB","XRP","SOL","TRX","DOGE","ADA","BCH","LINK","XLM","LTC","AVAX","HBAR","SUI","SHIB","TON","TAO","UNI","DOT"]')
ON CONFLICT (date) DO UPDATE SET coins = EXCLUDED.coins;

SELECT * FROM positions;
SELECT * FROM daily_spend;
SELECT * FROM coin_list;
