"""Terminal dashboard: live price chart + option chain + paper account (rich).

Run:
    python -m src.tui --snapshot     # single render (pipe-safe)
    python -m src.tui                # live refresh every 5s, Ctrl+C to quit
"""
import argparse
from datetime import datetime

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from src import db


def sparkline(values, width=60, height=10):
    if not values:
        return "(no data)"
    vals = values[-width:]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    rows = []
    for r in range(height, 0, -1):
        line = ""
        for v in vals:
            lvl = (v - lo) / span * height
            line += "#" if lvl >= r - 0.5 else ("-" if lvl >= r - 1 else " ")
        rows.append(line)
    rows.append(f"{lo:.0f}{' ' * max(width - 20, 1)}{hi:.0f}")
    return "\n".join(rows)


def closes(timeframe="1h", n=60):
    try:
        cols, rows = db.query(
            "SELECT close FROM candles WHERE timeframe=%s ORDER BY bucket DESC LIMIT %s",
            (timeframe, n),
        )
        if rows:
            return [float(r[0]) for r in reversed(rows)]
    except Exception:
        pass
    return []


def price_now():
    try:
        cols, rows = db.query("SELECT price, ts FROM spot_ticks ORDER BY ts DESC LIMIT 1")
        if rows:
            return float(rows[0][0]), str(rows[0][1])
    except Exception:
        pass
    try:
        from src.exchanges import coinbase_trades
        t = coinbase_trades("BTC-USD", 1)[0]
        return float(t["price"]), t["time"] + " live"
    except Exception as e:
        return 0.0, f"offline {e}"


def chain_table(limit=12):
    t = Table(title="Option chain (top by volume)", show_header=True, expand=True)
    t.add_column("instrument", overflow="fold")
    for h in ("mark", "iv", "oi", "vol"):
        t.add_column(h)
    try:
        cols, rows = db.query(
            """SELECT DISTINCT ON (instrument) instrument, mark, iv, oi, volume
               FROM option_snapshots ORDER BY instrument, ts DESC"""
        )
        rows = sorted(rows, key=lambda r: (r[4] or 0), reverse=True)[:limit]
    except Exception:
        rows = []
    if not rows:
        try:
            from src.exchanges import deribit_book_summary
            live = sorted(deribit_book_summary("BTC"),
                          key=lambda r: (r.get("volume") or 0), reverse=True)[:limit]
            rows = [(r["instrument_name"], r.get("mark_price"), r.get("mark_iv"),
                     r.get("open_interest"), r.get("volume")) for r in live]
        except Exception as e:
            return Panel(f"chain offline: {e}", title="options")
    for inst, mark, iv, oi, vol in rows:
        t.add_row(str(inst), str(mark), str(iv), str(oi), str(vol))
    return t


def paper_panel():
    try:
        from src import paper as p
        s = p.summary()
        st = s["state"]
        eq = s["equity"] or (st["cash"] + st["qty"] * (price_now()[0] or 0))
        lines = [f"equity ${eq:,.0f}  cash ${st['cash']:,.0f}  pos {st['qty']} BTC "
                 f"entry {st['avg_entry']:.0f}  trades {s['n_trades']}  pnl ${s['total_pnl']:,.0f}"]
        for side, q, px, pnl, ts in s["recent"]:
            lines.append(f"{ts} {side} {q} @ {px:.0f} pnl {pnl}")
        return Panel("\n".join(lines), title="Paper account (no real money)")
    except Exception as e:
        return Panel(f"paper offline: {e}", title="Paper account")


def render():
    px, when = price_now()
    head = Panel(f"BTC-USD ${px:,.2f}  ({when})  {datetime.now().strftime('%H:%M:%S')}",
                 title="LIVE" if px else "OFFLINE")
    layout = Layout()
    layout.split_column(
        Layout(head, size=3),
        Layout(Panel(sparkline(closes("1h")), title="1h closes chart"), size=14),
        Layout(chain_table()),
        Layout(paper_panel(), size=10),
    )
    return layout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--refresh", type=int, default=5)
    a = ap.parse_args()
    con = Console()
    if a.snapshot:
        px, when = price_now()
        con.print(Panel(f"BTC-USD ${px:,.2f}  ({when})", title="LIVE" if px else "OFFLINE"))
        con.print(Panel(sparkline(closes("1h")), title="1h closes chart"))
        con.print(chain_table())
        con.print(paper_panel())
        return
    with Live(render(), console=con, refresh_per_second=1) as live:
        import time
        while True:
            time.sleep(a.refresh)
            live.update(render())


if __name__ == "__main__":
    main()
