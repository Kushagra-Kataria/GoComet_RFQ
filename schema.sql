CREATE TABLE IF NOT EXISTS rfqs (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    service_date TEXT NOT NULL,
    bid_start INTEGER NOT NULL,
    initial_close INTEGER NOT NULL,
    current_close INTEGER NOT NULL,
    forced_close INTEGER NOT NULL,
    trigger_minutes INTEGER NOT NULL CHECK (trigger_minutes > 0),
    extension_minutes INTEGER NOT NULL CHECK (extension_minutes > 0),
    trigger_type TEXT NOT NULL CHECK (trigger_type IN ('bid', 'rank', 'leader')),
    CHECK (bid_start < initial_close AND initial_close < forced_close),
    CHECK (initial_close <= current_close AND current_close <= forced_close)
);

CREATE TABLE IF NOT EXISTS bids (
    id INTEGER PRIMARY KEY,
    rfq_id INTEGER NOT NULL REFERENCES rfqs(id),
    carrier_name TEXT NOT NULL,
    carrier_key TEXT NOT NULL,
    freight INTEGER NOT NULL CHECK (freight >= 0),
    origin INTEGER NOT NULL CHECK (origin >= 0),
    destination INTEGER NOT NULL CHECK (destination >= 0),
    total INTEGER NOT NULL CHECK (total = freight + origin + destination AND total > 0),
    transit_days INTEGER NOT NULL CHECK (transit_days > 0),
    valid_until TEXT NOT NULL,
    submitted_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS bids_rfq ON bids(rfq_id);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY,
    bid_id INTEGER NOT NULL REFERENCES bids(id),
    event_type TEXT NOT NULL CHECK (event_type IN ('bid', 'extension')),
    reason TEXT NOT NULL,
    old_close INTEGER,
    new_close INTEGER,
    UNIQUE (bid_id, event_type)
);
