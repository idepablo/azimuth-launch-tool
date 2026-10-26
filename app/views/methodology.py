"""Methodology: definitions, decisions and limits, in plain terms."""
import altair as alt
import pandas as pd
import streamlit as st

import data
import ui

ui.header("Methodology", "What the numbers mean, where they come from, and where they stop.")

m = data.manifest()
st.markdown(
    f"""
**Data.** Every launch in [Launch Library 2](https://thespacedevs.com/llapi) by The Space Devs,
1957 to {ui.data_as_of()}: {m['tables']['fct_launches']:,} launches. A pipeline on Databricks
loads changes every day, models them with dbt, and runs its tests before anything reaches this
app. The app reads a snapshot of the final tables, exported after each successful run.
Full detail is in the [scope document](https://github.com/idepablo/azimuth-launch-tool/blob/main/docs/scope.md).

### What counts

- **Orbital launches only.** Each vehicle is classified by hand (a reviewed list of 486
  vehicles), and a launch whose own record says suborbital is moved out. Launches from the Moon
  (Apollo ascent stages, Luna and Chang'e sample returns) are excluded.
- **Outcomes, not schedules.** Only launches with a known result count: success, failure or
  partial failure. Partial failures are not counted as successes.
- **Failures before launch.** Apollo 1 is excluded: it was a fire in the spacecraft during a
  ground test, and the rocket never launched. Amos-6 (Falcon 9, 2016) is kept: the rocket itself
  exploded during a test before launch and destroyed the customer's satellite. Keeping it moves
  Falcon 9's family reliability from 99.6% to 99.4%. Most launch logs leave it out.

### Configuration or family

A **configuration** is one version of a vehicle (Falcon 9 Block 5). A **family** groups the
versions (Falcon 9, from v1.0 in 2010 onward). Block 5 has an almost perfect record, but it
came after 57 flights of earlier versions, failures included. Counting by family is the fair
comparison for a new vehicle, so it is the default.

### Reliability

- **Success rate:** successes divided by flights.
- **Lower bound:** the 95% Wilson interval's lower end. A vehicle that is 3 for 3 has a 100%
  success rate, but the evidence only supports "at least 44%". The bound rises as flights
  accumulate.
- **First reached 80% or 90%:** the flight at which the lower bound first reached that level.
  A perfect record needs 16 flights to reach 80% and 35 to reach 90%.
- **Above 80% or 90% now:** whether the current lower bound is at or above that level. The two
  can differ: a failure after reaching a level can push the lower bound back below it, so
  "first reached" is a milestone, not a permanent status.

### The three models

- **Success rate by flight number.** Across every vehicle that reached a given flight, how often
  did that flight succeed? Split by the era in which the vehicle first flew.
- **Clean opening run.** The share of vehicles that get through their first n flights without a
  failure, estimated with Kaplan-Meier so vehicles that have not failed *yet* are handled
  correctly. Checked against the Python lifelines library.
- **vs expected.** Each vehicle against a typical vehicle of its era over the same flights. The
  vehicle's own flights are left out of the comparison.

### Limits

- **Survivors.** Vehicles that fail often get cancelled, so late flights are made of survivors and
  long-lived vehicles tend to look better than the benchmark. Compare vehicles with similar flight
  counts.
- **Source gaps.** About 7% of launches have no published orbit, concentrated in Chinese, Russian
  and military missions. Market share is counted by vehicle, so it does not depend on orbit data.
- **Vehicle details** (full names, families) come from a mirror of the source that can lag behind
  by weeks. A brand-new vehicle shows under its short name until the mirror catches up.
- **A tested, not adopted model.** An empirical Bayes model (one shared starting estimate for all
  vehicles) was tested and left out: vehicles differ too much for it to add information.
"""
)

# ---- backtest -----------------------------------------------------------------
bt = data.backtest()
st.markdown("### How well does the simulator predict?")
if bt is None:
    st.caption("Backtest results are published with the next data refresh.")
else:
    pf, nf, cr = bt["per_flight"], bt["next_five"], bt["crossing_80"]
    cutoffs = ", ".join(c[:4] for c in bt["cutoffs"])
    improvement = 1 - pf["brier"]["model"] / pf["brier"]["market_rate"]
    cal_rows = pf["calibration"]
    worst_gap = max(abs(r["observed"] - r["predicted"]) for r in cal_rows)
    better = sum(r["observed"] > r["predicted"] for r in cal_rows)
    # a blend only "helps" if it beats the model by at least 1%
    blend_worse = min(pf["brier_blend_with_own_record"].values()) >= pf["brier"]["model"] * 0.99
    pessimistic = nf["mean_predicted"] < nf["observed"]
    cover = cr["coverage"] or 0
    st.markdown(
        f"""
The simulator was tested against history. The data was frozen on 1 January of {cutoffs}; at each
date the success rates were rebuilt from earlier flights only, the model was run for every vehicle
active at the time, and its predictions were compared with what those vehicles actually did next.
It reruns automatically on every data refresh.

- **Per-flight odds.** Across {pf['flights_scored']:,} later flights by {pf['vehicles']} vehicles,
  the model predicted an average success rate of {ui.pct(pf['mean_predicted'])}; the real rate was
  {ui.pct(pf['actual_success_rate'])}. In every probability range the observed rate is within
  {worst_gap * 100:.1f} points of the prediction, and better than predicted in {better} of
  {len(cal_rows)} ranges.
- **Compared with simpler rules.** Measured by Brier score (lower is better), the model
  scores {pf['brier']['model']:.4f}, against {pf['brier']['own_record']:.4f} for each vehicle's own
  record so far and {pf['brier']['market_rate']:.4f} for the market's overall success rate, a
  {improvement:.0%} improvement on the latter.{" Blending in the vehicle's own record did not improve predictions at any weight tried: where a vehicle is in its life says more about its next flights than its record does." if blend_worse else " Blending in some of the vehicle's own record helped at some weights, a possible improvement for a future version."}
- **"Next five flights all succeed"{" runs a little pessimistic" if pessimistic else " runs a little optimistic"}.** Predicted on average
  {ui.pct(nf['mean_predicted'])} for {nf['vehicles']} vehicles; {ui.pct(nf['observed'])} actually
  did it. Part of the gap is selection: only vehicles that went on to fly five more times can be
  scored, and those tend to be the healthier ones.
- **The range for reaching 80% holds up, on a small sample.** For {cr['decided']} vehicles where the
  outcome is known, the real crossing fell inside the simulator's 80% range {cr['inside']} times
  ({ui.pct(cr['coverage'], 0)}): {cr['earlier']} earlier, {cr['later']} later. Another
  {cr['undetermined']} have not crossed yet and are still within their range, so they cannot be
  scored.{" A range that is right more often than 80% is, if anything, slightly too wide." if cover > 0.8 else (" A range that is right less often than 80% is slightly too narrow." if cover < 0.8 else "")}

Dates are not tested, because they depend on the cadence entered. Full results:
[analysis/backtest.py](https://github.com/idepablo/azimuth-launch-tool/blob/main/analysis/backtest.py).
"""
    )
    cal = pd.DataFrame(pf["calibration"])
    axis_scale = alt.Scale(domain=[0.6, 1.0])
    diagonal = alt.Chart(pd.DataFrame({"x": [0.6, 1.0], "y": [0.6, 1.0]})).mark_line(
        strokeDash=[5, 4], color=ui.MUTED).encode(x=alt.X("x:Q", scale=axis_scale),
                                                  y=alt.Y("y:Q", scale=axis_scale))
    points = alt.Chart(cal).mark_circle(color=ui.BLUE, opacity=0.9).encode(
        x=alt.X("predicted:Q", title="Predicted success rate", axis=alt.Axis(format="%"),
                scale=alt.Scale(domain=[0.6, 1.0])),
        y=alt.Y("observed:Q", title="Observed success rate", axis=alt.Axis(format="%"),
                scale=alt.Scale(domain=[0.6, 1.0])),
        size=alt.Size("flights:Q", legend=None, scale=alt.Scale(range=[60, 600])),
        tooltip=[alt.Tooltip("bin:N", title="Predicted range"),
                 alt.Tooltip("predicted:Q", title="Predicted", format=".1%"),
                 alt.Tooltip("observed:Q", title="Observed", format=".1%"),
                 alt.Tooltip("flights:Q", title="Flights")])
    left, _ = st.columns([1, 1])
    with left:
        ui.show(diagonal + points, 320)
        st.caption("Each dot is a range of predicted probabilities, sized by the number of "
                   "flights. Dots on the dashed line mean predictions matched reality.")

st.caption(f"Snapshot exported {m['exported_at'].replace('T', ' ').replace('Z', ' UTC')}.")
ui.footer()
