import glob
import json
import os

import pandas as pd

RAW_DIR = "raw_reference"
STAGING_DIR = "staging"


def dig(record, *keys):
    """Walk down nested keys, returning None if anything is missing."""
    value = record
    for key in keys:
        if value is None:
            return None
        value = value.get(key)
    return value


def as_text(value):
    """Stringify a value before it reaches pandas.

    Converting after the DataFrame is built is too late: pandas turns an
    integer column that contains nulls into floats at construction time,
    so 2020 becomes "2020.0". Converting each value first avoids that.
    """
    return None if value is None else str(value)


def latest_snapshot(endpoint):
    """Return the raw pages for the most recent ingest date of an endpoint."""
    paths = sorted(glob.glob(os.path.join(RAW_DIR, f"{endpoint}_*_page*.json")))
    if not paths:
        raise SystemExit(f"No raw files for {endpoint}. Run fetch_reference.py first.")
    latest_date = max(os.path.basename(p).split("_")[-2] for p in paths)
    return [p for p in paths if f"_{latest_date}_" in p], latest_date


def load_records(endpoint):
    paths, ingest_date = latest_snapshot(endpoint)
    records = []
    for path in paths:
        with open(path) as f:
            records.extend(json.load(f)["results"])
    print(f"{endpoint}: {len(records)} records from {len(paths)} files ({ingest_date})")
    return records, ingest_date


def flatten_agency(a, ingest_date):
    countries = a.get("country") or []
    first = countries[0] if countries else None
    return {
        "agency_id": as_text(a.get("id")),
        "agency_name": as_text(a.get("name")),
        "abbrev": as_text(a.get("abbrev")),
        "agency_type": as_text(dig(a, "type", "name")),
        "country_name": as_text(dig(first, "name")) if first else None,
        "country_code": as_text(dig(first, "alpha_3_code")) if first else None,
        "country_count": as_text(len(countries)),
        "founding_year": as_text(a.get("founding_year")),
        "source_endpoint": "agencies",
        "ingest_date": ingest_date,
    }


def flatten_configuration(c, ingest_date):
    return {
        "config_id": as_text(c.get("id")),
        "config_name": as_text(c.get("name")),
        "full_name": as_text(c.get("full_name")),
        "variant": as_text(c.get("variant")),
        "manufacturer_name": as_text(dig(c, "manufacturer", "name")),
        "active": as_text(c.get("active")),
        "reusable": as_text(c.get("reusable")),
        "is_placeholder": as_text(c.get("is_placeholder")),
        "leo_capacity": as_text(c.get("leo_capacity")),
        "gto_capacity": as_text(c.get("gto_capacity")),
        "apogee": as_text(c.get("apogee")),
        "maiden_flight": as_text(c.get("maiden_flight")),
        "source_endpoint": "launcher_configurations",
        "ingest_date": ingest_date,
    }


def flatten_families(c, ingest_date):
    """One row per (configuration, family).

    A configuration lists its family and every ancestor of that family
    (Falcon 9 Block 5 lists "Falcon" and "Falcon 9", whose parent is
    "Falcon"). The hierarchy is resolved in dbt, not here.
    """
    rows = []
    for fam in c.get("families") or []:
        parent = fam.get("parent")
        parent_name = parent.get("name") if isinstance(parent, dict) else parent
        rows.append({
            "config_id": as_text(c.get("id")),
            "family_id": as_text(fam.get("id")),
            "family_name": as_text(fam.get("name")),
            "parent_family_name": as_text(parent_name),
            "source_endpoint": "launcher_configurations",
            "ingest_date": ingest_date,
        })
    return rows


def to_parquet(rows, filename):
    df = pd.DataFrame(rows).astype("string")
    os.makedirs(STAGING_DIR, exist_ok=True)
    path = os.path.join(STAGING_DIR, filename)
    df.to_parquet(path, index=False)
    print(f"Wrote {path}: {len(df)} rows, {len(df.columns)} columns")


if __name__ == "__main__":
    agencies, agency_date = load_records("agencies")
    to_parquet([flatten_agency(a, agency_date) for a in agencies], "agencies.parquet")

    configs, config_date = load_records("launcher_configurations")
    to_parquet([flatten_configuration(c, config_date) for c in configs], "configurations.parquet")

    family_rows = [row for c in configs for row in flatten_families(c, config_date)]
    to_parquet(family_rows, "configuration_families.parquet")
