from contextlib import asynccontextmanager, closing

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import auction


@asynccontextmanager
async def lifespan(app):
    auction.init_db()
    yield


app = FastAPI(title="RFQ British Auctions", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=auction.BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=auction.BASE_DIR / "templates")
templates.env.filters.update(money=auction.display_money, ist=auction.display_time)
templates.env.globals["triggers"] = auction.TRIGGERS


def page(request, name, status_code=200, **context):
    return templates.TemplateResponse(
        request=request, name=name, context=context, status_code=status_code
    )


def auction_details(rfq_id):
    with closing(auction.connect()) as db:
        db.execute("BEGIN")
        rfq = db.execute("SELECT * FROM rfqs WHERE id = ?", (rfq_id,)).fetchone()
        if rfq is None:
            raise HTTPException(404, "RFQ not found.")
        bids = auction.get_bids(db, rfq_id)
        events = db.execute(
            """
            SELECT activity_log.*, bids.submitted_at
            FROM activity_log JOIN bids ON bids.id = activity_log.bid_id
            WHERE bids.rfq_id = ?
            ORDER BY activity_log.id DESC
            """,
            (rfq_id,),
        ).fetchall()

    now = auction.now_seconds()
    ranking = auction.rank_bids(bids)
    return {
        "rfq": rfq, "status": auction.status(rfq, now), "now": now,
        "ranking": ranking, "bids": bids, "events": events,
    }


@app.get("/", response_class=HTMLResponse)
def auction_list(request: Request):
    with closing(auction.connect()) as db:
        rows = db.execute(
            """
            SELECT rfqs.*, (SELECT MIN(total) FROM bids WHERE rfq_id = rfqs.id) AS lowest
            FROM rfqs ORDER BY id DESC
            """
        ).fetchall()
    now = auction.now_seconds()
    auctions = [(rfq, auction.status(rfq, now)) for rfq in rows]
    return page(request, "index.html", auctions=auctions)


@app.get("/rfqs/new", response_class=HTMLResponse)
def new_rfq(request: Request):
    return page(request, "new.html", values={})


@app.post("/rfqs", response_class=HTMLResponse)
def save_rfq(
    request: Request,
    name: str = Form(),
    bid_start: str = Form(),
    initial_close: str = Form(),
    forced_close: str = Form(),
    service_date: str = Form(),
    trigger_minutes: str = Form(),
    extension_minutes: str = Form(),
    trigger_type: str = Form(),
):
    values = {
        "name": name, "bid_start": bid_start, "initial_close": initial_close,
        "forced_close": forced_close, "service_date": service_date,
        "trigger_minutes": trigger_minutes, "extension_minutes": extension_minutes,
        "trigger_type": trigger_type,
    }
    try:
        rfq_id = auction.create_rfq(values)
    except ValueError as error:
        return page(request, "new.html", 400, values=values, error=str(error))
    return RedirectResponse(f"/rfqs/{rfq_id}", status_code=303)


@app.get("/rfqs/{rfq_id}", response_class=HTMLResponse)
def view_rfq(request: Request, rfq_id: int):
    return page(request, "detail.html", bid_form={}, **auction_details(rfq_id))


@app.get("/rfqs/{rfq_id}/live", response_class=HTMLResponse)
def live_rfq(request: Request, rfq_id: int):
    response = page(request, "_live.html", **auction_details(rfq_id))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/rfqs/{rfq_id}/bids", response_class=HTMLResponse)
def save_bid(
    request: Request,
    rfq_id: int,
    carrier_name: str = Form(),
    freight: str = Form(),
    origin: str = Form(),
    destination: str = Form(),
    transit_days: str = Form(),
    valid_until: str = Form(),
):
    values = {
        "carrier_name": carrier_name, "freight": freight, "origin": origin,
        "destination": destination, "transit_days": transit_days, "valid_until": valid_until,
    }
    try:
        auction.submit_bid(rfq_id, values)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        return page(
            request, "detail.html", 400, bid_form=values, error=str(error),
            **auction_details(rfq_id),
        )
    return RedirectResponse(f"/rfqs/{rfq_id}", status_code=303)
