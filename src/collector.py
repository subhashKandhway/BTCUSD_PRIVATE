"""Live websocket collector: Coinbase BTC-USD ticks + Deribit option chain snapshots -> Postgres.

Run:
    python -m src.collector --once        # one REST snapshot (no infinite loop)
    python -m src.collector               # infinite WS loops
"""
import argparse
import asyncio
import json
from datetime import datetime, timezone

import websockets

from src import db
from src.exchanges import coinbase_trades, deribit_book_summary, deribit_instruments

COINBASE_WS = "wss://ws-feed.exchange.coinbase.com"
DERIBIT_WS = "wss://www.deribit.com/ws/api/v2"


def _parse_opt_name(name):
    # BTC-27DEC24-100000-C
    try:
        _, exp, strike, typ = name.split("-")
        return exp, float(strike), typ
    except Exception:
        return None, None, None


async def coinbase_loop(product="BTC-USD"):
    while True:
        try:
            async with websockets.connect(COINBASE_WS, max_size=2**20) as ws:
                await ws.send(json.dumps({
                    "type": "subscribe",
                    "channels": [{"name": "matches", "product_ids": [product]}],
                }))
                buf = []
                async for msg in ws:
                    d = json.loads(msg)
                    if d.get("type") != "match":
                        continue
                    buf.append((d["time"], float(d["price"]), float(d["size"]),
                                d.get("side"), int(d["trade_id"])))
                    if len(buf) >= 200:
                        try:
                            db.insert_ticks(buf)
                        except Exception as e:
                            print("tick insert failed:", e)
                        buf.clear()
        except Exception as e:
            print("coinbase ws reconnect:", e)
            await asyncio.sleep(5)


async def prune_loop(interval=3600):
    """Hourly DELETE of rows older than retention so the DB stays small."""
    from src.prune import prune
    while True:
        try:
            print("prune:", prune())
        except Exception as e:
            print("prune failed:", e)
        await asyncio.sleep(interval)


async def deribit_loop(currency="BTC", interval=60):
    """Poll book summary (full chain snapshot) + persist. WS ticker loop optional."""
    while True:
        try:
            rows = deribit_book_summary(currency)
            now = datetime.now(timezone.utc)
            out = []
            for r in rows:
                exp, strike, typ = _parse_opt_name(r["instrument_name"])
                out.append((now, r["instrument_name"], None, strike, typ,
                            r.get("bid_price"), r.get("ask_price"), r.get("mark_price"),
                            r.get("mark_iv"), r.get("open_interest"), r.get("volume"),
                            r.get("delta")))
            try:
                db.insert_option_snapshots(out)
                print(f"options snapshot: {len(out)} instruments")
            except Exception as e:
                print("option insert failed:", e)
        except Exception as e:
            print("deribit snapshot failed:", e)
        await asyncio.sleep(interval)


def once(product="BTC-USD", currency="BTC"):
    db.init_db()
    trades = coinbase_trades(product)
    rows = [(t["time"], float(t["price"]), float(t["size"]), t.get("side"), int(t["trade_id"]))
            for t in trades]
    print("coinbase REST ticks:", db.insert_ticks(rows))
    try:
        inst = deribit_instruments(currency)
        print("deribit instruments:", len(inst))
        rows = deribit_book_summary(currency)
        now = datetime.now(timezone.utc)
        out = []
        for r in rows:
            _, strike, typ = _parse_opt_name(r["instrument_name"])
            out.append((now, r["instrument_name"], None, strike, typ,
                        r.get("bid_price"), r.get("ask_price"), r.get("mark_price"),
                        r.get("mark_iv"), r.get("open_interest"), r.get("volume"),
                        r.get("delta")))
        print("option snapshots:", db.insert_option_snapshots(out))
    except Exception as e:
        print("deribit once failed:", e)
    from src.aggregator import rebuild_from_coinbase
    print("candles upserted:", rebuild_from_coinbase(product))
    from src.prune import prune
    print("pruned:", prune())


async def main(product, currency):
    db.init_db()
    await asyncio.gather(coinbase_loop(product), deribit_loop(currency), prune_loop())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--product", default="BTC-USD")
    ap.add_argument("--currency", default="BTC")
    a = ap.parse_args()
    if a.once:
        once(a.product, a.currency)
    else:
        asyncio.run(main(a.product, a.currency))
