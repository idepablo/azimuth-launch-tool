import os
import time
import uuid
from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv
from databricks.sdk import WorkspaceClient
from databricks import sql

load_dotenv()

HOST = os.environ["DATABRICKS_HOST"]
TOKEN = os.environ["DATABRICKS_TOKEN"]

CATALOG = "azimuth"
SCHEMA = "bronze"
TABLE = "launches"
AUDIT_TABLE = "load_audit"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw"
LOCAL_PARQUET = "staging/launches.parquet"


def upload_to_volume():
    w = WorkspaceClient(host=HOST, token=TOKEN)
    target = f"{VOLUME_PATH}/launches.parquet"
    with open(LOCAL_PARQUET, "rb") as f:
        w.files.upload(target, f, overwrite=True)
    print(f"Uploaded to {target}")
    return target


def get_connection():
    w = WorkspaceClient(host=HOST, token=TOKEN)
    warehouse = list(w.warehouses.list())[0]
    print(f"Using warehouse: {warehouse.name}")
    return sql.connect(
        server_hostname=HOST.replace("https://", ""),
        http_path=warehouse.odbc_params.path,
        access_token=TOKEN,
    )


def ensure_tables(cur, columns):
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.{TABLE} (
            {", ".join(f"{c} STRING" for c in columns)}
        ) USING DELTA
    """)

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.{AUDIT_TABLE} (
            run_id STRING,
            run_timestamp TIMESTAMP,
            source_file STRING,
            rows_in_source BIGINT,
            rows_inserted BIGINT,
            rows_updated BIGINT,
            duration_seconds DOUBLE,
            status STRING
        ) USING DELTA
    """)


def run_merge(cur, volume_file, columns):
    update_set = ", ".join(f"t.{c} = s.{c}" for c in columns if c != "launch_id")
    insert_cols = ", ".join(columns)
    insert_vals = ", ".join(f"s.{c}" for c in columns)

    cur.execute(f"""
        MERGE INTO {CATALOG}.{SCHEMA}.{TABLE} AS t
        USING (SELECT * FROM parquet.`{volume_file}`) AS s
        ON t.launch_id = s.launch_id
        WHEN MATCHED AND s.last_updated > t.last_updated THEN UPDATE SET {update_set}
        WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})
    """)

    result = cur.fetchall()
    if result:
        row = result[0].asDict()
        return row.get("num_inserted_rows", 0), row.get("num_updated_rows", 0)
    return 0, 0


def write_audit(cur, record):
    cur.execute(f"""
        INSERT INTO {CATALOG}.{SCHEMA}.{AUDIT_TABLE} VALUES (
            '{record["run_id"]}',
            '{record["run_timestamp"]}',
            '{record["source_file"]}',
            {record["rows_in_source"]},
            {record["rows_inserted"]},
            {record["rows_updated"]},
            {record["duration_seconds"]},
            '{record["status"]}'
        )
    """)


def load(volume_file):
    df = pd.read_parquet(LOCAL_PARQUET)
    columns = list(df.columns)

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    start = time.time()

    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_tables(cur, columns)
            print("Tables ready")

            try:
                inserted, updated = run_merge(cur, volume_file, columns)
                status = "success"
            except Exception as exc:
                inserted, updated = 0, 0
                status = "failed"
                print(f"Merge failed: {exc}")

            write_audit(cur, {
                "run_id": run_id,
                "run_timestamp": started_at.strftime("%Y-%m-%d %H:%M:%S"),
                "source_file": os.path.basename(volume_file),
                "rows_in_source": len(df),
                "rows_inserted": inserted,
                "rows_updated": updated,
                "duration_seconds": round(time.time() - start, 2),
                "status": status,
            })

            print(f"Run {run_id}")
            print(f"  source rows: {len(df)}")
            print(f"  inserted:    {inserted}")
            print(f"  updated:     {updated}")
            print(f"  status:      {status}")

            cur.execute(f"SELECT COUNT(*) FROM {CATALOG}.{SCHEMA}.{TABLE}")
            print(f"  rows in bronze: {cur.fetchone()[0]}")


target = upload_to_volume()
load(target)