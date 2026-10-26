"""Market Overview: cadence, market share and the active fleet.

Neutral by default: no provider is highlighted until one is picked as the
focus, and the focus is always shown even when it is small.
"""
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

p1, p2 = st.columns([1, 1])
with p1:
    focus = ui.focus_picker()
with p2:
    year = st.selectbox("Year", years, index=years.index(full_years[0]),
                        format_func=lambda y: f"{y} (to date)" if y in partial_years else str(y))

this_year = share[share["launch_year"] == year].sort_values("attempts", ascending=False)
last_year = share[share["launch_year"] == year - 1]

attempts = int(this_year["attempts"].sum())
successes = int(this_year["successes"].sum())
prev_attempts = int(last_year["attempts"].sum())
leader = this_year.iloc[0]

# ---- key figures -----------------------------------------------------------
market_rate = successes / attempts
c1, c2, c3, c4 = st.columns(4)

if focus:
    # the provider's own numbers lead; the whole market is the context line
    mine = this_year[this_year["provider_name"] == focus]
    mine_prev = last_year[last_year["provider_name"] == focus]
    n = int(mine["attempts"].sum())
    ok = int(mine["successes"].sum())
    n_prev = int(mine_prev["attempts"].sum())
    rank = (int(this_year["attempts"].rank(ascending=False, method="min")[mine.index[0]])
            if len(mine) else None)

    c1.metric(f"{focus} orbital attempts", f"{n:,}",
              delta=f"{n - n_prev:+,} vs {year - 1}" if (n or n_prev) else None,
              delta_color="off" if year in partial_years else "normal")
    c1.caption(f"All providers: {attempts:,}")
    c2.metric(f"{focus} success rate", ui.pct(ok / n) if n else "n/a",
              help=f"{ok} of {n} attempts fully successful. Partial failures do not count.")
    c2.caption(f"All providers: {ui.pct(market_rate)}")
    c3.metric(f"{focus} share", ui.pct(n / attempts), help="Share of the year's orbital attempts.")
    c3.caption(f"of {attempts:,} attempts by all providers")
    c4.metric(f"{focus} rank", f"#{rank}" if rank else "none")
    c4.caption(f"of {len(this_year)} providers that launched" if rank
               else f"no orbital attempts in {year}")
else:
    top_two = this_year.head(2)["share_of_attempts"].sum()
    c1.metric("Orbital attempts", f"{attempts:,}",
              delta=f"{attempts - prev_attempts:+,} vs {year - 1}" if prev_attempts else None,
              delta_color="off" if year in partial_years else "normal")
    c1.caption("All providers")
    c2.metric("Success rate", ui.pct(market_rate), help="Full successes divided by attempts. "
              "Partial failures do not count as successes.")
    c2.caption("All providers")
    c3.metric("Largest provider", leader["provider_name"],
              help=f"{ui.pct(leader['share_of_attempts'])} of the year's attempts.")
    c3.caption(f"{ui.pct(leader['share_of_attempts'])} of attempts")
    c4.metric("Providers that launched", f"{len(this_year)}",
              help=f"The two largest account for {ui.pct(top_two)} of attempts.")

if year in partial_years:
    st.caption(f"{year} is a partial year, through {ui.data_as_of()}.")

# ---- cadence by provider ---------------------------------------------------
left, right = st.columns([3, 2], gap="large")

with left:
    st.subheader("Orbital attempts per year, all providers" if focus else "Orbital attempts per year")
    start, end = st.slider("Years", int(share["launch_year"].min()), int(share["launch_year"].max()),
                           (2000, int(share["launch_year"].max())), label_visibility="collapsed")
    window = share[share["launch_year"].between(start, end)]
    x = alt.X("launch_year:O", title=None, axis=alt.Axis(labelAngle=0, labelOverlap=True))

    if focus:
        # two groups only: the focus provider and everyone else, so the bar
        # height is clearly the whole market and the amber part is theirs
        others = f"All other providers"
        window = window.assign(provider=window["provider_name"].where(
            window["provider_name"] == focus, others))
        order = [focus, others]
        palette = [ui.AMBER, "#3A4656"]
    else:
        # the busiest providers in the window get their own color
        top = (window.groupby("provider_name")["attempts"].sum()
               .sort_values(ascending=False).head(5).index.tolist())
        window = window.assign(provider=window["provider_name"].where(
            window["provider_name"].isin(top), "Everyone else"))
        order = top + ["Everyone else"]
        palette = ui.NEUTRAL[:len(top)] + [ui.GRID]

    by_year = (window.groupby(["launch_year", "provider", "is_partial_year"], as_index=False)
               ["attempts"].sum())
    by_year["provider_rank"] = by_year["provider"].map(order.index)
    by_year["alpha"] = by_year["is_partial_year"].map({True: 0.4, False: 1.0})
    by_year["year_total"] = by_year.groupby("launch_year")["attempts"].transform("sum")

    chart = alt.Chart(by_year).mark_bar().encode(
        x=x,
        y=alt.Y("sum(attempts):Q", title="Attempts"),
        color=alt.Color("provider:N", sort=order, scale=alt.Scale(domain=order, range=palette)),
        order=alt.Order("provider_rank:Q"),
        opacity=alt.Opacity("alpha:Q", scale=None, legend=None),
        tooltip=[alt.Tooltip("launch_year:O", title="Year"), alt.Tooltip("provider:N", title="Provider"),
                 alt.Tooltip("attempts:Q", title="Attempts"),
                 alt.Tooltip("year_total:Q", title="All providers")],
    )
    ui.show(chart, 300 if focus else 340)

    if focus:
        # the provider on its own scale, so a small provider is still readable
        own = (window[window["provider"] == focus]
               .groupby(["launch_year", "is_partial_year"], as_index=False)[["attempts", "successes"]].sum())
        years_df = pd.DataFrame({"launch_year": range(start, end + 1)})
        own = years_df.merge(own, on="launch_year", how="left").fillna(
            {"attempts": 0, "successes": 0, "is_partial_year": False})
        own["alpha"] = own["is_partial_year"].map({True: 0.4, False: 1.0})
        st.markdown(f"**{focus} only**")
        own_chart = alt.Chart(own).mark_bar(color=ui.AMBER).encode(
            x=x,
            y=alt.Y("attempts:Q", title="Attempts", axis=alt.Axis(tickMinStep=1)),
            opacity=alt.Opacity("alpha:Q", scale=None, legend=None),
            tooltip=[alt.Tooltip("launch_year:O", title="Year"),
                     alt.Tooltip("attempts:Q", title=f"{focus} attempts"),
                     alt.Tooltip("successes:Q", title="Successes")])
        labels = alt.Chart(own[own["attempts"] > 0]).mark_text(dy=-7, fontSize=11, color=ui.AMBER) \
            .encode(x=x, y="attempts:Q", text="attempts:Q")
        ui.show(own_chart + labels, 150)

    if end in partial_years:
        st.caption(f"Faded bar: {end} so far.")

with right:
    st.subheader(f"Share of attempts, {year}")
    ranked = this_year.assign(
        rank=this_year["attempts"].rank(ascending=False, method="min").astype(int))
    ranked["display"] = "#" + ranked["rank"].astype(str) + "  " + ranked["provider_name"]

    # the top eight always stay; a focus provider outside them is added below
    # with its real position, and everyone else is grouped at the bottom
    shown = ranked.head(8)
    if focus and focus not in shown["provider_name"].values:
        shown = pd.concat([shown, ranked[ranked["provider_name"] == focus]])
    rest = ranked[~ranked["provider_name"].isin(shown["provider_name"])]
    top_share = shown.copy()
    if len(rest):
        top_share = pd.concat([top_share, pd.DataFrame([{
            "display": f"{len(rest)} others", "provider_name": "others",
            "share_of_attempts": rest["share_of_attempts"].sum(),
            "attempts": rest["attempts"].sum()}])])
    top_share["label"] = top_share["share_of_attempts"].map(lambda v: f"{v * 100:.1f}%")
    top_share["is_focus"] = top_share["provider_name"] == focus

    base = alt.Chart(top_share).encode(
        y=alt.Y("display:N", sort=None, title=None, axis=alt.Axis(labelLimit=240)),
        x=alt.X("share_of_attempts:Q", title=None, axis=None,
                scale=alt.Scale(domain=[0, max(0.6, top_share["share_of_attempts"].max() * 1.15)])),
    )
    bars = base.mark_bar(cornerRadiusEnd=3, height=18).encode(
        color=alt.condition("datum.is_focus", alt.value(ui.AMBER), alt.value(ui.BLUE)),
        tooltip=[alt.Tooltip("display:N", title="Provider"),
                 alt.Tooltip("attempts:Q", title="Attempts"),
                 alt.Tooltip("share_of_attempts:Q", title="Share", format=".1%")])
    labels = base.mark_text(align="left", dx=6, fontSize=12).encode(
        text="label:N",
        color=alt.condition("datum.is_focus", alt.value(ui.AMBER), alt.value(ui.LIGHT)))
    ui.show(bars + labels, 340 + 30 * (len(top_share) - 9))

    if focus and focus not in ranked["provider_name"].values:
        st.caption(f"{focus} had no orbital attempts in {year}.")
    st.caption("Orbital attempts only: suborbital flights, such as New Shepard, are not counted.")

    with st.expander(f"All {len(ranked)} providers in {year}"):
        table = ranked.assign(share=ranked["share_of_attempts"] * 100)[
            ["rank", "provider_name", "attempts", "successes", "share"]]
        styled = table.style.apply(
            lambda row: [f"color: {ui.AMBER}; font-weight: 600" if row["provider_name"] == focus
                         else "" for _ in row], axis=1)
        st.dataframe(
            styled, hide_index=True, width="stretch",
            column_config={
                "rank": st.column_config.NumberColumn("#"),
                "provider_name": st.column_config.TextColumn("Provider"),
                "attempts": st.column_config.NumberColumn("Attempts"),
                "successes": st.column_config.NumberColumn("Successes"),
                "share": st.column_config.NumberColumn("Share", format="%.1f%%"),
            },
        )

# ---- the active fleet ------------------------------------------------------
st.subheader("Active vehicles")
st.caption("Flew in the two years before the latest launch in the data. "
           "vs expected: reliability gap, in points, to a typical vehicle of the same era "
           "at the same stage of life.")

f1, f2, f3 = st.columns([1.2, 2, 1.2])
lens_label = f1.segmented_control("Count flights by", ["Family", "Configuration"], default="Family",
                                  help="Family groups every version of a vehicle (all Falcon 9 "
                                       "blocks together). Configuration treats each version "
                                       "separately.")
lens = (lens_label or "Family").lower()
min_flights = f2.slider("Minimum flights", 1, 50, 3)
only_focus = f3.toggle(f"Only {focus} vehicles", value=True,
                       help="Off: list every vehicle, with these highlighted.") if focus else False

fleet = reliability[(reliability["lens"] == lens)
                    & reliability["is_active"]
                    & (reliability["flights"] >= min_flights)].copy()
fleet["provider"] = fleet["unit_key"].map(lambda k: ui.provider_of(lens, k))
if only_focus:
    fleet = fleet[fleet["provider"] == focus]
fleet = fleet.sort_values("flights", ascending=False)

if fleet.empty:
    st.info("No active vehicles match these filters.")
else:
    shown_fleet = fleet.assign(
        reliability=fleet["reliability"] * 100,
        reliability_lower_95=fleet["reliability_lower_95"] * 100,
        reliability_vs_expected=fleet["reliability_vs_expected"] * 100,
    )[["unit_name", "provider", "era", "flights", "reliability", "reliability_lower_95",
       "reliability_vs_expected", "latest_flight_at"]]
    if focus and not only_focus:
        # everyone listed, the focus provider's vehicles highlighted
        shown_fleet = shown_fleet.style.apply(
            lambda row: [f"color: {ui.AMBER}; font-weight: 600" if row["provider"] == focus
                         else "" for _ in row], axis=1)
    st.dataframe(
        shown_fleet,
        hide_index=True,
        width="stretch",
        column_config={
            "unit_name": st.column_config.TextColumn("Vehicle"),
            "provider": st.column_config.TextColumn("Provider"),
            "era": st.column_config.TextColumn("First-flight era"),
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
