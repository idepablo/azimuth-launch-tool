"""AZIMUTH: launch-market intelligence.

Entry point. Run locally from the repository root with:
    streamlit run app/streamlit_app.py
"""
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="AZIMUTH",
    page_icon=":material/explore:",
    layout="wide",
)

pages = [
    st.Page("views/market.py", title="Market Overview", url_path="market", default=True),
    st.Page("views/maturation.py", title="Maturation Race", url_path="maturation"),
    st.Page("views/vehicle.py", title="Vehicles", url_path="vehicle"),
    st.Page("views/simulator.py", title="Scenario Simulator", url_path="simulator"),
    st.Page("views/methodology.py", title="Methodology", url_path="methodology"),
]

st.logo(str(Path(__file__).parent / "assets" / "logo.svg"), size="large")
nav = st.navigation(pages, position="top")
nav.run()
