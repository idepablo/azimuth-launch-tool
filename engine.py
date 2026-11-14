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
        return _like_databricks(cur.df(), [(d[0], str(d[1])) for d in cur.description])
    return cur.fetchall_arrow().to_pandas()


def _like_databricks(df, types):
    """Give DuckDB results the same pandas types the Databricks export had,
    so the app reads an identical snapshot whichever engine built it."""
    for col, kind in types:
        kind = kind.upper()
        if kind == "DATE":
            df[col] = df[col].dt.date.astype("object").where(df[col].notna(), None)
        elif kind.startswith("TIMESTAMP"):
            df[col] = df[col].dt.tz_localize("UTC") if df[col].dt.tz is None else df[col]
        elif kind in ("HUGEINT", "BIGINT", "INTEGER"):
            # sums come back as HUGEINT (decimals in pandas); nullable
            # integers came back from Databricks as floats
            if df[col].isna().any():
                df[col] = df[col].astype("float64")
            else:
                df[col] = df[col].astype("int32" if kind == "INTEGER" else "int64")
    return df
