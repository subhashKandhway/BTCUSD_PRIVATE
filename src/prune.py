"""Auto-prune raw tables so the DB stays small. Candles are kept (tiny).

Retention (days, env-overridable):
  TICKS_RETENTION_DAYS=7      -> spot_ticks
  OPTIONS_RETENTION_DAYS=7    -> option_snapshots

Run:
    python -m src.prune                 # one pass
    (collector runs this hourly automatically)
"""
import argparse
import os

from dotenv import load_dotenv

load_dotenv()

TICKS_DAYS = int(os.getenv("TICKS_RETENTION_DAYS", "7"))
OPTIONS_DAYS = int(os.getenv("OPTIONS_RETENTION_DAYS", "7"))


def prune(ticks_days=TICKS_DAYS, options_days=OPTIONS_DAYS):
    from src import db

    out = {}
    for label, sql, days in (
        ("spot_ticks", "DELETE FROM spot_ticks WHERE ts < now() - (%s || ' days')::interval", ticks_days),
        ("option_snapshots", "DELETE FROM option_snapshots WHERE ts < now() - (%s || ' days')::interval", options_days),
    ):
        with db.conn() as c, c.cursor() as cur:
            cur.execute(sql, (str(days),))
            out[label] = cur.rowcount
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks-days", type=int, default=TICKS_DAYS)
    ap.add_argument("--options-days", type=int, default=OPTIONS_DAYS)
    a = ap.parse_args()
    print(prune(a.ticks_days, a.options_days))
