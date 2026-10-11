"""Build 1h/2h/4h/1D/1W/1M candles.

Two paths:
  1. rebuild_from_ticks() - aggregate local spot_ticks (needs collector running).
  2. rebuild_from_coinbase() - pull Coinbase REST candles (works with no ticks, always available).
MCP reads from `candles` first, falls back to live REST.
"""
from datetime import datetime, timezone

from src import db
from src.exchanges import coinbase_candles

TF_SECONDS = {"1h": 3600, "2h": 7200, "4h": 14400, "1D": 86400, "1W": 604800, "1M": 2592000}
# Coinbase only serves these granularities; others are resampled from 1h.
CB_GRAN = {"1h": 3600, "2h": 7200, "4h": 14400, "1D": 86400}


def _bucket_floor(ts_epoch, secs):
    return int(ts_epoch // secs) * secs


def resample_ohlc(rows, factor, secs):
    """rows: list of (bucket_epoch, o,h,l,c, vol) sorted asc -> resampled to secs buckets."""
    out = []
    for i in range(0, len(rows), factor):
        chunk = rows[i:i + factor]
        if not chunk:
            continue
        b = _bucket_floor(chunk[0][0], secs)
        o = chunk[0][1]
        c = chunk[-1][4]
        h = max(x[2] for x in chunk)
        lo = min(x[3] for x in chunk)
        v = sum(x[5] for x in chunk)
        out.append((b, o, h, lo, c, v))
    return out


def rebuild_from_coinbase(product="BTC-USD", limit_1h=300):
    rows1h = coinbase_candles(product, 3600, limit_1h)  # [time,low,high,open,close,vol]
    norm1h = sorted((t, o, h, lo, c, v) for t, lo, h, o, c, v in rows1h)
    rows_d = coinbase_candles(product, 86400, 300)
    norm_d = sorted((t, o, h, lo, c, v) for t, lo, h, o, c, v in rows_d)
    data = {
        "1h": norm1h,
        "2h": resample_ohlc(norm1h, 2, 7200),
        "4h": resample_ohlc(norm1h, 4, 14400),
        "1D": norm_d,
        "1W": resample_ohlc(norm_d, 7, 604800),
        "1M": resample_ohlc(norm_d, 30, 2592000),
    }
    up = []
    for tf, rows in data.items():
        for b, o, h, lo, c, v in rows:
            dt = datetime.fromtimestamp(b, tz=timezone.utc)
            n_trades = 0
            vwap = c
            up.append((tf, dt, o, h, lo, c, v, vwap, n_trades))
    return db.upsert_candles(up)


def rebuild_from_ticks():
    total = 0
    for tf, secs in TF_SECONDS.items():
        cols, rows = db.query(
            """SELECT to_timestamp(floor(extract(epoch from ts)/%s)*%s) AS b,
                      (array_agg(price ORDER BY ts))[1] AS o,
                      max(price) AS h, min(price) AS l,
                      (array_agg(price ORDER BY ts DESC))[1] AS c,
                      sum(size) AS v,
                      sum(price*size)/nullif(sum(size),0) AS vwap,
                      count(*) AS n
               FROM spot_ticks WHERE ts > now() - interval '45 days'
               GROUP BY 1 ORDER BY 1""",
            (secs, secs),
        )
        up = [(tf, b, o, h, lo, c, v or 0, vwap, n) for b, o, h, lo, c, v, vwap, n in rows]
        total += db.upsert_candles(up)
    return total
