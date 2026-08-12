import requests
import json
import os
import time
from datetime import datetime, timezone

BASE_URL = "https://ll.thespacedevs.com/2.3.0/launches/previous/"
PAGE_SIZE = 100
SLEEP_SECONDS = 240
RAW_DIR = "raw"
STATE_FILE = "fetch_state.json"
MAX_RETRIES = 5
RETRY_WAIT = 600


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)
        print(f"Resuming from page {state['page']} (run of {state['ingest_date']})")
        return state
    return {
        "url": BASE_URL,
        "page": 1,
        "ingest_date": datetime.now(timezone.utc).strftime("%Y%m%d"),
    }


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def fetch_page(url, params):
    for attempt in range(MAX_RETRIES):
        response = requests.get(url, params=params)
        if response.status_code == 429:
            print(f"  rate limited, waiting {RETRY_WAIT}s (attempt {attempt + 1})")
            time.sleep(RETRY_WAIT)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError("Gave up after repeated rate limiting")


def fetch_all_pages():
    os.makedirs(RAW_DIR, exist_ok=True)
    state = load_state()
    first_request = state["page"] == 1

    while state["url"] is not None:
        print(f"Fetching page {state['page']}...")

        params = {"limit": PAGE_SIZE} if first_request else None
        data = fetch_page(state["url"], params)
        first_request = False

        filename = f"launches_{state['ingest_date']}_page{state['page']:03d}.json"
        path = os.path.join(RAW_DIR, filename)
        with open(path, "w") as f:
            json.dump(data, f)

        print(f"  saved {len(data['results'])} records to {path}")

        state["url"] = data["next"]
        state["page"] = state["page"] + 1
        save_state(state)

        if state["url"] is not None and SLEEP_SECONDS > 0:
            time.sleep(SLEEP_SECONDS)

    os.remove(STATE_FILE)
    print(f"Done. {state['page'] - 1} pages fetched.")


fetch_all_pages()