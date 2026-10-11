"""Free public REST helpers (no API key). Used for backfill + MCP fallback."""
import httpx

COINBASE = "https://api.exchange.coinbase.com"
DERIBIT = "https://www.deribit.com/api/v2"


def coinbase_trades(product="BTC-USD", limit=100):
    r = httpx.get(f"{COINBASE}/products/{product}/trades", params={"limit": limit}, timeout=15)
    r.raise_for_status()
    return r.json()  # newest first: time, trade_id, price, size, side


def coinbase_candles(product="BTC-USD", granularity=3600, limit=50):
    """granularity seconds: 60,300,900,3600,21600,86400. Returns [time,low,high,open,close,volume]."""
    r = httpx.get(
        f"{COINBASE}/products/{product}/candles",
        params={"granularity": granularity},
        timeout=15,
    )
    r.raise_for_status()
    rows = sorted(r.json(), key=lambda x: x[0])[-limit:]
    return rows


def deribit_instruments(currency="BTC", kind="option"):
    r = httpx.get(
        f"{DERIBIT}/public/get_instruments",
        params={"currency": currency, "kind": kind, "expired": "false"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["result"]


def deribit_book_summary(currency="BTC", kind="option"):
    r = httpx.get(
        f"{DERIBIT}/public/get_book_summary_by_currency",
        params={"currency": currency, "kind": kind},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["result"]


def deribit_ticker(instrument):
    r = httpx.get(f"{DERIBIT}/public/ticker", params={"instrument_name": instrument}, timeout=15)
    r.raise_for_status()
    return r.json()["result"]
