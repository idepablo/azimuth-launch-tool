"""Incremental refresh of bronze.launches.

The Phase 1 backfill fetched the full launch history once. This script
keeps it current: it asks the API only for launches whose record changed
since the newest one already in bronze, and merges them in.

How it works:
  1. Watermark: the latest last_updated in bronze, minus a one-day
     overlap so records edited during the previous run are not missed.
     The merge is idempotent, so overlap only costs a few repeated rows.
  2. Fetch launches/previous filtered by last_updated, ordered by
     last_updated ascending, 100 per page, throttled for the production
     rate limit.
  3. Each page is archived as raw JSON in the bronze volume (the raw
     archive stays the source of truth), flattened, and merged into
     bronze right away, with one audit row per page.

Merging page by page in last_updated order means an interrupted run
keeps everything it loaded, and the next run's watermark resumes from
there. New launches are covered too: a launch that has just flown gets
its status updated, which moves its last_updated forward.
"""
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pandas as pd
from databricks.sdk import WorkspaceClient

from fetch_launches import fetch_page, SLEEP_SECONDS
from flatten_launches import flatten_launch
from load_to_bronze import (
    CATALOG, SCHEMA, TABLE, VOLUME_PATH, HOST, TOKEN,
    get_connection, ensure_tables, run_merge, write_audit,
)

BASE_URL = "https://ll.thespacedevs.com/2.3.0/launches/previous/"
PAGE_SIZE = 100
OVERLAP = timedelta(days=1)
RAW_DIR = "raw"
STAGING_FILE = "staging/launches_incremental.parquet"
ARCHIVE_PATH = f"{VOLUME_PATH}/launches_archive"


def as_text(value):
    """Stringify before pandas sees the value (see flatten_reference.py).

    Bronze is all strings. Converting each value first keeps nullable
    integers like mission_id from arriving as '15.0'.
    """
    return None if value is None else str(value)


def annotate(level, message):
    """Print a GitHub Actions annotation, so results show on the run page."""
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::{level} title=Launch refresh::{message}")
    else:
        print(message)


def get_watermark(cur):
    cur.execute(f"""
        SELECT max(cast(last_updated AS timestamp))
        FROM {CATALOG}.{SCHEMA}.{TABLE}
    """)
    latest = cur.fetchone()[0]
    if latest is None:
        raise RuntimeError("bronze.launches is empty: run the full backfill first")
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    return latest - OVERLAP


def archive_raw(w, local_path):
    target = f"{ARCHIVE_PATH}/{os.path.basename(local_path)}"
    with open(local_path, "rb") as f:
        w.files.upload(target, f, overwrite=True)


def page_to_parquet(w, data, filename, ingest_date):
    rows = [
        {k: as_text(v) for k, v in flatten_launch(launch, filename, ingest_date).items()}
        for launch in data["results"]
    ]
    df = pd.DataFrame(rows)

    # a record edited mid-fetch can show up twice; keep its latest version,
    # because MERGE needs one source row per launch_id
    df = (df.sort_values("last_updated")
            .drop_duplicates("launch_id", keep="last")
            .reset_index(drop=True))

    os.makedirs(os.path.dirname(STAGING_FILE), exist_ok=True)
    df.to_parquet(STAGING_FILE, index=False)

    target = f"{VOLUME_PATH}/launches_incremental.parquet"
    with open(STAGING_FILE, "rb") as f:
        w.files.upload(target, f, overwrite=True)
    return df, target


def refresh():
    os.makedirs(RAW_DIR, exist_ok=True)
    w = WorkspaceClient(host=HOST, token=TOKEN)
    run_started = datetime.now(timezone.utc)
    ingest_date = run_started.strftime("%Y%m%d")
    run_tag = run_started.strftime("%H%M")

    totals = {"pages": 0, "records": 0, "inserted": 0, "updated": 0}

    with get_connection() as conn:
        with conn.cursor() as cur:
            watermark = get_watermark(cur)
            since = watermark.strftime("%Y-%m-%dT%H:%M:%SZ")
            print(f"Fetching launches updated since {since}")

            url = BASE_URL
            params = {
                "limit": PAGE_SIZE,
                "last_updated__gte": since,
                "ordering": "last_updated",
            }
            page = 1

            while url:
                data = fetch_page(url, params)
                params = None  # the next URL carries its own params

                # same naming as the backfill, so split("_")[1] is still the
                # ingest date; 'incr' plus the run time keeps runs apart
                filename = f"launches_{ingest_date}_incr{run_tag}_page{page:03d}.json"
                local_path = os.path.join(RAW_DIR, filename)
                with open(local_path, "w") as f:
                    json.dump(data, f)
                archive_raw(w, local_path)

                if data["results"]:
                    df, volume_file = page_to_parquet(w, data, filename, ingest_date)
                    columns = list(df.columns)
                    ensure_tables(cur, columns)

                    start = time.time()
                    try:
                        inserted, updated = run_merge(cur, volume_file, columns)
                        status = "success"
                    except Exception as exc:
                        inserted, updated, status = 0, 0, "failed"
                        print(f"Merge failed on page {page}: {exc}")

                    write_audit(cur, {
                        "run_id": str(uuid.uuid4()),
                        "run_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                        "source_file": filename,
                        "rows_in_source": len(df),
                        "rows_inserted": inserted,
                        "rows_updated": updated,
                        "duration_seconds": round(time.time() - start, 2),
                        "status": status,
                    })
                    if status == "failed":
                        raise RuntimeError(f"Merge failed on page {page}; earlier pages are kept")

                    totals["records"] += len(df)
                    totals["inserted"] += inserted
                    totals["updated"] += updated
                    print(f"Page {page}: {len(df)} records, "
                          f"{inserted} inserted, {updated} updated")

                totals["pages"] += 1
                url = data["next"]
                page += 1
                if url and SLEEP_SECONDS > 0:
                    time.sleep(SLEEP_SECONDS)

            cur.execute(f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.{TABLE}")
            bronze_rows = cur.fetchone()[0]

    annotate("notice",
             f"{totals['records']} changed launches since {since} "
             f"({totals['pages']} pages): {totals['inserted']} new, "
             f"{totals['updated']} updated. Bronze now holds {bronze_rows} launches.")


if __name__ == "__main__":
    refresh()
