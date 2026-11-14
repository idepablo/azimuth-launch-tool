"""Which engine the pipeline reads from: DuckDB (the daily refresh) or Databricks.

The daily refresh runs on DuckDB inside GitHub Actions, because Databricks
Free Edition would not reliably start compute for a scheduled job (see
docs/scope.md, "Where the daily refresh runs"). The Databricks path is kept
and still works. Set AZIMUTH_ENGINE=databricks to use it.

Both expose the same names (azimuth.gold.<table>): the DuckDB file is
called azimuth.duckdb, so its catalog is "azimuth" too.
"""
import os

ENGINE = os.environ.get("AZIMUTH_ENGINE", "duckdb")
DUCKDB_PATH = os.environ.get("AZIMUTH_DUCKDB", "azimuth_dbt/azimuth.duckdb")


def get_connection():
    if ENGINE == "duckdb":
        import duckdb
        return duckdb.connect(DUCKDB_PATH, read_only=True)
    from load_to_bronze import get_connection as databricks_connection
    return databricks_connection()


def fetch_df(cur, query):
    cur.execute(query)
    if ENGINE == "duckdb":
        return cur.df()
    return cur.fetchall_arrow().to_pandas()
