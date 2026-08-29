import json
import os
from datetime import datetime, timezone

import pandas as pd
import requests

BASE = "https://lldev.thespacedevs.com/2.3.0"
RAW_DIR = "raw_reference"
STAGING_DIR = "staging"
INGEST_DATE = datetime.now(timezone.utc).strftime("%Y%m%d")


def dig(record, *keys):
    """Walk down nested keys, returning None if anything is missing."""
    value = record
    for key in keys:
        if value is None:
            return None
        value = value.get(key)
    return value


def fetch_all(endpoint, params):
    """Fetch every page of an endpoint, saving raw JSON per page."""
    os.makedirs(RAW_DIR, exist_ok=True)
    results = []
    url = f"{BASE}/{endpoint}/"
    page = 1

    while url:
        r = requests.get(url, params=params)
        r.raise_for_status()
        data = r.json()

        raw_path = os.path.join(RAW_DIR, f"{endpoint}_{INGEST_DATE}_page{page:03d}.json")
        with open(raw_path, "w") as f:
            json.dump(data, f)

        results.extend(data["results"])
        print(f"{endpoint}: page {page}, {len(data['results'])} records")
        url = data["next"]
        params = None  # next URL carries its own params
        page += 1

    return results


def flatten_agency(a):
    countries = a.get("country") or []
    first = countries[0] if countries else None
    return {
        "agency_id": a.get("id"),
        "agency_name": a.get("name"),
        "abbrev": a.get("abbrev"),
        "agency_type": dig(a, "type", "name"),
        "country_name": dig(first, "name") if first else None,
        "country_code": dig(first, "alpha_3_code") if first else None,
        "country_count": len(countries),
        "founding_year": a.get("founding_year"),
        "source_endpoint": "agencies",
        "ingest_date": INGEST_DATE,
    }


def flatten_configuration(c):
    return {
        "config_id": c.get("id"),
        "config_name": c.get("name"),
        "full_name": c.get("full_name"),
        "variant": c.get("variant"),
        "manufacturer_name": dig(c, "manufacturer", "name"),
        "active": c.get("active"),
        "reusable": c.get("reusable"),
        "is_placeholder": c.get("is_placeholder"),
        "leo_capacity": c.get("leo_capacity"),
        "gto_capacity": c.get("gto_capacity"),
        "apogee": c.get("apogee"),
        "maiden_flight": c.get("maiden_flight"),
        "source_endpoint": "launcher_configurations",
        "ingest_date": INGEST_DATE,
    }


def to_parquet(rows, filename):
    df = pd.DataFrame(rows).astype("string")
    os.makedirs(STAGING_DIR, exist_ok=True)
    path = os.path.join(STAGING_DIR, filename)
    df.to_parquet(path, index=False)
    print(f"Wrote {path}: {len(df)} rows, {len(df.columns)} columns")


agencies = fetch_all("agencies", {"limit": 100, "mode": "detailed"})
to_parquet([flatten_agency(a) for a in agencies], "agencies.parquet")

configs = fetch_all("launcher_configurations", {"limit": 100, "mode": "detailed"})
to_parquet([flatten_configuration(c) for c in configs], "configurations.parquet")