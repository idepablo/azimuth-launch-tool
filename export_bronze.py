"""One-time copy of bronze from Databricks to parquet (the `bronze` branch).

Used once, when the daily refresh moved from Databricks to DuckDB, so the
new bronze starts from exactly the data Databricks held. Can be rerun from
the "Export bronze from Databricks" workflow if ever needed.

Usage: python export_bronze.py <output_dir>
"""
import os
import sys

from load_to_bronze import get_connection

TABLES = ["launches", "agencies", "launcher_configurations", "launcher_families"]


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with get_connection() as conn:
        with conn.cursor() as cur:
            for table in TABLES:
                cur.execute(f"SELECT * FROM azimuth.bronze.{table}")
                df = cur.fetchall_arrow().to_pandas().astype("string")
                df.to_parquet(os.path.join(out_dir, f"{table}.parquet"), index=False)
                print(f"{table}: {len(df)} rows")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "bronze")
