<!-- mcp-name: io.github.sepehr071/bama-ir-mcp -->

# bama-ir-mcp: Bama (باما) Iran car marketplace MCP server for AI agents

**bama-ir-mcp is an unofficial, read-only MCP server that gives AI agents the car ads and price lists of Bama (bama.ir), Iran's car marketplace.**<br>
Its 12 tools search used and new car, motorcycle and truck ads with real filters, read one ad in full, compute asking-price statistics for a model, search and rank the new-car price list, show the daily market mood, return technical specs and expert ratings, browse a dealer's inventory and look up brand, model and filter values.<br>
No API key or Bama account is needed. It works in Claude, Cursor, Copilot and any other MCP client.

[For AI agents](#for-ai-agents) · [Quick start](#quick-start) · [Tools](#tools) · [FAQ](#faq)

---

## For AI agents

- **What:** unofficial MCP server (model context protocol) for bama.ir: car ad search (brand/model/trim, year, price, mileage, city, seller, gearbox, body, fuel, color, paint condition, installment), ad details, market price statistics per model and year, new-car price list with trend, dealers and their inventory, motorcycle and truck ads, technical specs and ratings, market pulse.
- **Install:** `uvx bama-ir-mcp` or `claude mcp add bama -- uvx bama-ir-mcp`. Transport: stdio. Needs [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python 3.10+).
- **Auth:** none. Optional `BAMA_MCP_PROXY` (HTTP proxy URL, or a comma-separated list); system proxy settings are ignored.
- **Access:** read-only. It cannot log in, post ads, message sellers or read phone numbers.
- **Tools:** 12, all prefixed `ba_`. Typical sequences: `ba_vehicles` -> `ba_search` -> `ba_ad`; `ba_vehicles` -> `ba_market_stats`; `ba_new_prices` / `ba_price_list`; `ba_car_specs`; `ba_dealers` -> `ba_dealer_ads`; `ba_filters` -> `ba_search`.
- **Use when:** the user asks what a used or new car costs in Iran, wants listings by model, year, mileage or city, wants to compare asking prices, or needs a dealer.
- **Do not use when:** a car outside Iran, or actual sale prices (these are asking prices).
- **Output:** compact JSON. Prices are Toman, years Jalali (imports may show Gregorian), mileage km, text Persian.

## Quick start

```bash
claude mcp add bama -- uvx bama-ir-mcp
```

Other clients: command `uvx`, args `["bama-ir-mcp"]`.

## Tools

| Tool | What it does |
|---|---|
| `ba_search` | Car ads with filters, 30 per page, sortable. |
| `ba_ad` | One car, motorcycle or truck ad in full, with the real number of ads for that model; optional similar ads. |
| `ba_market_stats` | Min, quartiles, median, max asking price for a model, per year, from live ads. |
| `ba_new_prices` | Today's price of new-car trims (market, factory, dealer) with daily change and trend. |
| `ba_dealers` | Showrooms with ads for a model or city, with address and rating. |
| `ba_search_bikes_trucks` | Motorcycle or truck ads with filters (brand, year, price, city, body, usage...). |
| `ba_dealer_ads` | One dealer's inventory (up to 100 ads) with filters and sorting. |
| `ba_price_list` | Search and rank the daily new-car or motorcycle price list by brand, price type, origin. |
| `ba_market_pulse` | Today's market score and analysis plus the biggest new-car price movers. |
| `ba_car_specs` | Technical specs, expert rating, pros and cons, trims of a car or motorcycle model. |
| `ba_vehicles` | Brand, model and trim values for the other tools (cars, motorcycles, trucks). |
| `ba_filters` | Values for region, body, fuel, color, country, truck usage and other filters. |

## FAQ

**Does it need the internet from Iran?** Bama answers from inside Iran and through most proxies. Set `BAMA_MCP_PROXY` to route through one.

**Why a sample, not a total?** Bama gives no result count and 30 ads per page; `ba_market_stats` samples up to 5 pages and says so.

**Is it allowed?** It calls the same public JSON the website uses, serially and with caching. It does not bypass any browser check.

Author: Sepehr Radmard (سپهر رادمرد), github.com/sepehr071, linkedin.com/in/sepehr-radmard. MIT licensed. Not affiliated with Bama.
