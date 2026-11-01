import json

import httpx
import pytest
from conftest import fixture

from bama_mcp import cars, http

pytestmark = pytest.mark.anyio

TOOLS = {
    "ba_search",
    "ba_ad",
    "ba_market_stats",
    "ba_dealers",
    "ba_vehicles",
    "ba_filters",
    "ba_new_prices",
    "ba_search_bikes_trucks",
    "ba_dealer_ads",
    "ba_price_list",
    "ba_market_pulse",
    "ba_car_specs",
}


def q(call: httpx.Request) -> list[tuple[str, str]]:
    return list(call.url.params.multi_items())


async def test_all_tools_are_read_only_and_described(client):
    tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == TOOLS
    for t in tools:
        assert t.annotations.read_only_hint is True
        assert t.description and t.description.splitlines()[0].endswith(".")


async def test_search_builds_the_query_and_trims_ads(client, api):
    api["/cad/api/search"] = fixture("search_dealer.json")
    r = (
        await client.call_tool(
            "ba_search",
            {
                "vehicle": ["peugeot,206ir"],
                "year_from": 1397,
                "price_to": 2_000_000_000,
                "seller": "dealer",
                "region": ["tehran"],
                "sort": "cheapest",
                "transmission": "manual",
                "with_photo": True,
            },
        )
    ).structured_content
    params = q(api.calls[0])
    for pair in [
        ("vehicle", "peugeot,206ir"),
        ("yearFrom", "1397"),
        ("priceTo", "2000000000"),
        ("seller", "0"),
        ("region", "tehran"),
        ("sort", "4"),
        ("transmission", "manual"),
        ("image", "1"),
        ("pageIndex", "0"),
    ]:
        assert pair in params, params
    first = r["ads"][0]
    assert first["code"] == "ixm79kwg" and first["price_toman"] == 1_800_000_000 and first["year"] == "1400"
    assert first["seller"]["dealer"] == "رادکار موتور" and first["url"].startswith("https://bama.ir/car/detail-")
    negotiable = next(a for a in r["ads"] if a["code"] == "bxzqb9jl")
    assert "price_toman" not in negotiable and negotiable["price_type"] == "negotiable"


async def test_search_installment_fields(client, api):
    api["/cad/api/search"] = fixture("search_installment.json")
    ad = (await client.call_tool("ba_search", {"installment": True})).structured_content["ads"][0]
    assert (
        ad["price_type"] == "installment"
        and ad["prepayment_toman"] == 400_000_000
        and ad["monthly_toman"] == 75_000_000
    )


async def test_repeated_values_become_repeated_params(client, api):
    api["/cad/api/search"] = fixture("search_installment.json")
    await client.call_tool("ba_search", {"fuel": ["gasoline", "hybrid"], "mileage_to": 0})
    params = q(api.calls[0])
    assert params.count(("fuel", "gasoline")) == 1 and ("fuel", "hybrid") in params and ("mileageTo", "0") in params


async def test_ad_detail(client, api):
    api["/cad/api/detail/4avpuyq7"] = fixture("detail.json")
    r = (await client.call_tool("ba_ad", {"code": "4avpuyq7"})).structured_content
    assert r["brand"] == "samand" and r["price_toman"] == 860_000_000 and r["mileage_km"] == 220_000
    assert r["specs"]["power"] and r["photos"] and "phone" not in r


async def test_ad_missing(client, api):
    api["/cad/api/detail/zzzzzzzz"] = lambda request: httpx.Response(404)
    r = await client.call_tool("ba_ad", {"code": "zzzzzzzz"})
    assert r.is_error and "not found" in r.content[0].text


async def test_market_stats_ignores_negotiable_and_samples_pages(client, api):
    api["/cad/api/search"] = fixture("search_dealer.json")
    r = (await client.call_tool("ba_market_stats", {"vehicle": ["peugeot,206ir"], "pages": 1})).structured_content
    prices = r["price_toman"]
    assert prices["n"] == 4 and prices["min"] == 1_250_000_000 and prices["max"] == 2_050_000_000
    assert 1_250_000_000 < prices["median"] < 2_050_000_000 and "1400" in r["by_year"]
    assert ("sort", "5") in q(api.calls[0]) and ("priced", "1") in q(api.calls[0])


async def test_dealers_aggregate(client, api):
    api["/cad/api/search"] = fixture("search_dealer.json")
    r = (await client.call_tool("ba_dealers", {"vehicle": ["peugeot,206ir"], "pages": 1})).structured_content
    assert (
        len(r["dealers"]) == 5
        and r["dealers"][0]["matching_ads"] == 1
        and r["dealers"][0]["url"].startswith("https://bama.ir/dealer/")
    )


async def test_vehicles_lookup(client, api):
    api["/cad/api/filter/vehicle"] = fixture("vehicles.json")
    r = (await client.call_tool("ba_vehicles", {"query": "soren"})).structured_content
    assert "samand,soren" in {v["value"] for v in r["vehicles"]}
    r = (await client.call_tool("ba_vehicles", {"brand": "peugeot"})).structured_content
    assert {"peugeot", "peugeot,206ir", "peugeot,206ir,type2"} <= {v["value"] for v in r["vehicles"]}
    r = (await client.call_tool("ba_vehicles", {})).structured_content
    assert {v["value"] for v in r["vehicles"]} == {"samand", "peugeot"}


async def test_filters(client, api):
    api["/gen/api/filters/region"] = fixture("region.json")
    api["/gen/api/filters/fuel"] = fixture("fuel.json")
    r = (await client.call_tool("ba_filters", {"kind": "region"})).structured_content
    assert {v["value"] for v in r["values"]} == {"tehran", "isfahan"}
    r = (await client.call_tool("ba_filters", {"kind": "region", "query": "isfahan"})).structured_content
    assert r["values"] and all("isfahan" in v["value"] for v in r["values"])
    r = (await client.call_tool("ba_filters", {"kind": "fuel"})).structured_content
    assert "gasoline" in {v["value"] for v in r["values"]}
    assert ("vehicleCategory", "car") in q(api.calls[-1])


async def test_new_prices(client, api):
    api["/cad/api/price/detail"] = fixture("prices.json")
    r = (
        await client.call_tool("ba_new_prices", {"brand": "samand", "model": "soren", "history_days": 2})
    ).structured_content
    row = r["prices"][0]
    assert row["price_toman"] == 3_000_000_000 and row["provider"] == "قیمت بازار" and len(row["history"]) == 2
    assert row["trend"]["to_toman"] == 3_000_000_000
    assert ("model", "soren") in q(api.calls[0])


async def test_new_prices_empty_is_an_error(client, api):
    api["/cad/api/price/detail"] = {"status": True, "data": {"items": []}}
    r = await client.call_tool("ba_new_prices", {"brand": "nope"})
    assert r.is_error and "No price list" in r.content[0].text


async def test_browser_check_page_is_reported(client, api):
    api["/cad/api/search"] = lambda request: httpx.Response(200, text="<html>checking your browser</html>")
    r = await client.call_tool("ba_search", {})
    assert r.is_error and "browser check" in r.content[0].text


async def test_host_allowlist_and_cache(api):
    api["/cad/api/price/detail"] = {"status": True}
    await http.fetch("/cad/api/price/detail", {"brand": "a"})
    await http.fetch("/cad/api/price/detail", {"brand": "a"})
    assert len(api.calls) == 1
    assert json.dumps(cars._stats([1, 2, 3, 4])) == '{"n": 4, "min": 1, "p25": 1, "median": 2, "p75": 3, "max": 4}'


async def test_ad_stats_and_similar(client, api):
    api["/cad/api/detail/4avpuyq7"] = fixture("detail.json")
    api["/cad/api/relatedads/search"] = fixture("related.json")
    r = (await client.call_tool("ba_ad", {"code": "4avpuyq7", "similar": 3})).structured_content
    assert r["kind"] == "car" and r["ads_of_same_model"] == 146 and r["ads_of_same_trim"] == 86
    assert r["similar_total"] == 519 and r["similar"][0]["url"].startswith("https://bama.ir/car/detail-")
    assert ("pageSize", "3") in q(api.calls[-1])


async def test_ad_auto_finds_motorcycle(client, api):
    api["/mad/api/detail/q61rdrd8"] = fixture("detail_moto.json")
    r = (await client.call_tool("ba_ad", {"code": "q61rdrd8"})).structured_content
    assert r["kind"] == "motorcycle" and r["price_toman"] == 580_000_000 and r["engine"] == "300 cc"
    assert [c.url.path for c in api.calls] == ["/cad/api/detail/q61rdrd8", "/mad/api/detail/q61rdrd8"]


async def test_search_bikes_trucks(client, api):
    api["/mad/api/search"] = fixture("search_moto.json")
    r = (
        await client.call_tool(
            "ba_search_bikes_trucks",
            {"kind": "motorcycle", "vehicle": ["benelli"], "body": ["race"], "sort": "cheapest"},
        )
    ).structured_content
    assert r["kind"] == "motorcycle" and r["count"] == 3 and r["ads"][0]["engine"] == "300 cc"
    assert ("body", "race") in q(api.calls[0]) and ("sort", "4") in q(api.calls[0])
    api["/tad/api/search"] = fixture("search_moto.json")
    await client.call_tool("ba_search_bikes_trucks", {"kind": "truck", "usage": ["tractor"]})
    assert ("usage", "tractor") in q(api.calls[1])


async def test_dealer_ads_filter_and_sort(client, api):
    api["/cad/api/Corporation/5910"] = fixture("corp.json")
    api["/cad/api/Corporation/ads/5910"] = fixture("corp_ads.json")
    r = (await client.call_tool("ba_dealer_ads", {"dealer_id": 5910, "sort": "newest", "limit": 2})).structured_content
    assert r["dealer"]["name"] == "Auto F" and r["ads_fetched"] == 4 and len(r["ads"]) == 2
    r = (await client.call_tool("ba_dealer_ads", {"dealer_id": 5910, "query": "zzzz"})).structured_content
    assert r["matching"] == 0 and r["ads"] == []


async def test_price_list(client, api):
    api["/cad/api/price/hierarchy"] = fixture("hierarchy.json")
    r = (
        await client.call_tool("ba_price_list", {"search": "soren", "price_type": "market", "sort": "cheapest"})
    ).structured_content
    prices = [p["price_toman"] for p in r["prices"]]
    assert prices and prices == sorted(prices)
    assert ("searchQuery", "soren") in q(api.calls[0]) and ("priceType", "MarketPrice") in q(api.calls[0])


async def test_market_pulse(client, api):
    api["/gen/api/HomePage/market-pulse"] = fixture("pulse.json")
    api["/cad/api/Price/slider"] = fixture("slider.json")
    r = (await client.call_tool("ba_market_pulse", {"movers": 3})).structured_content
    assert r["score"] == 74 and len(r["markets"]) == 3 and len(r["movers"]) == 3
    assert r["movers"][0]["change_percent"] == 25


async def test_car_specs(client, api):
    api["/nws/api/CarReview/modelsbybrand"] = fixture("rv_models.json")
    api["/nws/api/CarReview/carreviewdetail"] = fixture("rv_detail.json")
    api["/nws/api/CarReview/getspecification"] = fixture("rv_spec.json")
    r = (await client.call_tool("ba_car_specs", {"brand": "samand"})).structured_content
    assert "soren" in {m["model"] for m in r["models"]}
    r = (await client.call_tool("ba_car_specs", {"brand": "samand", "model": "soren"})).structured_content
    assert r["rating"] == 2.3 and r["specs"]["عملکرد فنی"]["قدرت"].startswith("113")
    assert ("url", "/car-reviews/samand/soren-specs-1113-459-plus") in q(api.calls[1])
    assert ("id", "2491") in q(api.calls[2]) and ("trimname", "plus") in q(api.calls[2])
    bad = await client.call_tool("ba_car_specs", {"brand": "samand", "model": "nope"})
    assert bad.is_error and "soren" in bad.content[0].text


async def test_new_prices_trim_param(client, api):
    api["/cad/api/price/detail"] = fixture("price_trim.json")
    await client.call_tool("ba_new_prices", {"brand": "samand", "model": "soren", "trim": "pluscng"})
    assert ("trim", "pluscng") in q(api.calls[0])


async def test_vehicle_type_lists(client, api):
    api["/gen/api/filters/vehicle"] = fixture("vehicles.json")
    await client.call_tool("ba_vehicles", {"query": "soren", "vehicle_type": "motorcycle"})
    assert ("vehicleCategory", "motorcycle") in q(api.calls[0])


async def test_request_headers_match_the_sites_frontend(api):
    api["/cad/api/search"] = {}
    await http.fetch("/cad/api/search", {"pageIndex": 1})
    h = api.calls[-1].headers
    assert h["accept"] == "*/*" and h["referer"] == "https://bama.ir/car" and "origin" not in h
    assert (h["sec-fetch-site"], h["sec-fetch-mode"], h["sec-fetch-dest"]) == ("same-origin", "cors", "empty")
    assert h["priority"] == "u=1, i" and h["x-market-name"] == "Web_Desktop"
    assert len(h["x-user-context"]) == 36 and h["accept-language"].startswith("fa-IR")
