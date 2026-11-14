"""Incremental refresh of bronze launches, DuckDB version.

Same logic as refresh.py (the Databricks version): the watermark is the
latest last_updated in bronze minus one day, the API is asked only for
launches changed since then, in last_updated order, and each page is
archived and merged. Here bronze is a parquet file (see bronze_local.py)
instead of a Delta table, and it is written once at the end.
"""
import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

import bronze_local
from fetch_launches import fetch_page, SLEEP_SECONDS
from flatten_launches import flatten_launch

BASE_URL = "https://ll.thespacedevs.com/2.3.0/launches/previous/"
PAGE_SIZE = 100
OVERLAP = timedelta(days=1)


def as_text(value):
    """Stringify before pandas sees the value, so '15' does not become '15.0'."""
    return None if value is None else str(value)


def annotate(level, message):
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::{level} title=Launch refresh::{message}")
    else:
        print(message)


def refresh():
    bronze = bronze_local.read("launches")
    latest = pd.to_datetime(bronze["last_updated"], utc=True).max()
    since = (latest - OVERLAP).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"Bronze holds {len(bronze)} launches. Fetching launches updated since {since}")

    run_started = datetime.now(timezone.utc)
    ingest_date = run_started.strftime("%Y%m%d")
    run_tag = run_started.strftime("%H%M")

    url = BASE_URL
    params = {"limit": PAGE_SIZE, "last_updated__gte": since, "ordering": "last_updated"}
    page, rows = 1, []
    while url:
        data = fetch_page(url, params)
        params = None  # the next URL carries its own params
        filename = f"launches_{ingest_date}_incr{run_tag}_page{page:03d}.json"
        bronze_local.archive_page(filename, data)
        rows += [{k: as_text(v) for k, v in flatten_launch(launch, filename, ingest_date).items()}
                 for launch in data["results"]]
        print(f"Page {page}: {len(data['results'])} records")
        url = data["next"]
        page += 1
        if url and SLEEP_SECONDS > 0:
            time.sleep(SLEEP_SECONDS)

    if rows:
        merged, inserted, updated = bronze_local.merge_launches(
            bronze, pd.DataFrame(rows).astype("string"))
        bronze_local.write("launches", merged)
    else:
        merged, inserted, updated = bronze, 0, 0

    annotate("notice",
             f"{len(rows)} changed launches since {since} ({page - 1} pages): "
             f"{inserted} new, {updated} updated. Bronze now holds {len(merged)} launches.")


if __name__ == "__main__":
    refresh()
