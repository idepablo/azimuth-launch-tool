"""Copy the flattened reference snapshots into bronze (DuckDB version).

Same tables as load_reference.py writes to Databricks: each run replaces
them with the latest snapshot from the API.
"""
import pandas as pd

import bronze_local

TABLES = {
    "agencies": "staging/agencies.parquet",
    "launcher_configurations": "staging/configurations.parquet",
    "launcher_families": "staging/configuration_families.parquet",
}

if __name__ == "__main__":
    for table, staged in TABLES.items():
        df = pd.read_parquet(staged)
        bronze_local.write(table, df)
        print(f"{table}: {len(df)} rows in bronze")
