# British Auction for RFQs

A local FastAPI reference implementation for the RFQ assignment.

## Run on Windows

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app:app
```

Open [the auction listing](http://127.0.0.1:8000) or [FastAPI's interactive docs](http://127.0.0.1:8000/docs). SQLite creates `auction.sqlite3` on first startup.

## Project files

| File | Purpose |
| --- | --- |
| `HLD.md` | Architecture diagram, bid flow, and rule decisions |
| `schema.sql` | SQLite tables, relationships, and constraints |
| `app.py`, `auction.py` | FastAPI routes and auction logic |
| `templates/`, `static/` | HTML pages, styles, countdown, and live updates |

## Demo

1. Create an RFQ with a bid start in the past, an initial close three to five minutes from now, and a forced close seven minutes after the initial close. Use X = 10, Y = 5, and **Lowest bidder (L1) changes**.
2. Enter bids from Carrier A at ₹900 and Carrier B at ₹1,000. Use zero for origin and destination charges and a validity date today or later. The first bid establishes L1, and the second leaves L1 unchanged.
3. Enter a revised bid from B at ₹850. B takes L1, the close moves five minutes later, and the activity log records the reason.
4. Once the countdown is under ten minutes again, enter ₹800 from A. The new deadline reaches the forced close, adding only two minutes. At that time the status becomes **Force Closed** and the backend rejects further bids.
5. Reload the listing to see the latest status and lowest bid. Try **Any accepted bid** and **Any supplier rank change** on separate RFQs to compare trigger behavior.
