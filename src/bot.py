"""24x7 autonomous PAPER trading bot. PAPER ONLY — reads charts, writes paper ledger.

Loop: price -> signal (EMA12/26 + RSI14) -> SL/TP check -> paper trade -> equity snapshot.
You don't need to watch it; it logs every decision. Nothing here places real orders.

Run:
    python -m src.bot --once                  # single decision cycle (test)
    python -m src.bot                         # infinite loop, --interval 60s
    python -m src.bot --qty 0.02 --sl 0.03 --tp 0.06 --timeframe 4h
"""
import argparse
import time
from datetime import datetime, timezone

from src import db
from src import paper, strategy


def live_price(product="BTC-USD"):
    try:
        cols, rows = db.query("SELECT price FROM spot_ticks ORDER BY ts DESC LIMIT 1")
        if rows:
            return float(rows[0][0]), "pg"
    except Exception:
        pass
    from src.exchanges import coinbase_trades
    t = coinbase_trades(product, 1)[0]
    return float(t["price"]), "live"


def cycle(args):
    paper.ensure()
    price, src = live_price(args.product)
    sig = strategy.decide(args.timeframe, args.product)
    st = paper.state()
    action, reason = sig["action"], sig["reason"]
    # SL/TP override when long
    if st["qty"] > 0 and st["avg_entry"] > 0:
        ret = (price - st["avg_entry"]) / st["avg_entry"]
        if ret <= -args.sl:
            action, reason = "SELL", f"STOP-LOSS {ret*100:.2f}% <= -{args.sl*100:.1f}%"
        elif ret >= args.tp:
            action, reason = "SELL", f"TAKE-PROFIT {ret*100:.2f}% >= {args.tp*100:.1f}%"
    result = None
    if action == "BUY" and st["qty"] <= 0:
        result = paper.trade("BUY", args.qty, price, f"{sig['reason']} [{src}]")
    elif action == "SELL" and st["qty"] > 0:
        result = paper.trade("SELL", min(args.qty, st["qty"]), price, f"{reason} [{src}]")
    snap = paper.snapshot(price)
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = (f"{now} px={price:.0f} sig={sig['action']} pos={st['qty']} "
            f"eq={snap['equity']:.0f} | {reason}")
    if result:
        line += f" -> {result}"
    print(line, flush=True)
    return {"price": price, "signal": sig, "trade": result, "account": snap}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--qty", type=float, default=0.01)
    ap.add_argument("--sl", type=float, default=0.02)
    ap.add_argument("--tp", type=float, default=0.04)
    ap.add_argument("--timeframe", default="1h")
    ap.add_argument("--product", default="BTC-USD")
    a = ap.parse_args()
    db.init_db()
    paper.ensure()
    print(f"paper bot start: qty={a.qty} sl={a.sl} tp={a.tp} tf={a.timeframe} (PAPER ONLY)")
    if a.once:
        print(cycle(a))
        return
    while True:
        try:
            cycle(a)
        except Exception as e:
            print("bot cycle failed:", type(e).__name__, e, flush=True)
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
