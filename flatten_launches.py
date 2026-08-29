import json
import os
import glob
import pandas as pd

RAW_DIR = "raw"
OUTPUT_FILE = "staging/launches.parquet"


def dig(record, *keys):
    """Walk down nested keys, returning None if anything is missing."""
    value = record
    for key in keys:
        if value is None:
            return None
        value = value.get(key)
    return value


def flatten_launch(launch, source_file, ingest_date):
    return {
        "launch_id": launch.get("id"),
        "name": launch.get("name"),
        "slug": launch.get("slug"),
        "net": launch.get("net"),
        "net_precision_name": dig(launch, "net_precision", "name"),
        "last_updated": launch.get("last_updated"),
        "status_id": dig(launch, "status", "id"),
        "status_name": dig(launch, "status", "name"),
        "provider_id": dig(launch, "launch_service_provider", "id"),
        "provider_name": dig(launch, "launch_service_provider", "name"),
        "config_id": dig(launch, "rocket", "configuration", "id"),
        "config_name": dig(launch, "rocket", "configuration", "name"),
        "mission_id": dig(launch, "mission", "id"),
        "mission_name": dig(launch, "mission", "name"),
        "orbit_id": dig(launch, "mission", "orbit", "id"),
        "orbit_name": dig(launch, "mission", "orbit", "name"),
        "pad_id": dig(launch, "pad", "id"),
        "pad_name": dig(launch, "pad", "name"),
        "pad_latitude": dig(launch, "pad", "latitude"),
        "pad_longitude": dig(launch, "pad", "longitude"),
        "location_id": dig(launch, "pad", "location", "id"),
        "location_name": dig(launch, "pad", "location", "name"),
        "location_country": dig(launch, "pad", "location", "country", "name"),
        "location_country_code": dig(launch, "pad", "location", "country", "alpha_3_code"),
        "celestial_body": dig(launch, "pad", "location", "celestial_body", "name"),
        "source_file": source_file,
        "ingest_date": ingest_date,
    }


def flatten_all():
    files = sorted(glob.glob(os.path.join(RAW_DIR, "*.json")))
    print(f"Found {len(files)} raw files")

    rows = []
    for path in files:
        filename = os.path.basename(path)
        ingest_date = filename.split("_")[1]

        with open(path) as f:
            data = json.load(f)

        for launch in data["results"]:
            rows.append(flatten_launch(launch, filename, ingest_date))

    df = pd.DataFrame(rows)
    print(f"Flattened {len(df)} rows")
    print(f"Unique launch ids: {df['launch_id'].nunique()}")

    os.makedirs("staging", exist_ok=True)
    df.to_parquet(OUTPUT_FILE, index=False)
    print(f"Wrote {OUTPUT_FILE}")

    return df


df = flatten_all()
print(df.head())