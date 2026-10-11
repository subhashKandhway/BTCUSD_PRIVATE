"""Trend-following signal on paper account. Long/flat only, no leverage.

Signal (on timeframe closes, default 1h):
  BUY  if EMA12 > EMA26 and RSI14 < 70 and flat
  SELL if EMA12 < EMA26 and RSI14 > 30 and long
  else HOLD
SL/TP exit is enforced in bot.py against average entry.
"""
from src import db
from src.exchanges import coinbase_candles


def ema(values, span):
    k = 2 / (span + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def ema_series(values, span):
    k = 2 / (span + 1)
    out, e = [], values[0]
    for v in values:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def rsi(values, period=14):
    if len(values) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0:
        return 100.0 if ag else 50.0
    rs = ag / al
    return 100 - 100 / (1 + rs)


def get_closes(timeframe="1h", n=60, product="BTC-USD"):
    try:
        cols, rows = db.query(
            "SELECT close FROM candles WHERE timeframe=%s ORDER BY bucket DESC LIMIT %s",
            (timeframe, n),
        )
        if len(rows) >= 30:
            return [float(r[0]) for r in reversed(rows)]
    except Exception:
        pass
    gran = {"1h": 3600, "1D": 86400}.get(timeframe, 3600)
    rows = coinbase_candles(product, gran, n)
    return [c for _, _, _, _, c, _ in sorted(rows)]


def decide(timeframe="1h", product="BTC-USD"):
    closes = get_closes(timeframe, 60, product)
    price = closes[-1]
    f, s, r = ema(closes, 12), ema(closes, 26), rsi(closes)
    if f > s and r < 70:
        return {"action": "BUY", "price": price, "fast": f, "slow": s, "rsi": r,
                "reason": f"EMA12 {f:.0f} > EMA26 {s:.0f}, RSI {r:.0f}"}
    if f < s and r > 30:
        return {"action": "SELL", "price": price, "fast": f, "slow": s, "rsi": r,
                "reason": f"EMA12 {f:.0f} < EMA26 {s:.0f}, RSI {r:.0f}"}
    return {"action": "HOLD", "price": price, "fast": f, "slow": s, "rsi": r,
            "reason": f"no cross (EMA12 {f:.0f} vs {s:.0f}, RSI {r:.0f})"}
