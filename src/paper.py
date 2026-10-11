"""Paper ledger in Postgres. PAPER ONLY — never touches real orders.

Tables (created by ensure()):
  paper_state(id=1, cash, qty, avg_entry, updated)
  paper_trades(id serial, ts, side, qty, price, reason, cash_after, qty_after, pnl)
  paper_equity(ts, equity, price, qty, cash)
Start: $100,000 cash, 0 BTC.
"""
from src import db

START_CASH = 100_000.0


def ensure():
    with db.conn() as c, c.cursor() as cur:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS paper_state
               (id INT PRIMARY KEY, cash DOUBLE PRECISION, qty DOUBLE PRECISION,
                avg_entry DOUBLE PRECISION, updated TIMESTAMPTZ DEFAULT now())"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS paper_trades
               (id SERIAL PRIMARY KEY, ts TIMESTAMPTZ DEFAULT now(), side TEXT,
                qty DOUBLE PRECISION, price DOUBLE PRECISION, reason TEXT,
                cash_after DOUBLE PRECISION, qty_after DOUBLE PRECISION, pnl DOUBLE PRECISION)"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS paper_equity
               (ts TIMESTAMPTZ DEFAULT now(), equity DOUBLE PRECISION,
                price DOUBLE PRECISION, qty DOUBLE PRECISION, cash DOUBLE PRECISION)"""
        )
        cur.execute(
            "INSERT INTO paper_state (id, cash, qty, avg_entry) VALUES (1,%s,0,0) "
            "ON CONFLICT (id) DO NOTHING",
            (START_CASH,),
        )


def state():
    cols, rows = db.query("SELECT cash, qty, avg_entry, updated FROM paper_state WHERE id=1")
    cash, qty, entry, upd = rows[0]
    return {"cash": float(cash), "qty": float(qty), "avg_entry": float(entry or 0), "updated": upd}


def trade(side, qty, price, reason):
    """side BUY/SELL. BUY spends cash, SELL realizes pnl vs avg_entry. Returns trade row."""
    ensure()
    st = state()
    cash, q, entry = st["cash"], st["qty"], st["avg_entry"]
    pnl = 0.0
    if side == "BUY":
        cost = qty * price
        if cost > cash:
            return {"ok": False, "error": f"insufficient cash {cash:.0f} for {cost:.0f}"}
        cash -= cost
        entry = (entry * q + cost) / (q + qty) if q + qty else price
        q += qty
    else:
        if qty > q:
            return {"ok": False, "error": f"insufficient qty {q} for {qty}"}
        proceeds = qty * price
        pnl = (price - entry) * qty
        cash += proceeds
        q -= qty
        if q <= 1e-9:
            q, entry = 0.0, 0.0
    with db.conn() as c, c.cursor() as cur:
        cur.execute(
            "UPDATE paper_state SET cash=%s, qty=%s, avg_entry=%s, updated=now() WHERE id=1",
            (cash, q, entry),
        )
        cur.execute(
            """INSERT INTO paper_trades (side, qty, price, reason, cash_after, qty_after, pnl)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id, ts""",
            (side, qty, price, reason, cash, q, pnl),
        )
        tid, ts = cur.fetchone()
    return {"ok": True, "id": tid, "ts": str(ts), "side": side, "qty": qty,
            "price": price, "pnl": round(pnl, 2), "cash": round(cash, 2), "pos": round(q, 6)}


def snapshot(price):
    st = state()
    equity = st["cash"] + st["qty"] * price
    with db.conn() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO paper_equity (equity, price, qty, cash) VALUES (%s,%s,%s,%s)",
            (equity, price, st["qty"], st["cash"]),
        )
    return {"equity": round(equity, 2), "cash": round(st["cash"], 2),
            "qty": st["qty"], "price": price}


def summary():
    ensure()
    st = state()
    cols, last = db.query("SELECT equity FROM paper_equity ORDER BY ts DESC LIMIT 1")
    cols, tr = db.query("SELECT side, qty, price, pnl, ts FROM paper_trades ORDER BY id DESC LIMIT 5")
    cols, agg = db.query("SELECT count(*), coalesce(sum(pnl),0) FROM paper_trades")
    return {"state": st, "equity": last[0][0] if last else None,
            "recent": tr, "n_trades": agg[0][0], "total_pnl": round(float(agg[0][1]), 2)}
