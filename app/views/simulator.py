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
MAX_CADENCE = 500      # flights per year
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
# a vehicle passed in the link (from its vehicle page) wins over the default
if st.query_params.get("vehicle") in names:
    newest = st.query_params["vehicle"]

inputs, results = st.columns([1, 2.4], gap="large")

with inputs:
    vehicle = st.selectbox("Vehicle", names, index=names.index(newest),
                           format_func=lambda n: f"{n} ({provider_by_name.get(n) or 'unknown'})",
                           help="Active vehicles, counted by family.")
    st.query_params["vehicle"] = vehicle
    v = fleet[fleet["unit_name"] == vehicle].iloc[0]
    history = maturation[(maturation["lens"] == LENS) & (maturation["unit_name"] == vehicle)] \
        .sort_values("flight_number")
    last_flight = history["launched_at"].max()

    last_year = history[history["launched_at"] >= last_flight - timedelta(days=365)]
    cadence = st.number_input(
        "Flights per year", min_value=1, max_value=MAX_CADENCE, value=max(1, len(last_year)),
        step=1, help=f"Defaults to this vehicle's last 12 months of flights ({len(last_year)}). "
                     f"Any value from 1 to {MAX_CADENCE}.")
    scenario = st.select_slider("Performance from here on", list(SCENARIOS),
                                value="Typical for its era")
    target_label = st.segmented_control("Proven means a lower bound of", ["80%", "90%"],
                                        default="80%") or "80%"
    target = 0.8 if target_label == "80%" else 0.9

    st.markdown(
        f"**Record so far:** {int(v['successes'])} of {int(v['flights'])} "
        f"({ui.pct(v['reliability'])}), lower bound {ui.pct(v['reliability_lower_95'])}. "
        f"First-flight era: {v['era']}."
    )

# ---- per-flight success probabilities from the debut curve -------------------
BAND_STARTS = [1, 2, 3, 4, 5, 6, 11, 21, 51, 101]


def band_index(n):
    return max(i for i, start in enumerate(BAND_STARTS) if n >= start)


curve = debut[debut["lens"] == LENS].set_index(["era", "flight_band_start"])
successes_by_band, failures_by_band = [], []
for start in BAND_STARTS:
    key = (v["era"], start)
    row = curve.loc[key] if key in curve.index and curve.loc[key, "attempts"] >= MIN_BAND_FLIGHTS \
        else curve.loc[("all", start)]
    successes_by_band.append(int(row["successes"]))
    failures_by_band.append(int(row["attempts"] - row["successes"]))

future = np.arange(int(v["flights"]) + 1, int(v["flights"]) + HORIZON + 1)
band_of_flight = np.array([band_index(n) for n in future])


@st.cache_data(show_spinner=False)
def simulate(successes, flights, band_s, band_f, bands, multiplier, seed=7):
    """Monte Carlo futures, with uncertainty in both outcomes and the benchmark.

    Each simulated future first draws its own success rate for every flight
    band from a Beta distribution fitted to the band's counts (Jeffreys prior),
    so bands backed by few flights vary more from run to run. Then each
    flight succeeds or fails at that rate, scaled by the performance setting.
    """
    rng = np.random.default_rng(seed)
    band_rates = rng.beta(np.array(band_s) + 0.5, np.array(band_f) + 0.5,
                          size=(RUNS, len(band_s)))
    probs = 1 - np.clip(multiplier * (1 - band_rates[:, bands]), 0, 1)
    wins = rng.random(probs.shape) < probs
    cum_s = successes + np.cumsum(wins, axis=1)
    n = flights + np.arange(1, probs.shape[1] + 1)
    rate = cum_s / n
    lower = (rate + Z**2 / (2 * n) - Z * np.sqrt(rate * (1 - rate) / n + Z**2 / (4 * n**2))) \
        / (1 + Z**2 / n)
    return wins, lower


wins, lower = simulate(int(v["successes"]), int(v["flights"]), successes_by_band,
                       failures_by_band, band_of_flight, SCENARIOS[scenario])

# flights from now until the lower bound first reaches the target; runs that
# never get there within the horizon count as "later than the horizon"
reached = lower >= target
hit = np.where(reached.any(axis=1), reached.argmax(axis=1) + 1, np.inf)
share_reached = np.mean(np.isfinite(hit))
clean_five = np.mean(wins[:, :5].all(axis=1))

current_lb = v["reliability_lower_95"]
first_reached = v["flights_to_lb_80" if target == 0.8 else "flights_to_lb_90"]
above_now = current_lb >= target


def flight_label(k):
    return f"after flight {int(v['flights']) + HORIZON}" if not np.isfinite(k) \
        else f"flight {int(v['flights'] + k)}"


def when(k):
    if not np.isfinite(k):
        return f"beyond {HORIZON} flights"
    return (last_flight + timedelta(days=365.25 * k / cadence)).strftime("%b %Y")


with results:
    st.caption(
        f"Projection starts from **{vehicle}'s latest flight in the data, "
        f"{last_flight.strftime('%d %b %Y')}** (flight {int(v['flights'])}). "
        f"The data runs through {ui.data_as_of()}."
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Next five flights all succeed", ui.pct(clean_five),
              help=f"Share of simulated futures in which flights {int(v['flights']) + 1} to "
                   f"{int(v['flights']) + 5} all succeed.")
    if above_now:
        m2.metric(f"Above {target_label} now", "Yes",
                  help=f"Current lower bound {ui.pct(current_lb)}. A future failure can push it "
                       "back below, which the chart below shows as a dip.")
        m3.metric(f"First reached {target_label}", f"Flight {int(first_reached)}")
        m4.metric("Still above in 50 flights",
                  ui.pct(np.mean(lower[:, min(49, HORIZON - 1)] >= target)))
    else:
        median = np.percentile(hit, 50)
        m2.metric(f"Reaches {target_label} (median)", when(median),
                  help="Median of all simulated futures, including those that do not get there "
                       f"within {HORIZON} flights.")
        m3.metric("At", flight_label(median).capitalize())
        m4.metric(f"Reach it in {HORIZON} flights", ui.pct(share_reached),
                  help="Futures that never reach the target count as later than every date "
                       "shown; if fewer than half reach it, the median is beyond the horizon.")
        lo, hi = np.percentile(hit, [10, 90])
        note = (f"80% of simulated futures reach {target_label} between {when(lo)} "
                f"({flight_label(lo)}) and {when(hi)} ({flight_label(hi)}), "
                f"at {cadence} flight{'s' if cadence != 1 else ''} a year.")
        if pd.notna(first_reached):
            note += (f" {vehicle} first reached {target_label} at flight {int(first_reached)} and "
                     f"has since dropped below it.")
        st.caption(note)

    # fan chart: actual lower bound so far, then the simulated range. The
    # window always covers the reported 80% range (plus a margin), or all
    # simulated flights on request.
    p90_hit = np.percentile(hit, 90)
    needed = HORIZON if not np.isfinite(p90_hit) else int(p90_hit) + 15
    show_all = st.toggle(f"Show all {HORIZON} future flights", value=False)
    shown = HORIZON if show_all else int(min(HORIZON, max(120, needed)))
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
    median_line = alt.Chart(fan).mark_line(color=ui.AMBER, strokeDash=[6, 4], strokeWidth=2).encode(
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
    ui.show(goal + band + actual + median_line, 380)
    st.caption("Solid: the actual record. Dashed: the median simulated future. Shaded: the "
               "middle 80% of simulated futures, covering both chance in outcomes and "
               "uncertainty in the benchmark rates.")

with st.expander("How the simulation works"):
    st.markdown(
        f"""
**Starting point.** The projection starts from the vehicle's own latest flight in the data, not
from today. Dates are that flight plus the number of future flights divided by the cadence.

**Success rates.** Each future flight succeeds with the probability that vehicles from the
**{v['era']}** era had at the same point in their life (the success rate by flight number on the
Maturation Race page). Where fewer than {MIN_BAND_FLIGHTS} flights back an era's rate, the all-era
rate is used. The performance setting scales the failure probability up or down.

**Two kinds of uncertainty.** Each of the {RUNS:,} simulated futures first draws its own version of
those success rates, from a Beta distribution fitted to the counts behind each rate, so rates backed
by few flights vary more. Then each flight succeeds or fails at random at that rate. The shaded band
and the date range include both.

**Reaching the target.** In each future the simulator tracks the 95% lower bound after every flight
and records the first flight where it reaches the target, up to {HORIZON} flights ahead. Futures that
never get there count as later than every date shown, so they push the median and the range later
rather than being dropped. "First reached" and "above now" are different: a failure after reaching
the target can push the lower bound back below it.

**What it is not.** This is a benchmark path, not a forecast: it says what a typical vehicle in this
position would do. It has been backtested against how real vehicles fared after five past
dates; the results are on the Methodology page.
"""
    )

ui.footer()
