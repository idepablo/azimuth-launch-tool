"""Completeness check: does bronze hold every launch the API knows about?

Matching row counts rule out duplicates but not gaps (the open item from
Phase 1): offset pagination over a dataset that shifts while you page
through it can skip records without any error. This compares bronze with
the API's own count of past launches.

  bronze < API  -> launches are missing: fail, so the run shows red.
                   The fix is a full backfill (fetch_launches.py).
  bronze > API  -> the source removed records that bronze still holds:
                   reported, not a failure, since bronze keeps history.
  equal         -> pass.

One API call, so it fits inside the production rate limit.
"""
import os
import sys

from fetch_launches import fetch_page
from load_to_bronze import CATALOG, SCHEMA, TABLE, get_connection

API_URL = "https://ll.thespacedevs.com/2.3.0/launches/previous/"


def annotate(level, message):
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::{level} title=Completeness check::{message}")
    else:
        print(message)


def main():
    # fetch_page waits out a 429, in case the refresh just used the hour's quota
    api_count = fetch_page(API_URL, {"limit": 1, "mode": "list"})["count"]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.{TABLE}")
            bronze_count = cur.fetchone()[0]

    gap = api_count - bronze_count
    if gap > 0:
        annotate("error", f"Bronze has {bronze_count} launches, the API has {api_count}: "
                          f"{gap} missing. Run a full backfill.")
        sys.exit(1)
    elif gap < 0:
        annotate("notice", f"Bronze has {bronze_count} launches, the API has {api_count}: "
                           f"{-gap} removed upstream and kept in bronze.")
    else:
        annotate("notice", f"Bronze and the API agree: {api_count} launches.")


if __name__ == "__main__":
    main()
