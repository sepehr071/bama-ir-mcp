"""More Bama tools: motorcycle and truck ads, dealer inventory, new-car price list, market pulse, car specs."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal

from pydantic import Field

from .cars import KINDS, Many, _ad, _int, _list, _query
from .http import SITE, ApiError, fetch
from .registry import tool

PRICE_TYPES = {"market": "MarketPrice", "agency": "AgencyPrice", "factory": "FactoryPrice"}


@tool("Search motorcycle and truck ads")
async def ba_search_bikes_trucks(
    kind: Annotated[Literal["motorcycle", "truck"], Field(description="Which section of Bama to search.")],
    vehicle: Annotated[
        list[str] | None,
        Field(
            description="ba_vehicles values (same vehicle_type), e.g. ['honda'].",
            max_length=10,
        ),
    ] = None,
    year_from: Annotated[int | None, Field(description="Earliest year, Jalali.", ge=1300, le=1500)] = None,
    year_to: Annotated[int | None, Field(description="Latest year, Jalali.", ge=1300, le=1500)] = None,
    price_from: Annotated[int | None, Field(description="Minimum price in Toman.", ge=0)] = None,
    price_to: Annotated[int | None, Field(description="Maximum price in Toman.", ge=0)] = None,
    mileage_from: Annotated[int | None, Field(description="Minimum km.", ge=0)] = None,
    mileage_to: Annotated[int | None, Field(description="Maximum km (0 = zero-km only).", ge=0)] = None,
    region: Annotated[
        list[str] | None,
        Field(description="ba_filters kind=region values, e.g. ['tehran'].", max_length=10),
    ] = None,
    seller: Literal["dealer", "private"] | None = None,
    transmission: Literal["manual", "automatic"] | None = None,
    fuel: Annotated[Many, Field(description="Motorcycles: ['gasoline'] or ['electric'].")] = None,
    color: Annotated[Many, Field(description="ba_filters kind=color values (vehicle_type=kind).")] = None,
    body: Annotated[Many, Field(description="Motorcycles: ba_filters kind=body values, e.g. ['scooter'].")] = None,
    usage: Annotated[Many, Field(description="Trucks: ba_filters kind=usage values, e.g. ['tractor'].")] = None,
    body_status: Annotated[Many, Field(description="Trucks: ba_filters kind=body_status values.")] = None,
    with_photo: Annotated[bool, Field(description="Only ads with photos.")] = False,
    with_price: Annotated[bool, Field(description="Only ads with a stated price.")] = False,
    installment: Annotated[bool, Field(description="Only installment ads.")] = False,
    sort: Literal["relevance", "expensive", "cheapest", "newest", "oldest", "lowest_mileage"] = "relevance",
    page: Annotated[int, Field(description="0-based page (page 0 ~10 ads, later 30).", ge=0, le=50)] = 0,
    description_chars: Annotated[
        int, Field(description="Characters of each ad's text to include (0 = none).", ge=0, le=300)
    ] = 0,
) -> dict[str, Any]:
    """Search motorcycle or truck (heavy vehicle, bus, machinery) ads on Bama with filters.

    Get values from ba_vehicles / ba_filters with the same vehicle_type. Prices Toman. Then ba_ad with a code.
    No total count: page while has_more is true. Cars: ba_search.
    """
    q = _query(
        vehicle=vehicle,
        year_from=year_from,
        year_to=year_to,
        price_from=price_from,
        price_to=price_to,
        mileage_from=mileage_from,
        mileage_to=mileage_to,
        region=region,
        seller=seller,
        transmission=transmission,
        body=body,
        fuel=fuel,
        color=color,
        body_status=body_status,
        usage=usage,
        with_photo=with_photo,
        with_price=with_price,
        installment=installment,
        sort=sort,
        page=page,
    )
    r = await _list(q, kind)
    d, meta = r["data"], r.get("metadata") or {}
    ads = [_ad(a, description_chars) for a in d.get("ads", []) if a.get("type") == "ad" and a.get("detail")]
    return {
        "kind": kind,
        "page": page,
        "has_more": bool(meta.get("has_next")),
        "count": len(ads),
        "ads": ads,
        "list_url": SITE + (d.get("url") or f"/{kind}"),
    }


@tool("Dealer inventory")
async def ba_dealer_ads(
    dealer_id: Annotated[int, Field(description="Id from ba_dealers or an ad's seller.id.", ge=1)],
    query: Annotated[
        str | None, Field(description="Only ads whose title/trim contains this text.", max_length=40)
    ] = None,
    year_from: Annotated[int | None, Field(description="Earliest year, Jalali.", ge=1300, le=1500)] = None,
    year_to: Annotated[int | None, Field(description="Latest year, Jalali.", ge=1300, le=1500)] = None,
    price_to: Annotated[int | None, Field(description="Maximum price in Toman.", ge=0)] = None,
    sort: Literal["listed", "cheapest", "expensive", "newest", "lowest_mileage"] = "listed",
    limit: Annotated[int, Field(description="Most ads to return.", ge=1, le=100)] = 30,
) -> dict[str, Any]:
    """List the ads of one dealer (showroom) on Bama: the dealer's whole inventory, up to the first 100 ads.

    Use after ba_dealers. Filters and sorting run on the fetched list. Returns address, location and compact ads.
    """
    info = (await fetch(f"/cad/api/Corporation/{dealer_id}")).get("data")
    if not info:
        raise ApiError(f"Dealer {dealer_id} was not found.", 404)
    kind = info.get("vehicle_type") if info.get("vehicle_type") in KINDS else "car"
    r = await fetch(f"/{KINDS[kind]}/api/Corporation/ads/{dealer_id}")
    ads = [_ad(a) for a in r.get("data") or [] if a.get("type") == "ad" and a.get("detail")]
    total = len(ads)
    if query:
        w = query.lower().split()
        ads = [a for a in ads if all(x in f"{a['title']} {a.get('trim') or ''}".lower() for x in w)]
    ads = [
        a
        for a in ads
        if (not year_from or _int(a["year"]) >= year_from)
        and (not year_to or _int(a["year"]) <= year_to)
        and (price_to is None or (a.get("price_toman") and a["price_toman"] <= price_to))
    ]
    key = {
        "cheapest": lambda a: a.get("price_toman") or 10**15,
        "expensive": lambda a: -(a.get("price_toman") or 0),
        "newest": lambda a: -(_int(a["year"]) or 0),
        "lowest_mileage": lambda a: a["mileage_km"] if a["mileage_km"] is not None else 10**9,
    }.get(sort)
    if key:
        ads.sort(key=key)
    return {
        "dealer": {
            "id": dealer_id,
            "name": info.get("title", "").strip(),
            "type": info.get("type"),
            "address": info.get("address"),
            "lat": info.get("latitude"),
            "lng": info.get("longitude"),
            "active": info.get("is_active"),
            "section": kind,
            "url": f"{SITE}/dealer/{dealer_id}",
        },
        "ads_fetched": total,
        "matching": len(ads),
        "capped": total >= 100,
        "ads": ads[:limit],
    }


@tool("New-car price list")
async def ba_price_list(
    search: Annotated[
        str | None,
        Field(description="Brand/model/trim words, English or Persian, e.g. 'tiggo'.", max_length=40),
    ] = None,
    price_type: Annotated[
        Literal["market", "agency", "factory"] | None,
        Field(description="Only this price provider."),
    ] = None,
    imported: Annotated[bool | None, Field(description="True = imported/assembled; False = domestic.")] = None,
    vehicle_type: Literal["car", "motorcycle"] = "car",
    sort: Literal["brand", "cheapest", "expensive", "biggest_rise", "biggest_drop"] = "brand",
    limit: Annotated[int, Field(description="Most rows to return.", ge=1, le=150)] = 40,
) -> dict[str, Any]:
    """Search Bama's daily price list of new cars (or motorcycles) across all brands and rank it.

    Each row is one trim, year and price type: Toman price and change since the last quote. Use sort for "cheapest"
    or "biggest_rise". One model's history: ba_new_prices; specs: ba_car_specs.
    """
    params: dict[str, Any] = {"pageIndex": 0, "pageSize": 500}
    if search:
        params["searchQuery"] = search
    if price_type:
        params["priceType"] = PRICE_TYPES[price_type]
    if imported is not None:
        params["imported"] = str(imported).lower()
    r = await fetch(f"/{KINDS[vehicle_type]}/api/price/hierarchy", params)
    rows = []
    for b in r.get("data") or []:
        for i in b.get("items") or []:
            rows.append(
                {
                    "brand": i.get("brand"),
                    "brand_name": i.get("brand_fa"),
                    "model": i.get("model"),
                    "model_name": i.get("model_fa"),
                    "trim": i.get("trim"),
                    "trim_name": i.get("trim_fa"),
                    "year": i.get("model_year"),
                    "price_toman": i.get("price"),
                    "provider": i.get("price_provider"),
                    "change_percent": i.get("price_diff"),
                    "updated": i.get("price_date"),
                    "origin": (i.get("manufacture_type") or {}).get("display_name"),
                }
            )
    key = {
        "cheapest": lambda x: x["price_toman"] or 10**15,
        "expensive": lambda x: -(x["price_toman"] or 0),
        "biggest_rise": lambda x: -(x["change_percent"] or 0),
        "biggest_drop": lambda x: x["change_percent"] or 0,
    }.get(sort)
    if key:
        rows.sort(key=key)
    return {
        "updated": (r.get("metadata") or {}).get("last_update"),
        "matches": len(rows),
        "prices": rows[:limit],
    }


@tool("Car market pulse")
async def ba_market_pulse(
    movers: Annotated[int, Field(description="Number of biggest price movers to list.", ge=0, le=20)] = 10,
) -> dict[str, Any]:
    """Today's car market mood from Bama (score, trend and a short analysis per market) plus the biggest price movers.

    The analysis is Bama's Persian text. Movers are new cars with the largest price change; follow up with
    ba_new_prices or ba_price_list.
    """
    pulse = (await fetch("/gen/api/HomePage/market-pulse")).get("data") or {}
    rows = []
    if movers:
        await asyncio.sleep(0.3)
        for i in ((await fetch("/cad/api/Price/slider", {"distinct": "true"})).get("data") or [])[:movers]:
            rows.append(
                {
                    "brand": i.get("brand_fa"),
                    "model": i.get("model_fa"),
                    "trim": i.get("trim_fa"),
                    "year": i.get("model_year"),
                    "price_toman": i.get("price"),
                    "change_percent": i.get("price_diff"),
                    "provider": i.get("price_provider"),
                    "brand_key": i.get("brand"),
                    "model_key": i.get("model"),
                }
            )
    return {
        "score": pulse.get("score"),
        "status": (pulse.get("status") or {}).get("display_name"),
        "updated": (pulse.get("last_updated_at") or {}).get("display_name"),
        "summary": pulse.get("description"),
        "markets": [
            {
                "market": (s.get("category") or {}).get("display_name"),
                "status": (s.get("status") or {}).get("display_name"),
                "title": s.get("title"),
                "analysis": s.get("body"),
            }
            for s in pulse.get("sections") or []
        ],
        "movers": rows,
    }


def _specs(sections: list[dict[str, Any]], full: bool) -> dict[str, dict[str, str]]:
    """Section title -> {feature: value}; drops absent features ('false') and shows 'true' as yes."""
    out: dict[str, dict[str, str]] = {}
    for s in sections[: None if full else 4]:
        items = {
            (i.get("key") or "").strip(): "yes" if i.get("value") == "true" else str(i.get("value")).strip()
            for i in s.get("items") or []
            if i.get("value") not in (None, "", "false")
        }
        if items:
            out[s["title"]] = items
    return out


@tool("Car and motorcycle specs and review")
async def ba_car_specs(
    brand: Annotated[str, Field(description="Brand value from ba_vehicles, e.g. 'samand'.", max_length=40)],
    model: Annotated[
        str | None,
        Field(description="Model value, e.g. 'soren'. Omit to list models.", max_length=40),
    ] = None,
    trim: Annotated[
        str | None, Field(description="Trim key from a result's trims, e.g. 'pluscng'.", max_length=40)
    ] = None,
    vehicle_type: Literal["car", "motorcycle"] = "car",
    full_equipment: Annotated[bool, Field(description="Also return equipment sections.")] = False,
    description_chars: Annotated[
        int, Field(description="Characters of the review text to include (0 = none).", ge=0, le=1500)
    ] = 0,
) -> dict[str, Any]:
    """Technical specifications and the editorial review score of a car or motorcycle model from Bama's research pages.

    Without model it lists the brand's models. Returns power, torque, dimensions, rating, pros/cons, trims and
    generations. ba_ad shows what is for sale, ba_new_prices the new price.
    """
    pre = {"car": "CarReview", "motorcycle": "MotorcycleReview"}[vehicle_type]
    base = f"/nws/api/{pre}"
    listing = (await fetch(f"{base}/modelsbybrand", {"brand": brand}, ttl=3600)).get("data") or {}
    models = listing.get("models") or []
    if not models:
        raise ApiError(f"No research pages for brand {brand}. Check the brand value with ba_vehicles.", 404)
    if not model:
        return {
            "brand": listing.get("brand_name_fa"),
            "models": [
                {"model": m["brand_model_en"], "name": m["brand_model_fa"], "url": SITE + m["url"]} for m in models
            ],
        }
    hit = [m for m in models if m["brand_model_en"].lower() == model.lower()] or [
        m for m in models if f"/{model.lower()}-specs" in m["url"].lower()
    ]
    if not hit:
        names = ", ".join(m["brand_model_en"] for m in models)
        raise ApiError(f"No model {model} for {brand}. Models: {names}.", 404)
    url = hit[0]["url"]
    detail = (await fetch(f"{base}/{'carreviewdetail' if vehicle_type == 'car' else 'detail'}", {"url": url})).get(
        "data"
    )
    if trim and detail and trim != detail.get("trim_name"):
        t = next((t for t in detail.get("trims") or [] if t.get("trim") == trim), None)
        if not t:
            keys = ", ".join(t.get("trim", "") for t in detail.get("trims") or [])
            raise ApiError(f"No trim {trim}. Trims: {keys}.", 404)
        url = t["url"]
        detail = (await fetch(f"{base}/{'carreviewdetail' if vehicle_type == 'car' else 'detail'}", {"url": url})).get(
            "data"
        )
    if not detail:
        raise ApiError("Bama has no research page for that model.", 404)
    specs = await fetch(
        f"{base}/getspecification", {"id": detail["research_id"], "trimname": detail.get("trim_name") or ""}
    )
    st = detail.get("stats") or {}
    out = {
        "name": f"{detail.get('vehicle_full_name')} {detail.get('trim_name_fa') or ''}".strip(),
        "years": f"{detail.get('year')}-{detail.get('to_year')}" if detail.get("to_year") else detail.get("year"),
        "rating": st.get("rating"),
        "score": st.get("final_score"),
        "scores_percent": {k.removesuffix("_percent"): v for k, v in st.items() if k.endswith("_percent")},
        "pros": st.get("pros_list"),
        "cons": st.get("cons_list"),
        "reviews_count": detail.get("comments_count"),
        "ads_for_sale": detail.get("total_ad_count"),
        "trims": [{"trim": t.get("trim"), "name": t.get("trim_fa")} for t in detail.get("trims") or []],
        "generations": [{"years": y.get("year"), "url": SITE + y["url"]} for y in detail.get("years") or []],
        "specs": _specs(specs.get("data") or [], full_equipment),
        "url": SITE + url,
    }
    if description_chars and detail.get("description"):
        out["review"] = " ".join(detail["description"].split())[:description_chars]
    return out
