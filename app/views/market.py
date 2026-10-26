"""Market Overview: cadence, market share and the active fleet."""
import altair as alt
import pandas as pd
import streamlit as st

import data
import ui

ui.header("Market Overview",
          "Orbital launch attempts with a known outcome, every provider, 1957 to today.")

share = data.table("mart_market_share_yearly")
share = share.assign(provider_name=share["provider_name"].map(ui.short))
reliability = data.table("mart_vehicle_reliability")

years = sorted(share["launch_year"].unique(), reverse=True)
full_years = sorted(share.loc[~share["is_partial_year"], "launch_year"].unique(), reverse=True)
partial_years = set(share.loc[share["is_partial_year"], "launch_year"].unique())

year = st.selectbox("Year", years, index=years.index(full_years[0]),
                    format_func=lambda y: f"{y} (to date)" if y in partial_years else str(y))

this_year = share[share["launch_year"] == year].sort_values("attempts", ascending=False)
last_year = share[share["launch_year"] == year - 1]

attempts = int(this_year["attempts"].sum())
successes = int(this_year["successes"].sum())
prev_attempts = int(last_year["attempts"].sum())
leader = this_year.iloc[0]

# ---- key figures -----------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Orbital attempts", f"{attempts:,}",
          delta=f"{attempts - prev_attempts:+,} vs {year - 1}" if prev_attempts else None,
          delta_color="off" if year in partial_years else "normal")
c2.metric("Success rate", ui.pct(successes / attempts), help="Full successes divided by attempts. "
          "Partial failures do not count as successes.")
c3.metric(f"{leader['provider_name']} share", ui.pct(leader["share_of_attempts"]),
          help="Share of the year's orbital attempts.")
c4.metric("Providers that launched", f"{len(this_year)}")
if year in partial_years:
    st.caption(f"{year} is a partial year, through {ui.data_as_of()}.")

# ---- cadence by provider ---------------------------------------------------
left, right = st.columns([3, 2], gap="large")

with left:
    st.subheader("Orbital attempts per year")
    start, end = st.slider("Years", int(share["launch_year"].min()), int(share["launch_year"].max()),
                           (2000, int(share["launch_year"].max())), label_visibility="collapsed")
    window = share[share["launch_year"].between(start, end)]

    # the five busiest providers in the window get their own color
    top = (window.groupby("provider_name")["attempts"].sum()
           .sort_values(ascending=False).head(5).index.tolist())
    window = window.assign(provider=window["provider_name"].where(
        window["provider_name"].isin(top), "Everyone else"))
    by_year = (window.groupby(["launch_year", "provider", "is_partial_year"], as_index=False)
               ["attempts"].sum())
    order = top + ["Everyone else"]
    by_year["provider_rank"] = by_year["provider"].map(order.index)
    by_year["alpha"] = by_year["is_partial_year"].map({True: 0.4, False: 1.0})

    chart = alt.Chart(by_year).mark_bar().encode(
        x=alt.X("launch_year:O", title=None, axis=alt.Axis(labelAngle=0, labelOverlap=True)),
        y=alt.Y("sum(attempts):Q", title="Attempts"),
        color=alt.Color("provider:N", sort=order,
                        scale=alt.Scale(domain=order, range=ui.SERIES[:len(top)] + [ui.GRID])),
        order=alt.Order("provider_rank:Q"),
        opacity=alt.Opacity("alpha:Q", scale=None, legend=None),
        tooltip=[alt.Tooltip("launch_year:O", title="Year"), alt.Tooltip("provider:N", title="Provider"),
                 alt.Tooltip("attempts:Q", title="Attempts")],
    )
    ui.show(chart, 340)
    if end in partial_years:
        st.caption(f"Faded bar: {end} so far.")

with right:
    st.subheader(f"Share of attempts, {year}")
    top_share = this_year.head(8).copy()
    rest = this_year.iloc[8:]
    if len(rest):
        top_share = pd.concat([top_share, pd.DataFrame([{
            "provider_name": f"{len(rest)} others", "share_of_attempts": rest["share_of_attempts"].sum(),
            "attempts": rest["attempts"].sum()}])])
    top_share["label"] = top_share["share_of_attempts"].map(lambda v: f"{v * 100:.1f}%")
    top_share["is_leader"] = top_share["provider_name"] == leader["provider_name"]

    base = alt.Chart(top_share).encode(
        y=alt.Y("provider_name:N", sort=None, title=None, axis=alt.Axis(labelLimit=220)),
        x=alt.X("share_of_attempts:Q", title=None, axis=None,
                scale=alt.Scale(domain=[0, max(0.6, top_share["share_of_attempts"].max() * 1.15)])),
    )
    bars = base.mark_bar(cornerRadiusEnd=3, height=18).encode(
        color=alt.condition("datum.is_leader", alt.value(ui.AMBER), alt.value(ui.BLUE)),
        tooltip=[alt.Tooltip("provider_name:N", title="Provider"),
                 alt.Tooltip("attempts:Q", title="Attempts"),
                 alt.Tooltip("share_of_attempts:Q", title="Share", format=".1%")])
    labels = base.mark_text(align="left", dx=6, fontSize=12).encode(text="label:N")
    ui.show(bars + labels, 340)

# ---- the active fleet ------------------------------------------------------
st.subheader("Active vehicles")
st.caption("Flew in the two years before the latest launch in the data. "
           "vs expected: reliability gap, in points, to a typical vehicle of the same era "
           "at the same stage of life.")

f1, f2 = st.columns([1, 3])
lens = f1.segmented_control("Count flights by", ["Family", "Configuration"], default="Family",
                            help="Family groups every version of a vehicle (all Falcon 9 blocks "
                                 "together). Configuration treats each version separately.")
min_flights = f2.slider("Minimum flights", 1, 50, 3)

fleet = reliability[(reliability["lens"] == (lens or "Family").lower())
                    & reliability["is_active"]
                    & (reliability["flights"] >= min_flights)].sort_values("flights", ascending=False)

st.dataframe(
    fleet.assign(
        reliability=fleet["reliability"] * 100,
        reliability_lower_95=fleet["reliability_lower_95"] * 100,
        reliability_vs_expected=fleet["reliability_vs_expected"] * 100,
    )[["unit_name", "era", "flights", "reliability", "reliability_lower_95",
       "reliability_vs_expected", "latest_flight_at"]],
    hide_index=True,
    width="stretch",
    column_config={
        "unit_name": st.column_config.TextColumn("Vehicle"),
        "era": st.column_config.TextColumn("First flew"),
        "flights": st.column_config.NumberColumn("Flights"),
        "reliability": st.column_config.NumberColumn("Reliability", format="%.1f%%"),
        "reliability_lower_95": st.column_config.NumberColumn(
            "95% lower bound", format="%.1f%%",
            help="With this much evidence, reliability is at least this high (95% confidence)."),
        "reliability_vs_expected": st.column_config.NumberColumn("vs expected", format="%+.1f"),
        "latest_flight_at": st.column_config.DateColumn("Latest flight", format="D MMM YYYY"),
    },
)

ui.footer()
