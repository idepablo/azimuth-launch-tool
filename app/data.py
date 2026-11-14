"""Loads the gold snapshot the app runs on.

The daily pipeline publishes parquet exports of the gold tables to the
repository's `data` branch (see export_snapshot.py). The app checks the
small manifest every few minutes; the tables are kept in memory and
downloaded again only when the manifest shows a new snapshot. For local
work, set AZIMUTH_DATA_DIR to a folder holding the same files.
"""
import io
import json
import os
import time
import urllib.parse
import urllib.request

import pandas as pd
import streamlit as st

SNAPSHOT_URL = "https://raw.githubusercontent.com/idepablo/azimuth-launch-tool/data"
LOCAL_DIR = os.environ.get("AZIMUTH_DATA_DIR")


def _read(name, snapshot=None):
    if LOCAL_DIR:
        with open(os.path.join(LOCAL_DIR, name), "rb") as f:
            return f.read()
    # the snapshot id in the address skips GitHub's few-minute file cache, so a
    # new manifest is never paired with an older copy of a table
    query = f"?v={urllib.parse.quote(snapshot)}" if snapshot else f"?t={int(time.time() // 300)}"
    with urllib.request.urlopen(f"{SNAPSHOT_URL}/{name}{query}", timeout=30) as response:
        return response.read()


@st.cache_data(ttl=300, show_spinner=False)
def manifest():
    """Small file that changes with every published snapshot. Checked every 5 minutes."""
    return json.loads(_read("manifest.json"))


def version():
    """Identifies the current snapshot; every cached load below is keyed on it,
    so a new snapshot is picked up within minutes instead of waiting out a cache."""
    return manifest()["exported_at"]


def table(name):
    return _table(name, version())


@st.cache_data(max_entries=40, show_spinner="Loading launch data...")
def _table(name, snapshot):
    return pd.read_parquet(io.BytesIO(_read(f"{name}.parquet", snapshot)))


def ask_eval():
    """Latest Ask AZIMUTH exam results (analysis/ask_eval.py), or None."""
    return _json_or_none("ask_eval.json", version())


def backtest():
    """Simulator backtest results (analysis/backtest.py), or None if not published yet."""
    return _json_or_none("backtest.json", version())


@st.cache_data(max_entries=10, show_spinner=False)
def _json_or_none(name, snapshot):
    try:
        return json.loads(_read(name, snapshot))
    except Exception:
        return None
