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
    st.altair_chart(style(chart, height), use_container_width=True, theme=None)


SHORT_NAMES = {
    "China Aerospace Science and Technology Corporation": "CASC",
    "China Aerospace Science and Industry Corporation": "CASIC",
    "Russian Federal Space Agency (ROSCOSMOS)": "Roscosmos",
    "Russian Aerospace Defence Forces": "Russian Aerospace Defence",
    "National Aeronautics and Space Administration": "NASA",
    "Indian Space Research Organization": "ISRO",
    "Japan Aerospace Exploration Agency": "JAXA",
    "Mitsubishi Heavy Industries": "MHI",
}


def short(name):
    return SHORT_NAMES.get(name, name)


def pct(x, digits=1):
    return "n/a" if x is None or x != x else f"{x * 100:.{digits}f}%"


def pts(x):
    return "n/a" if x is None or x != x else f"{x * 100:+.1f} pts"
