import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import time


BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "auction.sqlite3"
IST = timezone(timedelta(hours=5, minutes=30))
TRIGGERS = {
    "bid": "Any accepted bid",
    "rank": "Any supplier rank change",
    "leader": "Lowest bidder (L1) changes",
}


def connect():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db():
    with closing(connect()) as db:
        db.executescript((BASE_DIR / "schema.sql").read_text(encoding="utf-8"))


def now_seconds():
    return int(time())


def parse_time(value):
    try:
        local_time = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        raise ValueError("Enter a valid date and time.") from None
    return int(local_time.replace(tzinfo=IST).timestamp())


def display_time(timestamp):
    return datetime.fromtimestamp(timestamp, IST).strftime("%d %b %Y, %H:%M:%S")


def display_money(paise):
    if paise is None:
        return "—"
    rupees, fraction = divmod(paise, 100)
    return f"₹{rupees:,}.{fraction:02d}"


def parse_charge(value):
    try:
        charge = Decimal(value)
    except InvalidOperation:
        raise ValueError("Enter valid amounts for all three charges.") from None
    if not charge.is_finite() or not 0 <= charge <= 100_000_000:
        raise ValueError("Each charge must be between ₹0 and ₹100,000,000.")
    paise = charge * 100
    if paise != paise.to_integral_value():
        raise ValueError("Charges may have at most two decimal places.")
    return int(paise)


def status(rfq, now):
    if now < rfq["bid_start"]:
        return "Scheduled"
    if now < rfq["current_close"]:
        return "Active"
    if rfq["current_close"] == rfq["forced_close"]:
        return "Force Closed"
    return "Closed"


def rank_bids(bids):
    latest = {}
    for bid in bids:
        key = bid["carrier_key"]
        if key not in latest or bid["id"] > latest[key]["id"]:
            latest[key] = bid
    return sorted(latest.values(), key=lambda bid: (bid["total"], bid["id"]))


def extension_reason(trigger, before, after):
    if trigger == "bid":
        return "An accepted bid arrived in the trigger window."
    if trigger == "leader":
        if before and before[0]["carrier_key"] != after[0]["carrier_key"]:
            return f"L1 changed from {before[0]['carrier_name']} to {after[0]['carrier_name']}."
        return None

    new_positions = {
        bid["carrier_key"]: position for position, bid in enumerate(after, start=1)
    }
    for old_position, bid in enumerate(before, start=1):
        new_position = new_positions[bid["carrier_key"]]
        if new_position != old_position:
            return f"{bid['carrier_name']} moved from L{old_position} to L{new_position}."
    return None


def get_bids(db, rfq_id):
    return db.execute(
        "SELECT * FROM bids WHERE rfq_id = ? ORDER BY total, id", (rfq_id,)
    ).fetchall()


def create_rfq(form):
    name = form["name"].strip()
    start = parse_time(form["bid_start"])
    initial = parse_time(form["initial_close"])
    forced = parse_time(form["forced_close"])
    service_date = date.fromisoformat(form["service_date"]).isoformat()
    trigger_minutes = int(form["trigger_minutes"])
    extension_minutes = int(form["extension_minutes"])
    trigger_type = form["trigger_type"]

    if not name or len(name) > 100:
        raise ValueError("Enter an RFQ name of up to 100 characters.")
    if not start < initial < forced:
        raise ValueError("The start, initial close, and forced close must be in that order.")
    if not 1 <= trigger_minutes <= 1440 or not 1 <= extension_minutes <= 1440:
        raise ValueError("Enter a window and extension between 1 and 1440 minutes.")
    if trigger_type not in TRIGGERS:
        raise ValueError("Select a valid extension trigger.")

    with closing(connect()) as db, db:
        cursor = db.execute(
            """
            INSERT INTO rfqs (
                name, service_date, bid_start, initial_close, current_close,
                forced_close, trigger_minutes, extension_minutes, trigger_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, service_date, start, initial, initial, forced,
             trigger_minutes, extension_minutes, trigger_type),
        )
        return cursor.lastrowid


def submit_bid(rfq_id, form):
    carrier = " ".join(form["carrier_name"].split())
    carrier_key = carrier.casefold()
    freight, origin, destination = (
        parse_charge(form[field]) for field in ("freight", "origin", "destination")
    )
    total = freight + origin + destination
    transit_days = int(form["transit_days"])
    valid_until = date.fromisoformat(form["valid_until"])
    if not carrier or len(carrier) > 100:
        raise ValueError("Enter a carrier name of up to 100 characters.")
    if total <= 0 or not 1 <= transit_days <= 3650:
        raise ValueError("Enter a positive total and a transit time from 1 to 3650 days.")

    with closing(connect()) as db, db:
        # Reserve the write transaction before reading the deadline and ranks.
        db.execute("BEGIN IMMEDIATE")
        rfq = db.execute("SELECT * FROM rfqs WHERE id = ?", (rfq_id,)).fetchone()
        if rfq is None:
            raise LookupError("RFQ not found.")
        now = now_seconds()
        bid_status = status(rfq, now)
        if bid_status == "Scheduled":
            raise ValueError("Bidding has not started yet.")
        if bid_status != "Active":
            raise ValueError("Bidding is closed for this RFQ.")
        if valid_until < datetime.fromtimestamp(now, IST).date():
            raise ValueError("Quote validity cannot end before today.")

        bids = get_bids(db, rfq_id)
        before = rank_bids(bids)
        for bid in before:
            if bid["carrier_key"] == carrier_key and total >= bid["total"]:
                raise ValueError("A revised bid must be lower than your previous bid.")

        cursor = db.execute(
            """
            INSERT INTO bids (
                rfq_id, carrier_name, carrier_key, freight, origin, destination,
                total, transit_days, valid_until, submitted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (rfq_id, carrier, carrier_key, freight, origin, destination,
             total, transit_days, valid_until.isoformat(), now),
        )
        bid_id = cursor.lastrowid
        db.execute(
            "INSERT INTO activity_log (bid_id, event_type, reason) VALUES (?, 'bid', ?)",
            (bid_id, f"{carrier} submitted a bid of {display_money(total)}."),
        )

        close = rfq["current_close"]
        if now >= close - rfq["trigger_minutes"] * 60 and close < rfq["forced_close"]:
            new_bid = {"id": bid_id, "carrier_key": carrier_key,
                       "carrier_name": carrier, "total": total}
            reason = extension_reason(rfq["trigger_type"], before, rank_bids([*bids, new_bid]))
            if reason:
                new_close = min(close + rfq["extension_minutes"] * 60, rfq["forced_close"])
                db.execute("UPDATE rfqs SET current_close = ? WHERE id = ?", (new_close, rfq_id))
                db.execute(
                    """
                    INSERT INTO activity_log (bid_id, event_type, reason, old_close, new_close)
                    VALUES (?, 'extension', ?, ?, ?)
                    """,
                    (bid_id, reason, close, new_close),
                )
