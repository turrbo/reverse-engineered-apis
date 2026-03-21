"""
AutoTempest Unofficial API Client
Reverse-engineered from autotempest.com internal APIs.

Discovered endpoints:
  - /api/get-makes          -- list all car makes
  - /api/get-models/{make}  -- list models for a make
  - /api/truecar/makes-models -- full make/model catalog (new + used)
  - /sh                     -- initialize search session
  - /queue-results          -- fetch car listings (requires HMAC token)
  - /api/facebookMarketplace -- Facebook Marketplace results
  - /api/searchtempest/direct -- SearchTempest/Craigslist results

Token auth: SHA-256(url_params + hash_secret)
"""

import hashlib
import urllib.parse
import requests
from typing import Optional


class AutoTempestClient:
    BASE_URL = "https://www.autotempest.com"
    HASH_SECRET = "d8007486d73c168684860aae427ea1f9d74e502b06d94609691f5f4f2704a07f"

    # Site codes used by AutoTempest
    SITES = {
        "te": "AutoTempest",
        "hem": "Hemmings",
        "cs": "Cars.com",
        "cv": "Carvana",
        "cm": "CarMax",
        "eb": "eBay",
        "ot": "Other",
        "extended": "Extended radius",
        "fbm": "Facebook Marketplace",
        "st": "SearchTempest/Craigslist",
    }

    ALL_SITES = "te|hem|cs|cv|cm|eb|ot|extended|fbm|st"

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.autotempest.com/results",
        })

    @staticmethod
    def _generate_token(params: dict) -> str:
        """Generate HMAC token required for queue-results endpoint."""
        param_str = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        decoded = urllib.parse.unquote(param_str)
        payload = decoded + AutoTempestClient.HASH_SECRET
        return hashlib.sha256(payload.encode()).hexdigest()

    # ── Reference data ──────────────────────────────────────────────

    def get_makes(self, popular_only: bool = True) -> dict:
        """Get list of all car makes."""
        params = {"popularMakes": "true"} if popular_only else {}
        r = self.session.get(f"{self.BASE_URL}/api/get-makes", params=params)
        r.raise_for_status()
        return r.json()

    def get_models(self, make: str, popular_only: bool = True) -> dict:
        """Get models for a given make (e.g. 'toyota', 'bmw')."""
        params = {"popularModels": "true"} if popular_only else {}
        r = self.session.get(
            f"{self.BASE_URL}/api/get-models/{make.lower()}", params=params
        )
        r.raise_for_status()
        return r.json()

    def get_makes_models_catalog(self) -> dict:
        """Get full make/model catalog with slugs and IDs (new + used)."""
        r = self.session.get(f"{self.BASE_URL}/api/truecar/makes-models")
        r.raise_for_status()
        return r.json()

    # ── Search ──────────────────────────────────────────────────────

    def search(
        self,
        make: str,
        zip_code: str,
        radius: int = 100,
        model: str = "",
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_miles: Optional[int] = None,
        max_miles: Optional[int] = None,
        transmission: str = "any",
        fuel: str = "any",
        drive: str = "any",
        body_style: str = "any",
        exterior_color: str = "any",
        sale_by: str = "any",
        sale_type: str = "any",
        keywords: str = "",
        sort: str = "best_match",
        sites: str = "te",
        results_per_page: int = 50,
    ) -> dict:
        """
        Search for car listings across AutoTempest sources.

        Args:
            make: Car make slug (e.g. 'toyota', 'bmw', 'ford')
            zip_code: US zip code for location search
            radius: Search radius in miles (default 100)
            model: Model slug (e.g. 'camry', '3-series'). Empty = all models
            min_year/max_year: Year range filters
            min_price/max_price: Price range filters
            min_miles/max_miles: Mileage range filters
            transmission: 'any', 'man', or 'auto'
            fuel: 'any', 'gas', 'diesel', 'electric', 'hybrid'
            drive: 'any', 'fwd', 'rwd', 'awd', '4wd'
            body_style: 'any', 'sedan', 'coupe', 'suv', 'truck', etc.
            exterior_color: 'any', 'black', 'white', 'red', etc.
            sale_by: 'any', 'dealer', 'private'
            sale_type: 'any', 'auction', 'classified'
            keywords: Free text keywords
            sort: 'best_match', 'price_asc', 'price_desc', 'miles_asc',
                  'miles_desc', 'year_asc', 'year_desc', 'date_asc',
                  'date_desc', 'dist_asc'
            sites: Pipe-separated site codes (default 'te').
                   Options: te, hem, cs, cv, cm, eb, ot, fbm, st
            results_per_page: Number of results (default 50, max 50)

        Returns:
            dict with 'status' (0=ok), 'results' list of car listings
        """
        params = {
            "make": make.lower(),
            "radius": str(radius),
            "originalradius": str(radius),
            "zip": zip_code,
            "sort": sort,
            "sites": sites,
            "deduplicationSites": self.ALL_SITES,
            "rpp": str(min(results_per_page, 50)),
        }

        if model:
            params["model"] = model.lower()
        if min_year:
            params["minyear"] = str(min_year)
        if max_year:
            params["maxyear"] = str(max_year)
        if min_price:
            params["minprice"] = str(min_price)
        if max_price:
            params["maxprice"] = str(max_price)
        if min_miles:
            params["minmiles"] = str(min_miles)
        if max_miles:
            params["maxmiles"] = str(max_miles)
        if transmission != "any":
            params["transmission"] = transmission
        if fuel != "any":
            params["fuel"] = fuel
        if drive != "any":
            params["drive"] = drive
        if body_style != "any":
            params["bodystyle"] = body_style
        if exterior_color != "any":
            params["exterior_color"] = exterior_color
        if sale_by != "any":
            params["saleby"] = sale_by
        if sale_type != "any":
            params["saletype"] = sale_type
        if keywords:
            params["keywords"] = keywords

        token = self._generate_token(params)
        params["token"] = token

        r = self.session.get(f"{self.BASE_URL}/queue-results", params=params)
        r.raise_for_status()
        return r.json()

    def search_all_sources(
        self, make: str, zip_code: str, radius: int = 100, **kwargs
    ) -> dict:
        """Search across all sources and merge results."""
        all_results = []
        for site_code in ["te", "hem", "cs", "cv", "cm", "eb", "ot"]:
            try:
                data = self.search(
                    make=make,
                    zip_code=zip_code,
                    radius=radius,
                    sites=site_code,
                    **kwargs,
                )
                if data.get("status") in (0, 1):  # 0=done, 1=partial/pending
                    for r in data.get("results", []):
                        r["_source"] = self.SITES.get(site_code, site_code)
                    all_results.extend(data.get("results", []))
            except Exception:
                continue
        return {"status": 0, "total": len(all_results), "results": all_results}


# ── Example usage ───────────────────────────────────────────────────

if __name__ == "__main__":
    client = AutoTempestClient()

    # List available makes
    makes = client.get_makes()
    print(f"Available makes: {len(makes.get('popularMakes', []))}")

    # Search for Toyota in Beverly Hills
    results = client.search(
        make="toyota",
        zip_code="90210",
        radius=50,
        max_price=30000,
        min_year=2020,
        sort="price_asc",
    )

    print(f"\nFound {len(results.get('results', []))} listings:")
    for car in results.get("results", [])[:5]:
        print(f"  {car['title']} - {car['price']} - {car['mileage']} mi "
              f"- {car['location']} ({car['distance']} mi away)")
        print(f"    VIN: {car['vin']} | Dealer: {car.get('dealerName', 'N/A')}")
        print(f"    URL: {car['url']}")
        print()
