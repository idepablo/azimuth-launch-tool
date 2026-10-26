"""Export the gold tables the app reads to parquet, plus a manifest.

The app does not query Databricks. After every successful deploy, CI runs
this script and publishes the files to the repository's `data` branch,
which the app reads. That keeps credentials out of the app, keeps visitor
traffic off the Free Edition compute quota, and makes every chart load
from memory. The whole snapshot is a few MB.

Usage: python export_snapshot.py <output_dir>
"""
import json
import os
import sys
from datetime import datetime, timezone

from load_to_bronze import get_connection

TABLES = {
    "dim_provider": "SELECT * FROM azimuth.gold.dim_provider",
    "dim_vehicle": "SELECT * FROM azimuth.gold.dim_vehicle",
    "fct_launches": """
        SELECT launch_id, launch_name, launched_at, net_precision, provider_key,
               vehicle_key, orbit_name, pad_name, status_name, scope_class,
               is_outcome_known, is_success
        FROM azimuth.gold.fct_launches
    """,
    "mart_cadence_yearly": "SELECT * FROM azimuth.gold.mart_cadence_yearly",
    "mart_market_share_yearly": "SELECT * FROM azimuth.gold.mart_market_share_yearly",
    "mart_maturation": "SELECT * FROM azimuth.gold.mart_maturation",
    "mart_vehicle_reliability": "SELECT * FROM azimuth.gold.mart_vehicle_reliability",
    "mart_debut_curve": "SELECT * FROM azimuth.gold.mart_debut_curve",
    "mart_failure_free_survival": "SELECT * FROM azimuth.gold.mart_failure_free_survival",
}


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    manifest = {"exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "tables": {}}

    with get_connection() as conn:
        with conn.cursor() as cur:
            for name, query in TABLES.items():
                cur.execute(query)
                df = cur.fetchall_arrow().to_pandas()
                df.to_parquet(os.path.join(out_dir, f"{name}.parquet"), index=False)
                manifest["tables"][name] = len(df)
                print(f"{name}: {len(df)} rows")

            cur.execute("SELECT max(launched_at) FROM azimuth.gold.fct_launches "
                        "WHERE is_outcome_known")
            manifest["data_as_of"] = cur.fetchone()[0].strftime("%Y-%m-%d")

    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Data as of {manifest['data_as_of']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "snapshot")
