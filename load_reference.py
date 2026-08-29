import os

from dotenv import load_dotenv
from databricks.sdk import WorkspaceClient
from databricks import sql

load_dotenv()

HOST = os.environ["DATABRICKS_HOST"]
TOKEN = os.environ["DATABRICKS_TOKEN"]

CATALOG = "azimuth"
SCHEMA = "bronze"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw"

TABLES = {
    "agencies": "staging/agencies.parquet",
    "launcher_configurations": "staging/configurations.parquet",
}


def get_connection():
    w = WorkspaceClient(host=HOST, token=TOKEN)
    warehouse = list(w.warehouses.list())[0]
    print(f"Using warehouse: {warehouse.name}")
    return sql.connect(
        server_hostname=HOST.replace("https://", ""),
        http_path=warehouse.odbc_params.path,
        access_token=TOKEN,
    )


def upload(local_path, table):
    w = WorkspaceClient(host=HOST, token=TOKEN)
    target = f"{VOLUME_PATH}/{table}.parquet"
    with open(local_path, "rb") as f:
        w.files.upload(target, f, overwrite=True)
    print(f"Uploaded {target}")
    return target


with get_connection() as conn:
    with conn.cursor() as cur:
        for table, local_path in TABLES.items():
            volume_file = upload(local_path, table)
            cur.execute(f"""
                CREATE OR REPLACE TABLE {CATALOG}.{SCHEMA}.{table}
                USING DELTA
                AS SELECT * FROM parquet.`{volume_file}`
            """)
            cur.execute(f"SELECT COUNT(*) FROM {CATALOG}.{SCHEMA}.{table}")
            print(f"{table}: {cur.fetchone()[0]} rows in bronze")