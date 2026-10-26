"""Loads the gold snapshot the app runs on.

The daily pipeline publishes parquet exports of the gold tables to the
repository's `data` branch (see export_snapshot.py). The app downloads
them once an hour at most and keeps them in memory. For local work, set
AZIMUTH_DATA_DIR to a folder holding the same files.
"""
import io
import json
import os
import urllib.request

import pandas as pd
import streamlit as st

SNAPSHOT_URL = "https://raw.githubusercontent.com/idepablo/azimuth-launch-tool/data"
LOCAL_DIR = os.environ.get("AZIMUTH_DATA_DIR")


def _read(name):
    if LOCAL_DIR:
        with open(os.path.join(LOCAL_DIR, name), "rb") as f:
            return f.read()
    with urllib.request.urlopen(f"{SNAPSHOT_URL}/{name}", timeout=30) as response:
        return response.read()


@st.cache_data(ttl=3600, show_spinner="Loading launch data...")
def table(name):
    return pd.read_parquet(io.BytesIO(_read(f"{name}.parquet")))


@st.cache_data(ttl=3600, show_spinner=False)
def manifest():
    return json.loads(_read("manifest.json"))


@st.cache_data(ttl=3600, show_spinner=False)
def ask_eval():
    """Latest Ask AZIMUTH exam results (analysis/ask_eval.py), or None."""
    try:
        return json.loads(_read("ask_eval.json"))
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def backtest():
    """Simulator backtest results (analysis/backtest.py), or None if not published yet."""
    try:
        return json.loads(_read("backtest.json"))
    except Exception:
        return None
