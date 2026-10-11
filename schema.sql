-- Small BTCUSD store: raw ticks (short retention) + snapshots + rolled-up candles.
CREATE TABLE IF NOT EXISTS spot_ticks (
  ts TIMESTAMPTZ NOT NULL,
  price DOUBLE PRECISION NOT NULL,
  size DOUBLE PRECISION NOT NULL,
  side TEXT,
  trade_id BIGINT
);
CREATE INDEX IF NOT EXISTS ix_spot_ticks_ts ON spot_ticks (ts DESC);

CREATE TABLE IF NOT EXISTS option_snapshots (
  ts TIMESTAMPTZ NOT NULL,
  instrument TEXT NOT NULL,
  expiry DATE,
  strike DOUBLE PRECISION,
  opt_type TEXT,
  bid DOUBLE PRECISION,
  ask DOUBLE PRECISION,
  mark DOUBLE PRECISION,
  iv DOUBLE PRECISION,
  oi DOUBLE PRECISION,
  volume DOUBLE PRECISION,
  delta DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS ix_opt_snap_ts ON option_snapshots (ts DESC);
CREATE INDEX IF NOT EXISTS ix_opt_snap_inst ON option_snapshots (instrument, ts DESC);

-- One table for all timeframes keeps the DB small.
-- timeframe in ('1h','2h','4h','1D','1W','1M')
CREATE TABLE IF NOT EXISTS candles (
  timeframe TEXT NOT NULL,
  bucket TIMESTAMPTZ NOT NULL,
  open DOUBLE PRECISION NOT NULL,
  high DOUBLE PRECISION NOT NULL,
  low DOUBLE PRECISION NOT NULL,
  close DOUBLE PRECISION NOT NULL,
  volume DOUBLE PRECISION NOT NULL DEFAULT 0,
  vwap DOUBLE PRECISION,
  trades INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (timeframe, bucket)
);
