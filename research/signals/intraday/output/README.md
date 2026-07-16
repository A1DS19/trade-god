# Edge-hunt output schema note

`horizon_hours` in these CSVs holds **15m-bar counts, not hours** (the column name is inherited
from `siglib.events.event_study`, which was written for 1h panels): 4 = 1h, 16 = 4h, 32 = 8h,
96 = 24h. `checks.csv` uses the honest name `horizon_bars`.
