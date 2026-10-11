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

- `spot_ticks` — raw trades, keep short retention (`DELETE WHERE ts < now()-interval '7 days'`)
- `option_snapshots` — full chain per snapshot
- `candles(timeframe, bucket, o/h/l/c, volume, vwap, trades)` — `1h/2h/4h/1D/1W/1M`
