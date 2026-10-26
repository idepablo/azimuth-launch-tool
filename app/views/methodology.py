"""Methodology: definitions, decisions and limits, in plain terms."""
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

st.caption(f"Snapshot exported {m['exported_at'].replace('T', ' ').replace('Z', ' UTC')}.")
ui.footer()
