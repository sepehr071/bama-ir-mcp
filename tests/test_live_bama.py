import pytest

pytestmark = [pytest.mark.live, pytest.mark.anyio]


async def test_live_vehicles_and_filters(client):
    r = (await client.call_tool("ba_vehicles", {"query": "soren"})).structured_content
    assert "samand,soren" in {v["value"] for v in r["vehicles"]}, r
    r = (await client.call_tool("ba_filters", {"kind": "region", "query": "isfahan"})).structured_content
    assert any(v["value"] == "isfahan" for v in r["values"]), r


async def test_live_search_filters_apply(client):
    r = (
        await client.call_tool(
            "ba_search",
            {
                "vehicle": ["peugeot,206ir"],
                "year_from": 1395,
                "year_to": 1400,
                "region": ["tehran"],
                "sort": "cheapest",
            },
        )
    ).structured_content
    assert r["count"] > 10, r
    assert all("206" in a["title"] and 1395 <= int(a["year"]) <= 1400 for a in r["ads"]), r


async def test_live_ad_roundtrip(client):
    ads = (await client.call_tool("ba_search", {"vehicle": ["pride"], "with_photo": True})).structured_content["ads"]
    r = (await client.call_tool("ba_ad", {"code": ads[0]["code"]})).structured_content
    assert r["code"] == ads[0]["code"] and r["brand"] == "pride" and r["specs"]


async def test_live_market_stats(client):
    r = (
        await client.call_tool(
            "ba_market_stats", {"vehicle": ["pride"], "year_from": 1395, "year_to": 1395, "pages": 1}
        )
    ).structured_content
    p = r["price_toman"]
    assert p["n"] > 3 and 100_000_000 < p["median"] < 3_000_000_000 and p["min"] <= p["median"] <= p["max"], r


async def test_live_dealers(client):
    r = (await client.call_tool("ba_dealers", {"vehicle": ["samand"], "pages": 1})).structured_content
    assert r["dealers"] and r["dealers"][0]["name"], r


async def test_live_new_prices(client):
    r = (await client.call_tool("ba_new_prices", {"brand": "samand", "model": "soren"})).structured_content
    assert r["prices"] and all(p["price_toman"] > 100_000_000 for p in r["prices"]), r


async def test_live_bikes_trucks_and_ad_kinds(client):
    m = (
        await client.call_tool("ba_search_bikes_trucks", {"kind": "motorcycle", "sort": "cheapest"})
    ).structured_content
    assert m["count"] > 5 and all(a["price_toman"] or a["price_type"] != "lumpsum" for a in m["ads"]), m
    t = (await client.call_tool("ba_search_bikes_trucks", {"kind": "truck", "usage": ["tractor"]})).structured_content
    assert t["count"] > 0, t
    for r in (m, t):
        ad = (await client.call_tool("ba_ad", {"code": r["ads"][0]["code"]})).structured_content
        assert ad["kind"] == r["kind"] and ad["code"] == r["ads"][0]["code"], ad


async def test_live_dealer_price_pulse_specs(client):
    d = (await client.call_tool("ba_dealers", {"vehicle": ["samand"], "pages": 1})).structured_content["dealers"][0]
    r = (await client.call_tool("ba_dealer_ads", {"dealer_id": d["id"]})).structured_content
    assert r["ads_fetched"] > 0 and r["dealer"]["name"], r
    p = (await client.call_tool("ba_price_list", {"search": "soren", "price_type": "market"})).structured_content
    assert p["prices"] and all(x["provider"] == "قیمت بازار" for x in p["prices"]), p
    pulse = (await client.call_tool("ba_market_pulse", {"movers": 5})).structured_content
    assert pulse["score"] and len(pulse["movers"]) == 5, pulse
    s = (await client.call_tool("ba_car_specs", {"brand": "samand", "model": "soren"})).structured_content
    assert s["specs"] and s["trims"], s
    n = (
        await client.call_tool("ba_new_prices", {"brand": "samand", "model": "soren", "trim": "pluscng"})
    ).structured_content
    assert n["prices"] and all(x["trim_key"] == "pluscng" for x in n["prices"]), n
