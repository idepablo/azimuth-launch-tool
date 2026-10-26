"""Shared look: colors, page header, chart styling, formatting."""
from datetime import datetime

import altair as alt
import streamlit as st

import data

AMBER = "#F2A33A"   # the focus vehicle / highlight
BLUE = "#6CB6FF"    # the field
LIGHT = "#C9D1D9"
MUTED = "#9AA7B4"
GRID = "#263040"
PANEL = "#151B23"

# categorical series: distinct in lightness as well as hue
SERIES = [AMBER, BLUE, LIGHT, "#3FB68B", "#C38BFF", "#E46F6F", "#7D8B99", "#F7D774"]


def header(title, subtitle):
    st.title(title)
    st.caption(subtitle)


def data_as_of():
    m = data.manifest()
    as_of = datetime.strptime(m["data_as_of"], "%Y-%m-%d").strftime("%d %b %Y")
    return as_of


def footer():
    m = data.manifest()
    st.divider()
    st.caption(
        f"Data through {data_as_of()} · {m['tables']['fct_launches']:,} launches · "
        "Source: Launch Library 2 (The Space Devs) · Refreshed daily · "
        "[Methodology](/methodology) · "
        "[Code](https://github.com/idepablo/azimuth-launch-tool)"
    )
    exported = datetime.strptime(m["exported_at"][:10], "%Y-%m-%d").strftime("%d %b %Y")
    vehicles = data.table("dim_vehicle")
    pending = int((vehicles["vehicle_class"] == "unclassified").sum())
    status = f"Last refresh {exported}"
    if pending:
        status += (f" · {pending} new vehicle{'s' if pending != 1 else ''} awaiting "
                   "classification, not yet counted")
    st.caption(status)
    st.caption("© 2026 Ignacio de Pablo. All rights reserved. "
               "Launch data © The Space Devs, used with attribution.")


def style(chart, height=320):
    """Dark styling for every Altair chart in the app."""
    return (
        chart.properties(height=height, background="transparent")
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor=MUTED, titleColor=MUTED, gridColor=GRID,
                        domainColor=GRID, tickColor=GRID, labelFontSize=12,
                        titleFontSize=12, titleFontWeight="normal")
        .configure_legend(labelColor=LIGHT, titleColor=MUTED, labelFontSize=12,
                          orient="bottom", title=None, columns=4, labelLimit=200)
        .configure_text(color=LIGHT)
    )


def show(chart, height=320):
    st.altair_chart(style(chart, height), width="stretch", theme=None)


SHORT_NAMES = {
    "China Aerospace Science and Technology Corporation": "CASC",
    "China Aerospace Science and Industry Corporation": "CASIC",
    "Russian Federal Space Agency (ROSCOSMOS)": "Roscosmos",
    "Russian Aerospace Defence Forces": "Russian Aerospace Defence",
    "National Aeronautics and Space Administration": "NASA",
    "Indian Space Research Organization": "ISRO",
    "Japan Aerospace Exploration Agency": "JAXA",
    "Mitsubishi Heavy Industries": "MHI",
    "Khrunichev State Research and Production Space Center": "Khrunichev",
}


def short(name):
    return SHORT_NAMES.get(name, name)


WHOLE_MARKET = "Whole market"
NEUTRAL = [BLUE, LIGHT, "#3FB68B", "#C38BFF", "#E46F6F", "#7D8B99", "#F7D774"]  # no amber


@st.cache_data(ttl=3600, show_spinner=False)
def unit_providers(lens):
    """Map each vehicle (family or configuration) to the provider of its latest launch.

    Latest rather than most frequent, so Proton shows its current operator
    rather than the Soviet program that flew it for decades.
    """
    launches = data.table("fct_launches")[["vehicle_key", "provider_key", "launched_at"]]
    vehicles = data.table("dim_vehicle")[["vehicle_key", "family_name"]]
    providers = data.table("dim_provider")[["provider_key", "provider_name"]]
    df = launches.merge(vehicles, on="vehicle_key").merge(providers, on="provider_key")
    unit = "family_name" if lens == "family" else "vehicle_key"
    latest = df.sort_values("launched_at").drop_duplicates(unit, keep="last")
    return dict(zip(latest[unit].astype(str), latest["provider_name"].map(short)))


def provider_of(lens, unit_key):
    return unit_providers(lens).get(str(unit_key))


def focus_picker():
    """Shared 'Focus provider' selector. Neutral by default, kept across pages and in the URL."""
    share = data.table("mart_market_share_yearly")
    names = (share.assign(name=share["provider_name"].map(short))
                  .groupby("name")["attempts"].sum().sort_values(ascending=False).index.tolist())
    options = [WHOLE_MARKET] + sorted(names)

    current = st.session_state.get("focus_provider") or st.query_params.get("provider", WHOLE_MARKET)
    if current not in options:
        current = WHOLE_MARKET

    choice = st.selectbox(
        "Focus provider", options, index=options.index(current),
        help="Highlight one provider across every page. Whole market highlights no one.")
    st.session_state["focus_provider"] = choice
    if choice == WHOLE_MARKET:
        st.query_params.pop("provider", None)
        return None
    st.query_params["provider"] = choice
    return choice


def open_vehicle_on_click(event, names, lens):
    """Open the vehicle page for the row clicked in a table."""
    rows = event.selection.rows if event else []
    if rows:
        st.switch_page("views/vehicle.py",
                       query_params={"vehicle": names[rows[0]], "lens": lens})


def pct(x, digits=1):
    return "n/a" if x is None or x != x else f"{x * 100:.{digits}f}%"


def pts(x):
    return "n/a" if x is None or x != x else f"{x * 100:+.1f} pts"
