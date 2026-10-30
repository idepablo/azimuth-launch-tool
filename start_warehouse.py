"""Start the SQL warehouse and wait until it is running.

Databricks Free Edition sometimes refuses to start the warehouse when a
connection has to wake it ("Cannot create the resource, please try again
later"), while an explicit start works. So every pipeline job starts it
first. Uses the warehouse in DBT_DATABRICKS_HTTP_PATH if set, otherwise the
first one in the workspace (the same one the load scripts use).
"""
import os
from datetime import timedelta

from databricks.sdk import WorkspaceClient


def main():
    w = WorkspaceClient(host=os.environ["DATABRICKS_HOST"], token=os.environ["DATABRICKS_TOKEN"])
    http_path = os.environ.get("DBT_DATABRICKS_HTTP_PATH", "")
    warehouse_id = http_path.rstrip("/").split("/")[-1] if http_path else \
        list(w.warehouses.list())[0].id
    state = w.warehouses.get(warehouse_id).state.value
    print(f"Warehouse state: {state}")
    if state != "RUNNING":
        w.warehouses.start_and_wait(warehouse_id, timeout=timedelta(minutes=10))
    print("Warehouse running")


if __name__ == "__main__":
    main()
