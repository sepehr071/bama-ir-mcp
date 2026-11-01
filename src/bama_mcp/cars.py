"""Bama tools: car ad search, ad detail, market price statistics, new-car prices, brand/model and filter lists."""

from __future__ import annotations

import asyncio
import re
import statistics
from typing import Annotated, Any, Literal

from pydantic import Field

from .http import CACHE_LONG, SITE, ApiError, fetch
from .registry import tool

SORTS = {"relevance": 2, "expensive": 3, "cheapest": 4, "newest": 5, "oldest": 6, "lowest_mileage": 7}
SELLERS = {"dealer": "0", "private": "1"}
FILTER_KINDS = {
    "region": "region",
    "body": "body",
    "fuel": "fuel",
    "color": "color",
    "country": "country",
    "body_status": "status",
    "cylinder": "cylinder",
    "drive": "drive",
    "engine_volume": "engine",
    "economy": "expense",
    "origin": "origin",
    "lifestyle": "lifestyle",
    "year": "year",
    "usage": "usage",
}
KINDS = {"car": "cad", "motorcycle": "mad", "truck": "tad"}  # API prefix per vehicle section
PAGE_ADS = 30  # the API ignores pageSize above its default and returns up to 30 ads per page

Vehicle = Annotated[
    list[str] | None,
    Field(
        description="Brand, model or trim values from ba_vehicles, e.g. ['samand'], ['samand,lx'], ['peugeot,206ir,type2']. Several values mean any of them.",
        max_length=10,
    ),
]
Many = Annotated[list[str] | None, Field(max_length=10)]


def _int(s: Any) -> int | None:
    d = re.sub(r"\D", "", str(s or ""))
    return int(d) if d else None


def _mileage(s: str | None) -> int | None:
    if not s:
        return None
    return 0 if "صفر" in s else _int(s)


def _ad(a: dict[str, Any], desc: int = 0, full: bool = False) -> dict[str, Any]:
    """One compact ad from a search result item (type == 'ad')."""
    d, p, dealer = a["detail"], a.get("price") or {}, a.get("dealer")
    price = _int(p.get("price"))
    out: dict[str, Any] = {
        "code": d["code"],
        "title": d["title"],
        "year": d.get("year"),
        "trim": d.get("trim"),
        "price_toman": price or None,
        "price_type": p.get("type"),
        "mileage_km": _mileage(d.get("mileage")),
        "city": d.get("location"),
        "transmission": d.get("transmission"),
        "fuel": d.get("fuel"),
        "body_color": d.get("body_color"),
        "body_status": d.get("body_status"),
        "posted": d.get("time"),
        "url": SITE + d["url"],
    }
    if p.get("type") == "installment":
        # detail splits the prepayment in two and has the real count; search items carry a placeholder 1
        out["prepayment_toman"] = (
            _int(p.get("prepayment"))
            or (_int(p.get("prepayment_primary")) or 0) + (_int(p.get("prepayment_secondary")) or 0)
            or None
        )
        out["monthly_toman"] = _int(p.get("payment")) or _int(p.get("payment_primary")) or None
        if full:
            out["installments"] = p.get("installments") or None
    if dealer:
        out["seller"] = {"dealer": dealer.get("name", "").strip(), "id": dealer.get("id"), "score": dealer.get("score")}
    # motorcycle and truck items carry these instead of the car fields
    out |= {
        "engine": d.get("engine_volume"),
        "body_type": d.get("body_type_fa") or d.get("body_type"),
        "usage": d.get("usage_type"),
        "operating_hours": d.get("operating_hour"),
    }
    if desc and d.get("description"):
        out["description"] = " ".join(d["description"].split())[:desc]
    return out


def _query(
    vehicle=None,
    year_from=None,
    year_to=None,
    price_from=None,
    price_to=None,
    mileage_from=None,
    mileage_to=None,
    region=None,
    seller=None,
    transmission=None,
    body=None,
    fuel=None,
    color=None,
    country=None,
    body_status=None,
    cylinder=None,
    drive=None,
    lifestyle=None,
    origin=None,
    usage=None,
    with_photo=False,
    with_price=False,
    installment=False,
    presale=False,
    sort="relevance",
    page=0,
) -> list[tuple[str, Any]]:
    q: list[tuple[str, Any]] = []
    for key, val in (
        ("vehicle", vehicle),
        ("region", region),
        ("body", body),
        ("fuel", fuel),
        ("color", color),
        ("country", country),
        ("status", body_status),
        ("cylinder", cylinder),
        ("drive", drive),
        ("lifestyle", lifestyle),
        ("origin", origin),
        ("usage", usage),
    ):
        q += [(key, v) for v in (val or [])]
    for key, val in (
        ("yearFrom", year_from),
        ("yearTo", year_to),
        ("priceFrom", price_from),
        ("priceTo", price_to),
        ("mileageFrom", mileage_from),
        ("mileageTo", mileage_to),
        ("transmission", transmission),
        ("seller", SELLERS.get(seller or "")),
        ("sort", SORTS[sort] if sort != "relevance" else None),
    ):
        if val is not None:
            q.append((key, val))
    q += [
        (k, 1)
        for k, on in (("image", with_photo), ("priced", with_price), ("installment", installment), ("presale", presale))
        if on
    ]
    return [*q, ("pageIndex", page)]


async def _list(q: list[tuple[str, Any]], kind: str = "car") -> dict[str, Any]:
    r = await fetch(f"/{KINDS[kind]}/api/search", q)
    if not r.get("status"):
        raise ApiError(f"Bama search failed: {r.get('errors')}")
    return r


@tool("Search car ads")
async def ba_search(
    vehicle: Vehicle = None,
    year_from: Annotated[
        int | None, Field(description="Earliest production year, Jalali (e.g. 1395).", ge=1300, le=1500)
    ] = None,
    year_to: Annotated[
        int | None, Field(description="Latest production year, Jalali (e.g. 1400).", ge=1300, le=1500)
    ] = None,
    price_from: Annotated[int | None, Field(description="Minimum price in Toman.", ge=0)] = None,
    price_to: Annotated[int | None, Field(description="Maximum price in Toman.", ge=0)] = None,
    mileage_from: Annotated[
        int | None, Field(description="Minimum mileage in km. 0 with mileage_to=0 means zero-km cars.", ge=0)
    ] = None,
    mileage_to: Annotated[int | None, Field(description="Maximum mileage in km.", ge=0)] = None,
    region: Annotated[
        list[str] | None,
        Field(
            description="State or city values from ba_filters kind=region, e.g. ['tehran'] or ['isfahan,kashan'].",
            max_length=10,
        ),
    ] = None,
    seller: Annotated[
        Literal["dealer", "private"] | None, Field(description="Only dealers (showrooms) or only private sellers.")
    ] = None,
    transmission: Literal["manual", "automatic"] | None = None,
    body: Annotated[Many, Field(description="Body values from ba_filters kind=body, e.g. ['suv'].")] = None,
    fuel: Annotated[Many, Field(description="Fuel values from ba_filters kind=fuel, e.g. ['gasoline'].")] = None,
    color: Annotated[Many, Field(description="Color values from ba_filters kind=color, e.g. ['white'].")] = None,
    country: Annotated[
        Many, Field(description="Maker country values from ba_filters kind=country, e.g. ['Chinese'].")
    ] = None,
    body_status: Annotated[
        Many, Field(description="Paint/body condition values from ba_filters kind=body_status, e.g. ['no_paint'].")
    ] = None,
    cylinder: Annotated[Many, Field(description="Values from ba_filters kind=cylinder, e.g. ['four'].")] = None,
    drive: Annotated[Many, Field(description="Drive-train values from ba_filters kind=drive, e.g. ['awd'].")] = None,
    lifestyle: Annotated[
        Many, Field(description="Lifestyle values from ba_filters kind=lifestyle (e.g. family, sport).")
    ] = None,
    origin: Annotated[
        Many, Field(description="Origin values from ba_filters kind=origin (e.g. domestic, imported, assembled).")
    ] = None,
    with_photo: Annotated[bool, Field(description="Only ads with photos.")] = False,
    with_price: Annotated[bool, Field(description="Only ads that state a price (hides 'negotiable').")] = False,
    installment: Annotated[bool, Field(description="Only installment (اقساطی) ads.")] = False,
    presale: Annotated[bool, Field(description="Only presale or allocation-letter (حواله) ads.")] = False,
    sort: Literal["relevance", "expensive", "cheapest", "newest", "oldest", "lowest_mileage"] = "relevance",
    page: Annotated[int, Field(description="0-based page; each page holds up to 30 ads.", ge=0, le=50)] = 0,
    description_chars: Annotated[
        int, Field(description="Include this many characters of each ad's text (0 = none).", ge=0, le=300)
    ] = 0,
) -> dict[str, Any]:
    """Search used and new car ads on Bama (bama.ir) with filters; returns up to 30 compact ads per page.

    Use it for "find me X under Y" questions. Get brand/model values from ba_vehicles and region, body, fuel and
    color values from ba_filters. Prices are Toman; year is Jalali (imports can show a Gregorian year); mileage_km 0
    means zero-km. Then call ba_ad with a code for full details, or ba_market_stats for price statistics. The site
    gives no total count: keep paging while has_more is true (ba_ad reports the real number of ads for one model).
    Motorcycles and trucks are searched with ba_search_bikes_trucks.
    """
    args = dict(locals())
    args.pop("description_chars")
    r = await _list(_query(**args))
    d, meta = r["data"], r.get("metadata") or {}
    ads = [_ad(a, description_chars) for a in d.get("ads", []) if a.get("type") == "ad" and a.get("detail")]
    return {
        "page": page,
        "has_more": bool(meta.get("has_next")),
        "count": len(ads),
        "ads": ads,
        "list_url": SITE + (d.get("url") or "/car"),
    }


async def _detail(code: str, kind: str) -> tuple[str, dict[str, Any]]:
    """Fetch an ad from the section it lives in; kind 'auto' tries car, motorcycle, then truck."""
    for k in KINDS if kind == "auto" else [kind]:
        try:
            r = await fetch(f"/{KINDS[k]}/api/detail/{code}")
        except ApiError as e:
            if e.status not in (400, 404):
                raise
            continue
        if r.get("status") and r.get("data"):
            return k, r["data"]
    raise ApiError(f"Ad {code} was not found (it may have been removed).", 404)


def _related(a: dict[str, Any]) -> dict[str, Any]:
    d, p = a["detail"], a.get("price") or {}
    return {
        "code": d["code"],
        "title": d.get("title"),
        "trim": d.get("trim"),
        "year": d.get("year"),
        "mileage_km": _mileage(d.get("mileage")),
        "price_toman": _int(p.get("price")) or None,
        "city": d.get("location"),
        "url": SITE + d["url"],
    }


@tool("Ad details")
async def ba_ad(
    code: Annotated[str, Field(description="Ad code from ba_search, e.g. 4avpuyq7.", pattern=r"^[A-Za-z0-9]{6,12}$")],
    kind: Annotated[
        Literal["auto", "car", "motorcycle", "truck"],
        Field(description="Section of the ad. auto tries car, then motorcycle, then truck."),
    ] = "auto",
    similar: Annotated[
        int, Field(description="Also list this many similar car ads (0 = none). Car ads only.", ge=0, le=12)
    ] = 0,
) -> dict[str, Any]:
    """Get one Bama ad (car, motorcycle or truck) in full: price, specs, condition, seller, description and photos.

    Use it after ba_search or ba_search_bikes_trucks for a promising ad. ads_of_same_model and ads_of_same_trim
    are the real number of live ads for that car (the "N related ads" on the ad page). similar adds comparable
    car ads; similar_total counts Bama's wider similar pool. Phone numbers are masked by Bama, not available here.
    """
    kind, x = await _detail(code, kind)
    d, s = x["detail"], x.get("specs") or {}
    out = _ad(x, full=True)
    out.update(
        {
            "kind": kind,
            "ads_of_same_model": (x.get("ads_statistics") or {}).get("model"),
            "ads_of_same_trim": (x.get("ads_statistics") or {}).get("trim"),
            "brand": d.get("brand"),
            "model": d.get("model"),
            "trim_key": d.get("trim_en"),
            "body_type": (d.get("body") or {}).get("display_name"),
            "province": d.get("province"),
            "inside_color": d.get("inside_color"),
            "description": d.get("description"),
            "lifestyle": [v["display_name"] for v in d.get("life_styles") or []],
            "presale": d.get("is_pre_sale") or None,
            "authenticated": d.get("authenticated") or None,
            "specs": {k: v for k, v in s.items() if v and not k.startswith("url_")},
            "review_url": SITE + s["url_review"] if s.get("url_review") else None,
            "photos": [i.get("large") for i in (x.get("images") or [])][:8],
            "photo_count": d.get("image_count"),
        }
    )
    dealer = x.get("dealer")
    if dealer:
        out["seller"] = {k: dealer.get(k) for k in ("name", "type", "address", "ad_count", "score")} | {
            "id": dealer.get("id")
        }
    if similar and kind == "car":
        rel = await fetch("/cad/api/relatedads/search", {"code": code, "pageSize": similar, "pageIndex": 0})
        out["similar_total"] = (rel.get("metadata") or {}).get("total_count")
        out["similar"] = [_related(a) for a in rel.get("data") or [] if a.get("detail")]
    return out


def _stats(vals: list[int]) -> dict[str, int | None]:
    if not vals:
        return {"n": 0}
    q = statistics.quantiles(vals, n=4, method="inclusive") if len(vals) > 1 else [vals[0]] * 3
    return {"n": len(vals), "min": min(vals), "p25": int(q[0]), "median": int(q[1]), "p75": int(q[2]), "max": max(vals)}


@tool("Used-car market price stats")
async def ba_market_stats(
    vehicle: Vehicle = None,
    year_from: Annotated[int | None, Field(ge=1300, le=1500, description="Earliest production year, Jalali.")] = None,
    year_to: Annotated[int | None, Field(ge=1300, le=1500, description="Latest production year, Jalali.")] = None,
    region: Annotated[
        list[str] | None, Field(description="State or city values from ba_filters kind=region.", max_length=10)
    ] = None,
    mileage_from: Annotated[int | None, Field(ge=0, description="Minimum mileage in km.")] = None,
    mileage_to: Annotated[int | None, Field(ge=0, description="Maximum mileage in km (0 = zero-km only).")] = None,
    transmission: Literal["manual", "automatic"] | None = None,
    seller: Literal["dealer", "private"] | None = None,
    pages: Annotated[
        int, Field(description="How many result pages to sample (30 ads each). More is slower.", ge=1, le=5)
    ] = 3,
) -> dict[str, Any]:
    """Price statistics (min, quartiles, median, max, per year) for a car model from live Bama ads.

    Use it for "what is a 1398 Peugeot 206 worth" questions. It samples the first pages of the newest-updated
    matching ads, keeps only ads with a fixed price (no negotiable, installment or presale ads) and reports Toman.
    It is a sample of asking prices, not a full census nor sale prices. Narrow with year, mileage and region for
    a tighter range, then use ba_search with sort=cheapest to see the actual ads.
    """
    base = dict(
        vehicle=vehicle,
        year_from=year_from,
        year_to=year_to,
        region=region,
        mileage_from=mileage_from,
        mileage_to=mileage_to,
        transmission=transmission,
        seller=seller,
        with_price=True,
    )
    ads: list[dict[str, Any]] = []
    more = False
    for i in range(pages):
        r = await _list(_query(**base, sort="newest", page=i))
        ads += [_ad(a) for a in r["data"].get("ads", []) if a.get("type") == "ad" and a.get("detail")]
        more = bool((r.get("metadata") or {}).get("has_next"))
        if not more:
            break
        await asyncio.sleep(0.5)
    fixed = [a for a in ads if a["price_type"] == "lumpsum" and a["price_toman"] and not a["title"].startswith("حواله")]
    by_year: dict[str, list[int]] = {}
    for a in fixed:
        by_year.setdefault(str(a["year"]), []).append(a["price_toman"])
    kms = [a["mileage_km"] for a in fixed if a["mileage_km"] is not None]
    return {
        "sampled_ads": len(ads),
        "price_toman": _stats([a["price_toman"] for a in fixed]),
        "median_mileage_km": int(statistics.median(kms)) if kms else None,
        "by_year": {y: _stats(v) for y, v in sorted(by_year.items(), reverse=True)},
        "more_ads_exist": more,
        "note": "Asking prices from the sampled newest ads with a fixed price; not sale prices.",
    }


@tool("Dealers selling a model")
async def ba_dealers(
    vehicle: Vehicle = None,
    region: Annotated[
        list[str] | None, Field(description="State or city values from ba_filters kind=region.", max_length=10)
    ] = None,
    pages: Annotated[int, Field(description="Result pages to scan (30 ads each).", ge=1, le=4)] = 2,
) -> dict[str, Any]:
    """List car dealers (showrooms) with ads for a model or city on Bama, with address, rating and how many ads match.

    Use it for "where can I buy X from a dealer". Scans the first pages of dealer-only ads; dealer ids and names
    come from the ads, and each dealer's own listing is at the returned url. Then call ba_search with seller=dealer
    for the ads themselves.
    """
    found: dict[Any, dict[str, Any]] = {}
    for i in range(pages):
        r = await _list(_query(vehicle=vehicle, region=region, seller="dealer", page=i))
        for a in r["data"].get("ads", []):
            dl = a.get("dealer")
            if a.get("type") != "ad" or not dl:
                continue
            e = found.setdefault(
                dl["id"],
                {
                    "id": dl["id"],
                    "name": dl.get("name", "").strip(),
                    "address": dl.get("address"),
                    "rating": dl.get("score"),
                    "total_ads": dl.get("ad_count"),
                    "matching_ads": 0,
                    "url": SITE + (dl.get("link") or ""),
                },
            )
            e["matching_ads"] += 1
        if not (r.get("metadata") or {}).get("has_next"):
            break
        await asyncio.sleep(0.5)
    return {"dealers": sorted(found.values(), key=lambda d: -d["matching_ads"])}


def _walk(nodes: list[dict[str, Any]], out: list[dict[str, Any]]) -> None:
    for n in nodes:
        if n.get("selectable") and n.get("value"):
            out.append(n)
        _walk(n.get("items") or [], out)


async def _vehicle_nodes(kind: str = "car") -> list[dict[str, Any]]:
    if kind == "car":
        r = await fetch("/cad/api/filter/vehicle", ttl=CACHE_LONG)
    else:
        r = await fetch("/gen/api/filters/vehicle", {"vehicleCategory": kind}, ttl=CACHE_LONG)
    flat: list[dict[str, Any]] = []
    _walk(r["data"], flat)
    return flat


@tool("Brands, models and trims")
async def ba_vehicles(
    query: Annotated[
        str | None,
        Field(
            description="Brand, model or trim name in Persian or English, e.g. 'پژو 206', 'samand', 'soren'.",
            max_length=60,
        ),
    ] = None,
    brand: Annotated[
        str | None, Field(description="A brand value, e.g. 'peugeot': lists all its models and trims.", max_length=40)
    ] = None,
    vehicle_type: Annotated[
        Literal["car", "motorcycle", "truck"], Field(description="Section to look in (default car).")
    ] = "car",
) -> dict[str, Any]:
    """Look up the brand, model and trim values that ba_search, ba_market_stats and ba_new_prices take.

    Give query to find matches (up to 25) or brand to list one brand's models and trims; with neither it lists all
    brands. A value looks like 'samand', 'samand,lx' or 'peugeot,206ir,type2': brand, brand,model, brand,model,trim.
    Use vehicle_type motorcycle or truck for ba_search_bikes_trucks values.
    """
    nodes = await _vehicle_nodes(vehicle_type)
    if brand:
        rows = [n for n in nodes if n["value"] == brand or n["value"].startswith(brand + ",")]
    elif query:
        words = query.lower().split()
        rows = [n for n in nodes if all(w in (n.get("keywords") or n["title"]).lower() for w in words)]
    else:
        rows = [n for n in nodes if n.get("type") == "brand"]
    total = len(rows)
    return {
        "matches": total,
        "vehicles": [
            {"value": n["value"], "name": n["title"], "level": n.get("type")} for n in rows[: 25 if query else 150]
        ],
    }


async def _filter(kind: str, vehicle_type: str = "car") -> list[dict[str, Any]]:
    r = await fetch(f"/gen/api/filters/{FILTER_KINDS[kind]}", {"vehicleCategory": vehicle_type}, ttl=CACHE_LONG)
    return r.get("data") or []


@tool("Filter values")
async def ba_filters(
    kind: Literal[
        "region",
        "body",
        "fuel",
        "color",
        "country",
        "body_status",
        "cylinder",
        "drive",
        "engine_volume",
        "economy",
        "origin",
        "lifestyle",
        "year",
        "usage",
    ],
    query: Annotated[
        str | None,
        Field(
            description="For region and usage: part of a name (Persian or English) to find its value.",
            max_length=40,
        ),
    ] = None,
    vehicle_type: Annotated[
        Literal["car", "motorcycle", "truck"],
        Field(description="Section the values are for (default car). usage is for trucks."),
    ] = "car",
) -> dict[str, Any]:
    """List the allowed values of one ba_search filter (states and cities, body types, fuels, colors, years...).

    Use it before ba_search when you need an exact value, e.g. kind=region query=اصفهان gives 'isfahan'. Region lists
    states only unless query is given. transmission needs no lookup: manual or automatic.
    For trucks use vehicle_type=truck kind=usage (e.g. 'tractor', 'truck,axle1,tanker'); for motorcycles
    vehicle_type=motorcycle kind=body, fuel or color. Not every kind exists for every section.
    """
    data = await _filter(kind, vehicle_type)
    if kind in ("region", "usage"):
        flat: list[dict[str, Any]] = []
        _walk(data, flat)
        if query:
            words = query.lower().split()
            flat = [n for n in flat if all(w in (n.get("keywords") or n["title"]).lower() for w in words)]
        else:
            flat = [n for n in flat if n.get("type") == ("state" if kind == "region" else "kind")]
        return {"values": [{"value": n["value"], "name": n["title"]} for n in flat[:40]]}
    return {"values": [{"value": n["value"], "name": n["text"]} for n in data]}


def _trend(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    pts = [h for h in history if h.get("price")]
    if len(pts) < 2:
        return None
    first, last = pts[-min(len(pts), 30)], pts[-1]
    return {
        "since": first["date"],
        "from_toman": first["price"],
        "to_toman": last["price"],
        "change_percent": round((last["price"] - first["price"]) * 100 / first["price"], 1),
    }


@tool("New-car prices")
async def ba_new_prices(
    brand: Annotated[
        str,
        Field(
            description="Brand value from ba_vehicles, e.g. 'samand', 'peugeot', 'mvm'.", min_length=2, max_length=40
        ),
    ],
    model: Annotated[
        str | None,
        Field(description="Model value, e.g. 'soren' or '206ir'. Omit for all of the brand's models.", max_length=40),
    ] = None,
    history_days: Annotated[
        int, Field(description="Include this many recent price points per trim (0 = none).", ge=0, le=60)
    ] = 0,
    trim: Annotated[
        str | None,
        Field(
            description="Trim key (trim_key in a result, e.g. 'pluscng') to list one trim only; needs model.",
            max_length=40,
        ),
    ] = None,
) -> dict[str, Any]:
    """Current price of every new-car trim of a brand or model on Bama's price list (market price or factory price).

    Use it for "how much is a zero Samand Soren today": each row is one trim and year with price in Toman,
    provider (قیمت بازار market, قیمت کارخانه factory, قیمت نمایندگی dealer), daily change percent and a trend over
    the last 30 quoted prices. Compare with ba_market_stats for the used market. Brand-wide queries can list many trims;
    pass model and trim for one. ba_price_list searches all brands, ba_car_specs gives the technical data.
    """
    params = {"brand": brand} | ({"model": model} if model else {}) | ({"trim": trim} if trim and model else {})
    r = await fetch("/cad/api/price/detail", params)
    d = r.get("data") or {}
    if not d.get("items"):
        raise ApiError(
            f"No price list for {brand}{'/' + model if model else ''}. Check the values with ba_vehicles.", 404
        )
    rows = []
    for it in d["items"]:
        x = it["detail"]
        row = {
            "trim": x.get("trim_fa"),
            "trim_key": x.get("trim"),
            "year": x.get("model_year"),
            "class": x.get("class"),
            "price_toman": x.get("price"),
            "provider": x.get("price_provider"),
            "change_percent": x.get("price_diff"),
            "updated": x.get("price_date"),
            "trend": _trend(it.get("history") or []),
        }
        if history_days:
            row["history"] = [h for h in (it.get("history") or []) if h.get("price")][-history_days:]
        rows.append(row)
    return {
        "brand": d.get("brand_fa"),
        "model": d.get("model_fa"),
        "page": f"{SITE}/price/{brand}",
        "specs_url": SITE + d["review_url"] if d.get("review_url") else None,
        "prices": rows,
    }
