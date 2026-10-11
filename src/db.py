"""DB helpers: connect via DATABASE_URL, init schema, small insert/query API."""
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://btc:btc@localhost:5433/btcusd")
SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"


def conn():
    return psycopg.connect(DATABASE_URL, autocommit=True)


def init_db():
    sql = SCHEMA.read_text()
    with conn() as c, c.cursor() as cur:
        cur.execute(sql)


def insert_ticks(rows):
    """rows: list of (ts, price, size, side, trade_id). ts ISO string or datetime."""
    if not rows:
        return 0
    with conn() as c, c.cursor() as cur:
        cur.executemany(
            "INSERT INTO spot_ticks (ts, price, size, side, trade_id) VALUES (%s,%s,%s,%s,%s)",
            rows,
        )
    return len(rows)


def insert_option_snapshots(rows):
    if not rows:
        return 0
    with conn() as c, c.cursor() as cur:
        cur.executemany(
            """INSERT INTO option_snapshots
               (ts, instrument, expiry, strike, opt_type, bid, ask, mark, iv, oi, volume, delta)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            rows,
        )
    return len(rows)


def upsert_candles(rows):
    """rows: list of (timeframe, bucket, o,h,l,c, volume, vwap, trades)."""
    if not rows:
        return 0
    with conn() as c, c.cursor() as cur:
        cur.executemany(
            """INSERT INTO candles (timeframe, bucket, open, high, low, close, volume, vwap, trades)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (timeframe, bucket) DO UPDATE SET
                 open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                 close=EXCLUDED.close, volume=EXCLUDED.volume,
                 vwap=EXCLUDED.vwap, trades=EXCLUDED.trades""",
            rows,
        )
    return len(rows)


def query(sql, params=()):
    with conn() as c, c.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description] if cur.description else []
        return cols, cur.fetchall()
