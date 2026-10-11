# BTCUSD_PRIVATE — live tick-by-tick BTCUSD + options MCP with small Postgres

Free sources, no API keys:
- Spot ticks `BTC-USD`: Coinbase Exchange public WS `wss://ws-feed.exchange.coinbase.com` (`matches`) + REST fallback.
- Options chain: Deribit public `wss://www.deribit.com/ws/api/v2` + REST `get_book_summary_by_currency` (BTC index options).

## 1. Start

```powershell
cd C:\Users\Subhash Kandhway\Downloads\BTCUSD_PRIVATE
copy .env.example .env
pip install -r requirements.txt
docker compose up -d db
python -c "from src.db import init_db; init_db(); print('schema ok')"
python -m src.collector --once   # one REST snapshot + candle build (needs DB up)
python btc_server.py --selftest
python btc_server.py --list-tools
```

Infinite collector (ticks + hourly chain snapshots):

```powershell
python -m src.collector
```

## 2. MCP tools (`btc_server.py`)

- `btc_price` — latest tick (PG first, live fallback)
- `btc_candles(timeframe=1h|2h|4h|1D|1W|1M, limit)` — PG `candles`, live fallback
- `options_chain(expiry_filter, limit)` — PG snapshot, live fallback
- `option_quote(instrument)` — e.g. `BTC-PERPETUAL`
- `iv_skew(expiry_filter)` — strike vs IV
- `db_status` — counts + lag

Add to your `opencode.json`:

```json
{ "mcp": { "btc-private": {
  "type": "local",
  "command": ["python", "C:\\Users\\Subhash Kandhway\\Downloads\\BTCUSD_PRIVATE\\btc_server.py"],
  "enabled": true
} } }
```

## 3. Tables (`schema.sql`)

- `spot_ticks` — raw trades, auto-pruned hourly to last 7 days (`src/prune.py`, `TICKS_RETENTION_DAYS`)
- `option_snapshots` — full chain per snapshot, auto-pruned hourly to last 7 days (`OPTIONS_RETENTION_DAYS`)
- `candles(timeframe, bucket, o/h/l/c, volume, vwap, trades)` — `1h/2h/4h/1D/1W/1M`

## 4. Terminal + paper bot (all PAPER, no real orders)

```powershell
python -m src.tui --snapshot   # dashboard once: chart + chain + paper account
python -m src.tui              # live refresh every 5s
python -m src.dashboard        # view-only web terminal: http://localhost:8765
python -m src.bot --once       # one paper decision cycle
python -m src.bot --interval 60 --qty 0.01 --sl 0.02 --tp 0.04 --timeframe 1h
```

Strategy: EMA12/26 cross + RSI14 filter on `1h` (or `4h`), long/flat only,
stop-loss / take-profit exits, $100k starting cash in `paper_state`.
