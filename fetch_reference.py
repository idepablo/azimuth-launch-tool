import json
import os
from datetime import datetime, timezone

import requests

# Reference data (agencies, launcher configurations) comes from the
# development mirror to stay inside the production rate limit. Coverage
# against launch data is verified downstream (see docs/scope.md).
BASE = "https://lldev.thespacedevs.com/2.3.0"
RAW_DIR = "raw_reference"
INGEST_DATE = datetime.now(timezone.utc).strftime("%Y%m%d")


def fetch_all(endpoint, params):
    """Fetch every page of an endpoint, saving raw JSON per page.

    This script only fetches. Flattening lives in flatten_reference.py,
    the same split as fetch_launches.py / flatten_launches.py, so the
    flatten can be re-run from the raw archive without calling the API.
    """
    os.makedirs(RAW_DIR, exist_ok=True)
    url = f"{BASE}/{endpoint}/"
    page = 1

    while url:
        r = requests.get(url, params=params)
        r.raise_for_status()
        data = r.json()

        raw_path = os.path.join(RAW_DIR, f"{endpoint}_{INGEST_DATE}_page{page:03d}.json")
        with open(raw_path, "w") as f:
            json.dump(data, f)

        print(f"{endpoint}: page {page}, {len(data['results'])} records")
        url = data["next"]
        params = None  # next URL carries its own params
        page += 1


if __name__ == "__main__":
    fetch_all("agencies", {"limit": 100, "mode": "detailed"})
    fetch_all("launcher_configurations", {"limit": 100, "mode": "detailed"})
    print("Done. Run flatten_reference.py next.")
