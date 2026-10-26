"""Scenario Simulator: when does a vehicle become proven, and what moves it?

Method: Monte Carlo. Each future flight succeeds with the probability a
typical vehicle of the same era has at that point in its life (the debut
curve), adjusted by the chosen performance scenario. Thousands of possible
futures are simulated; for each, the flight at which the 95% Wilson lower
bound first reaches the target is recorded. The result is a range, not a
single date, because a few early failures change the answer a lot.
"""
from datetime import timedelta

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

import data
import ui

RUNS = 4000
HORIZON = 300          # future flights simulated
Z = 1.96
MIN_BAND_FLIGHTS = 20  # thinner era bands fall back to the all-era rate
SCENARIOS = {
    "Half the typical failure rate": 0.5,
    "Typical for its era": 1.0,
    "1.5x the typical failure rate": 1.5,
    "Twice the typical failure rate": 2.0,
}

ui.header("Scenario Simulator",
          "If a vehicle flies like a typical vehicle of its era from here on, when does it "
          "become proven, and how much do cadence and performance change the answer?")

reliability = data.table("mart_vehicle_reliability")
maturation = data.table("mart_maturation")
debut = data.table("mart_debut_curve")

LENS = "family"
fleet = reliability[(reliability["lens"] == LENS) & reliability["is_active"]].copy()
fleet["provider"] = fleet["unit_key"].map(lambda k: ui.provider_of(LENS, k))
fleet = fleet.sort_values("unit_name")
names = fleet["unit_name"].tolist()
provider_by_name = dict(zip(fleet["unit_name"], fleet["provider"]))

focus = ui.focus_picker()

# Default vehicle: the newest active vehicle with at least two flights,
# from the focus provider if one is picked, otherwise from anyone.
candidates = fleet[fleet["flights"] >= 2]
if focus and (candidates["provider"] == focus).any():
    candidates = candidates[candidates["provider"] == focus]
newest = candidates.sort_values("first_flight_at").iloc[-1]["unit_name"]

inputs, results = st.columns([1, 2.4], gap="large")

with inputs:
    vehicle = st.selectbox("Vehicle", names, index=names.index(newest),
                           format_func=lambda n: f"{n} ({provider_by_name.get(n) or 'unknown'})",
                           help="Active vehicles, counted by family.")
    v = fleet[fleet["unit_name"] == vehicle].iloc[0]
    history = maturation[(maturation["lens"] == LENS) & (maturation["unit_name"] == vehicle)] \
        .sort_values("flight_number")

    last_year = history[history["launched_at"] >= history["launched_at"].max() - timedelta(days=365)]
    suggested = int(min(60, max(2, len(last_year))))
    cadence = st.slider("Flights per year", 1, 60, suggested,
                        help=f"Defaults to the last 12 months: {len(last_year)} flights.")
    scenario = st.select_slider("Performance from here on", list(SCENARIOS),
                                value="Typical for its era")
    target = st.segmented_control("Proven means a lower bound of", ["80%", "90%"], default="80%")
    target = 0.8 if (target or "80%") == "80%" else 0.9

    st.markdown(
        f"**Record so far:** {int(v['successes'])} of {int(v['flights'])} "
        f"({ui.pct(v['reliability'])}), lower bound {ui.pct(v['reliability_lower_95'])}. "
        f"First flew in the {v['era']} era."
    )

# ---- per-flight success probabilities from the debut curve -------------------
def band_start(n):
    if n <= 5:
        return n
    for start, end in [(6, 10), (11, 20), (21, 50), (51, 100)]:
        if n <= end:
            return start
    return 101


curve = debut[debut["lens"] == LENS].set_index(["era", "flight_band_start"])
future = np.arange(int(v["flights"]) + 1, int(v["flights"]) + HORIZON + 1)


def typical_rate(n):
    key = (v["era"], band_start(n))
    if key in curve.index and curve.loc[key, "attempts"] >= MIN_BAND_FLIGHTS:
        return curve.loc[key, "success_rate"]
    return curve.loc[("all", band_start(n)), "success_rate"]


p_typical = np.array([typical_rate(n) for n in future])
p = 1 - np.clip(SCENARIOS[scenario] * (1 - p_typical), 0, 1)


@st.cache_data(show_spinner=False)
def simulate(successes, flights, probs, seed=7):
    rng = np.random.default_rng(seed)
    wins = rng.random((RUNS, len(probs))) < probs
    cum_s = successes + np.cumsum(wins, axis=1)
    n = flights + np.arange(1, len(probs) + 1)
    rate = cum_s / n
    lower = (rate + Z**2 / (2 * n) - Z * np.sqrt(rate * (1 - rate) / n + Z**2 / (4 * n**2))) \
        / (1 + Z**2 / n)
    return wins, lower


wins, lower = simulate(int(v["successes"]), int(v["flights"]), p)

reached = lower >= target
hit = np.where(reached.any(axis=1), reached.argmax(axis=1) + 1, np.nan)  # flights from now
share_reached = np.mean(~np.isnan(hit))
clean_five = np.mean(wins[:, :5].all(axis=1))
already = v["reliability_lower_95"] >= target
last_flight = history["launched_at"].max()


def when(k):
    return (last_flight + timedelta(days=365.25 * k / cadence)).strftime("%b %Y")


with results:
    m1, m2, m3 = st.columns(3)
    m1.metric("Next five flights all succeed", ui.pct(clean_five),
              help=f"Flights {int(v['flights']) + 1} to {int(v['flights']) + 5}.")
    if already:
        m2.metric(f"Proven at {target:.0%}", "Already")
        m3.metric("Reached at flight", f"{int(v['flights_to_lb_80' if target == 0.8 else 'flights_to_lb_90'])}")
    elif share_reached < 0.5:
        m2.metric(f"Proven at {target:.0%}", "Not within 300 flights",
                  help=f"Reached in {ui.pct(share_reached)} of simulated futures.")
        m3.metric("Simulated futures reaching it", ui.pct(share_reached))
    else:
        mid = np.nanmedian(hit)
        lo, hi = np.nanpercentile(hit, [10, 90])
        m2.metric(f"Proven at {target:.0%}", when(mid),
                  help="Median of the simulated futures.")
        m3.metric("At flight", f"{int(v['flights'] + mid)}",
                  help=f"80% of simulated futures land between flight {int(v['flights'] + lo)} "
                       f"({when(lo)}) and {int(v['flights'] + hi)} ({when(hi)}).")
        st.caption(f"80% of simulated futures reach it between {when(lo)} and {when(hi)}, "
                   f"at {cadence} flights a year.")

    # fan chart: actual lower bound so far, then the simulated range
    shown = 120
    fan = pd.DataFrame({
        "flight_number": future[:shown],
        "p10": np.percentile(lower[:, :shown], 10, axis=0),
        "p50": np.percentile(lower[:, :shown], 50, axis=0),
        "p90": np.percentile(lower[:, :shown], 90, axis=0),
    })
    past = history[["flight_number", "reliability_lower_95"]]
    x = alt.X("flight_number:Q", title="Flight number")
    band = alt.Chart(fan).mark_area(color=ui.AMBER, opacity=0.18).encode(
        x=x, y=alt.Y("p10:Q", title="Lower bound", axis=alt.Axis(format="%"),
                     scale=alt.Scale(domain=[0, 1])), y2="p90:Q")
    median = alt.Chart(fan).mark_line(color=ui.AMBER, strokeDash=[6, 4], strokeWidth=2).encode(
        x=x, y="p50:Q",
        tooltip=[alt.Tooltip("flight_number:Q", title="Flight"),
                 alt.Tooltip("p50:Q", title="Median", format=".1%"),
                 alt.Tooltip("p10:Q", title="10th pct", format=".1%"),
                 alt.Tooltip("p90:Q", title="90th pct", format=".1%")])
    actual = alt.Chart(past).mark_line(color=ui.LIGHT, strokeWidth=2.5, interpolate="step-after") \
        .encode(x=x, y="reliability_lower_95:Q")
    goal = alt.Chart(pd.DataFrame({"y": [target]})).mark_rule(
        strokeDash=[5, 4], color=ui.MUTED).encode(y="y:Q")
    st.subheader("Lower bound: so far, then simulated")
    ui.show(goal + band + actual + median, 380)
    st.caption("Solid: the actual record. Dashed: the median simulated future. "
               "Shaded: 80% of simulated futures.")

with st.expander("How the simulation works"):
    st.markdown(
        f"""
Each future flight succeeds with the probability that vehicles from the **{v['era']}** era had
at the same point in their life (the success rate by flight number on the Maturation Race page).
Where fewer than {MIN_BAND_FLIGHTS} flights back that rate, the all-era rate is used. The
performance setting scales the failure probability up or down.

The simulator runs {RUNS:,} possible futures of {HORIZON} flights each. In each one, it tracks
the 95% lower bound on reliability after every flight, and notes the first flight where it
reaches the target. Dates assume the chosen cadence, counted from the latest flight in the data.

This is a benchmark path, not a forecast: it says what a typical vehicle in this position would
do, and the performance setting is the way to ask "what if it is better or worse than typical?"
"""
    )

ui.footer()
