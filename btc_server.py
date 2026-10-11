"""
BTCUSD_PRIVATE MCP server — live tick + option-chain + PG candles.

Tools:
  - btc_price            latest BTC-USD (DB tick first, live REST fallback)
  - btc_candles          1h/2h/4h/1D/1W/1M from PG, fallback to Coinbase REST
  - options_chain        Deribit BTC options snapshot (PG first, live fallback)
  - option_quote         single instrument quote
  - iv_skew              strike vs IV for an expiry filter
  - db_status            row counts + latest timestamps

Run standalone (stdio, for MCP clients):
    python btc_server.py
Test:
    python btc_server.py --list-tools
    python btc_server.py --selftest
"""
import json
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("btcusd-private")
PRODUCT = os.getenv("COINBASE_PRODUCT", "BTC-USD")
CURRENCY = os.getenv("DERIBIT_CURRENCY", "BTC")
VALID_TF = ("1h", "2h", "4h", "1D", "1W", "1M")


def _norm_tf(tf):
    tf = (tf or "1h").strip()
    alias = {"1H": "1h", "2H": "2h", "4H": "4h", "1d": "1D", "1w": "1W", "1m": "1M", "D": "1D", "W": "1W", "M": "1M"}
    tf = alias.get(tf, tf)
    return tf if tf in VALID_TF else "1h"


@mcp.tool()
def btc_price() -> str:
    """Latest BTC-USD price. Tries PG ticks, falls back to live Coinbase REST."""
    try:
        from src import db
        cols, rows = db.query("SELECT ts, price, size FROM spot_ticks ORDER BY ts DESC LIMIT 1")
        if rows:
            ts, px, sz = rows[0]
            return f"BTC-USD {float(px):,.2f} (size {sz}, {ts}, PG tick)"
    except Exception as e:
        pg_err = f"{type(e).__name__}: {e}"
    else:
        pg_err = "no ticks yet"
    try:
        from src.exchanges import coinbase_trades
        t = coinbase_trades(PRODUCT, 1)[0]
        return f"BTC-USD {float(t['price']):,.2f} (size {t['size']} {t.get('side')}, {t['time']}, live)"
    except Exception as e:
        return f"No price available. PG: {pg_err}. Live: {type(e).__name__}: {e}"


@mcp.tool()
def btc_candles(timeframe: str = "1h", limit: int = 20) -> str:
    """OHLC candles for timeframe 1h/2h/4h/1D/1W/1M. PG first, live REST fallback.

    Args:
        timeframe: one of 1h,2h,4h,1D,1W,1M.
        limit: rows to return (1-200).
    """
    tf = _norm_tf(timeframe)
    limit = max(1, min(int(limit), 200))
    try:
        from src import db
        cols, rows = db.query(
            "SELECT bucket, open, high, low, close, volume FROM candles "
            "WHERE timeframe=%s ORDER BY bucket DESC LIMIT %s",
            (tf, limit),
        )
        if rows:
            lines = [f"BTC-USD {tf} candles (PG, newest first):"]
            for b, o, h, lo, c, v in rows:
                lines.append(f"{b}: O={o:.1f} H={h:.1f} L={lo:.1f} C={c:.1f} V={v:.4f}")
            return "\n".join(lines)
    except Exception:
        pass
    try:
        from src.exchanges import coinbase_candles
        from datetime import datetime, timezone
        gran = {"1h": 3600, "2h": 3600, "4h": 3600, "1D": 86400, "1W": 86400, "1M": 86400}.get(tf, 3600)
        rows = coinbase_candles(PRODUCT, gran, min(limit, 100))
        lines = [f"BTC-USD {tf} candles (live Coinbase fallback):"]
        for t, lo, h, o, c, v in sorted(rows)[-limit:]:
            dt = datetime.fromtimestamp(t, tz=timezone.utc).isoformat()
            lines.append(f"{dt}: O={o:.1f} H={h:.1f} L={lo:.1f} C={c:.1f} V={v:.4f}")
        return "\n".join(lines)
    except Exception as e:
        return f"Candle fetch failed: {type(e).__name__}: {e}"


@mcp.tool()
def options_chain(expiry_filter: str = "", limit: int = 30) -> str:
    """Deribit BTC option chain snapshot (mark, IV, OI). PG snapshot first, live fallback.

    Args:
        expiry_filter: e.g. 'DEC24', 'JAN25', '' for all.
        limit: max legs (1-100).
    """
    limit = max(1, min(int(limit), 100))
    filt = (expiry_filter or "").upper()
    try:
        from src import db
        cols, rows = db.query(
            """SELECT DISTINCT ON (instrument) instrument, strike, opt_type, mark, iv, oi, volume, ts
               FROM option_snapshots ORDER BY instrument, ts DESC"""
        )
        if rows:
            sel = [r for r in rows if not filt or filt in r[0].upper()][:limit]
            if sel:
                lines = [f"BTC options chain (PG snapshot, filter='{filt or 'all'}'):"]
                for inst, k, typ, mark, iv, oi, vol, ts in sel:
                    lines.append(f"{inst} K={k} {typ} mark={mark} iv={iv} oi={oi} vol={vol}")
                return "\n".join(lines)
    except Exception:
        pass
    try:
        from src.exchanges import deribit_book_summary
        rows = deribit_book_summary(CURRENCY)
        sel = [r for r in rows if not filt or filt in r["instrument_name"].upper()][:limit]
        lines = [f"BTC options chain (live Deribit, filter='{filt or 'all'}'):"]
        for r in sel:
            lines.append(f"{r['instrument_name']} mark={r.get('mark_price')} "
                         f"iv={r.get('mark_iv')} oi={r.get('open_interest')} vol={r.get('volume')}")
        return "\n".join(lines)
    except Exception as e:
        return f"Chain fetch failed: {type(e).__name__}: {e}"


@mcp.tool()
def option_quote(instrument: str) -> str:
    """Quote one Deribit instrument, e.g. BTC-PERPETUAL or BTC-27DEC24-100000-C."""
    try:
        from src.exchanges import deribit_ticker
        t = deribit_ticker(instrument)
        return json.dumps({k: t.get(k) for k in
                           ("instrument_name", "last_price", "mark_price", "bid_price",
                            "ask_price", "mark_iv", "open_interest", "volume")}, indent=2)
    except Exception as e:
        return f"Quote failed for {instrument}: {type(e).__name__}: {e}"


@mcp.tool()
def iv_skew(expiry_filter: str = "") -> str:
    """Strike vs IV skew lines for an expiry filter (from live book summary)."""
    filt = (expiry_filter or "").upper()
    try:
        from src.exchanges import deribit_book_summary
        rows = deribit_book_summary(CURRENCY)
        sel = [r for r in rows if not filt or filt in r["instrument_name"].upper()]
        calls, puts = [], []
        for r in sel:
            try:
                strike = float(r["instrument_name"].split("-")[2])
            except Exception:
                continue
            (calls if r["instrument_name"].endswith("-C") else puts).append((strike, r.get("mark_iv")))
        out = [f"IV skew (live, filter='{filt or 'all'}', {len(sel)} legs):"]
        for label, legs in (("CALL", sorted(calls)), ("PUT", sorted(puts))):
            out.append(f"-- {label} --")
            out += [f"K={k:.0f} iv={iv}" for k, iv in legs[:25]]
        return "\n".join(out)
    except Exception as e:
        return f"Skew failed: {type(e).__name__}: {e}"


@mcp.tool()
def db_status() -> str:
    """PG row counts + latest timestamps for ticks/snapshots/candles."""
    try:
        from src import db
        out = []
        for label, sql in (
            ("spot_ticks", "SELECT count(*), max(ts) FROM spot_ticks"),
            ("option_snapshots", "SELECT count(*), max(ts) FROM option_snapshots"),
            ("candles", "SELECT count(*), max(bucket) FROM candles"),
        ):
            cols, rows = db.query(sql)
            out.append(f"{label}: count={rows[0][0]} latest={rows[0][1]}")
        return "\n".join(out)
    except Exception as e:
        return f"DB offline: {type(e).__name__}: {e}. Start it: docker compose up -d db"


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--list-tools":
        import asyncio

        async def _list():
            for t in await mcp.list_tools():
                print(f"- {t.name}: {(t.description or '').splitlines()[0]}")

        asyncio.run(_list())
    elif len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        print(btc_price())
        print(btc_candles("1h", 3))
        print(db_status())
    else:
        mcp.run()
