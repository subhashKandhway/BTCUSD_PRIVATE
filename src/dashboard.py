"""View-only web terminal: watch the paper bot live. READ ONLY - no trade buttons.

Run:
    python -m src.dashboard            # serves http://localhost:8765
Open that URL in your browser; it refreshes every 5 seconds.
"""
import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>BTCUSD Paper Terminal (view only)</title>
<style>
body{font-family:Consolas,monospace;background:#0d1117;color:#c9d1d9;margin:0;padding:16px}
h1{font-size:18px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px}
.big{font-size:28px}.green{color:#3fb950}.red{color:#f85149}.dim{color:#8b949e}
table{width:100%;border-collapse:collapse;font-size:12px}
td,th{border-bottom:1px solid #30363d;padding:4px 6px;text-align:right}
td:first-child,th:first-child{text-align:left}
canvas{width:100%;height:120px;background:#0d1117}
.badge{padding:2px 10px;border-radius:10px;font-weight:bold}
</style></head><body>
<h1>BTCUSD Paper Terminal <span class="dim">(view only - bot trades by itself)</span></h1>
<div class="grid">
<div class="card"><div class="dim">PRICE</div><div class="big" id="px">-</div><div class="dim" id="pxts"></div></div>
<div class="card"><div class="dim">SIGNAL</div><div class="big" id="sig">-</div><div class="dim" id="reason"></div></div>
</div><br><div class="grid">
<div class="card"><div class="dim">POSITION / ACCOUNT</div><div id="acct">-</div></div>
<div class="card"><div class="dim">EQUITY CURVE</div><canvas id="eq" width="600" height="120"></canvas></div>
</div><br><div class="grid">
<div class="card"><div class="dim">PRICE (1h closes)</div><canvas id="ch" width="600" height="120"></canvas></div>
<div class="card"><div class="dim">RECENT PAPER TRADES</div><div id="trades">-</div></div>
</div><br>
<div class="card"><div class="dim">OPTION CHAIN (top by volume)</div><div id="chain">-</div></div>
<script>
function draw(id, vals, color){
  const c=document.getElementById(id), x=c.getContext('2d');
  x.clearRect(0,0,c.width,c.height); if(!vals.length) return;
  const lo=Math.min(...vals), hi=Math.max(...vals), sp=(hi-lo)||1;
  x.strokeStyle=color||'#3fb950'; x.beginPath();
  vals.forEach((v,i)=>{const px=i/(vals.length-1)*c.width, py=c.height-4-((v-lo)/sp)*(c.height-8);
    i?x.lineTo(px,py):x.moveTo(px,py);});
  x.stroke();
}
async function tick(){
  const d=await (await fetch('/api/data')).json();
  document.getElementById('px').textContent='$'+Number(d.price).toLocaleString();
  document.getElementById('pxts').textContent=d.price_ts+' ('+d.price_src+')';
  const s=document.getElementById('sig');
  s.innerHTML='<span class="badge" style="background:'+(d.signal.action==='BUY'?'#0a3d1f':'#3d0a0a')+'">'+d.signal.action+'</span>';
  document.getElementById('reason').textContent=d.signal.reason+' ['+d.signal.timeframe+']';
  const a=d.account;
  document.getElementById('acct').innerHTML=
    'Equity <b>$'+Number(a.equity).toLocaleString()+'</b> &nbsp; Cash $'+Number(a.cash).toLocaleString()+
    '<br>Position <b>'+a.qty+' BTC</b> @ '+Math.round(a.avg_entry)+
    '<br>Trades '+a.n_trades+' &nbsp; Total PnL <b class="'+(a.total_pnl>=0?'green':'red')+'">$'+a.total_pnl+'</b>';
  draw('eq', d.equity_curve); draw('ch', d.closes, '#58a6ff');
  document.getElementById('trades').innerHTML='<table><tr><th>time</th><th>side</th><th>qty</th><th>price</th><th>pnl</th></tr>'+
    d.recent.map(t=>'<tr><td>'+t[4]+'</td><td>'+t[0]+'</td><td>'+t[1]+'</td><td>'+Math.round(t[2])+'</td><td>'+t[3]+'</td></tr>').join('')+'</table>';
  document.getElementById('chain').innerHTML='<table><tr><th>instrument</th><th>mark</th><th>iv</th><th>oi</th><th>vol</th></tr>'+
    d.chain.map(r=>'<tr><td>'+r[0]+'</td><td>'+r[1]+'</td><td>'+r[2]+'</td><td>'+r[3]+'</td><td>'+r[4]+'</td></tr>').join('')+'</table>';
}
tick(); setInterval(tick, 5000);
</script></body></html>"""


def snapshot():
    from src import db
    from src import paper as paper_mod
    from src import strategy

    try:
        cols, rows = db.query("SELECT price, ts FROM spot_ticks ORDER BY ts DESC LIMIT 1")
        price, ts, src = float(rows[0][0]), str(rows[0][1]), "pg"
    except Exception:
        from src.exchanges import coinbase_trades
        t = coinbase_trades("BTC-USD", 1)[0]
        price, ts, src = float(t["price"]), t["time"], "live"
    try:
        sig = strategy.decide("1h")
    except Exception as e:
        sig = {"action": "?", "reason": str(e), "price": price, "timeframe": "1h"}
    sig["timeframe"] = "1h"
    try:
        s = paper_mod.summary()
        st = s["state"]
        eq = s["equity"] if s["equity"] is not None else st["cash"] + st["qty"] * price
        cols, curve = db.query("SELECT equity FROM paper_equity ORDER BY ts DESC LIMIT 100")
        curve = [float(r[0]) for r in reversed(curve)] or [eq]
        acct = {"equity": round(float(eq), 2), "cash": round(st["cash"], 2), "qty": st["qty"],
                "avg_entry": round(st["avg_entry"], 2), "n_trades": s["n_trades"],
                "total_pnl": s["total_pnl"]}
        recent = [[r[0], r[1], r[2], r[3], str(r[4])] for r in s["recent"]]
    except Exception as e:
        acct = {"equity": 0, "cash": 0, "qty": 0, "avg_entry": 0, "n_trades": 0,
                "total_pnl": 0, "error": str(e)}
        recent, curve = [], [price]
    try:
        cols, rows = db.query("SELECT close FROM candles WHERE timeframe='1h' ORDER BY bucket DESC LIMIT 60")
        closes = [float(r[0]) for r in reversed(rows)]
    except Exception:
        closes = []
    try:
        cols, rows = db.query(
            "SELECT DISTINCT ON (instrument) instrument, mark, iv, oi, volume "
            "FROM option_snapshots ORDER BY instrument, ts DESC")
        chain = sorted(
            [[r[0], r[1], r[2], r[3], r[4]] for r in rows],
            key=lambda r: (r[4] or 0), reverse=True)[:12]
    except Exception:
        chain = []
    return {"price": price, "price_ts": ts, "price_src": src, "signal": sig,
            "account": acct, "recent": recent, "equity_curve": curve,
            "closes": closes, "chain": chain}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
        elif self.path == "/api/data":
            try:
                body = json.dumps(snapshot(), default=str).encode()
            except Exception as e:
                body = json.dumps({"error": str(e)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        else:
            self.send_response(404)
            body = b"not found"
            self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"view-only terminal: http://localhost:{a.port} (READ ONLY, bot trades by itself)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
