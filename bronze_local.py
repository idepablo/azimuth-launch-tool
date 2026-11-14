"""Bronze as parquet files, for the DuckDB refresh.

Bronze lives on the repository's `bronze` branch: one parquet file per
table (all columns strings, same as the Databricks bronze tables) plus a
gzipped archive of every raw API page fetched. The workflow checks the
branch out into a folder, the scripts update it, and the workflow pushes it
back only after the dbt build and tests pass.
"""
import gzip
import json
import os

import pandas as pd

BRONZE_DIR = os.environ.get("AZIMUTH_BRONZE_DIR", "bronze")
ARCHIVE_DIR = os.path.join(BRONZE_DIR, "raw_archive")


def path(table):
    return os.path.join(BRONZE_DIR, f"{table}.parquet")


def read(table):
    return pd.read_parquet(path(table)).astype("string")


def write(table, df):
    os.makedirs(BRONZE_DIR, exist_ok=True)
    df.astype("string").to_parquet(path(table), index=False)


def archive_page(filename, data):
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    with gzip.open(os.path.join(ARCHIVE_DIR, filename + ".gz"), "wt") as f:
        json.dump(data, f)


def merge_launches(existing, incoming):
    """Same rule as the Databricks MERGE: insert new launch_ids, and replace an
    existing row only when the incoming last_updated is newer.

    Returns (merged, inserted, updated).
    """
    incoming = (incoming.sort_values("last_updated")
                        .drop_duplicates("launch_id", keep="last"))
    old = existing.set_index("launch_id")["last_updated"]
    known = incoming["launch_id"].isin(old.index)
    newer = known & (incoming["last_updated"].values >
                     old.reindex(incoming["launch_id"]).fillna("").values)
    inserted = int((~known).sum())
    updated = int(newer.sum())

    keep = incoming[~known | newer]
    merged = pd.concat([existing[~existing["launch_id"].isin(keep["launch_id"])], keep],
                       ignore_index=True)
    columns = list(existing.columns) + [c for c in keep.columns if c not in existing.columns]
    return merged[columns], inserted, updated
