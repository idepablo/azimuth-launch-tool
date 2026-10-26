"""Vehicle page: one rocket's whole story in one place.

Opened from the menu, by clicking a vehicle in any table, or by link
(?vehicle=Electron&lens=family). From here, one click simulates its future.
"""
import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

import data
import ui

RECENT = 20  # flights in the "recent" window

maturation = data.table("mart_maturation")
reliability = data.table("mart_vehicle_reliability")
vehicles = data.table("dim_vehicle")

# ---- which vehicle -------------------------------------------------------------
params = st.query_params
lens = params.get("lens", "family")
lens = lens if lens in ("family", "configuration") else "family"

units = reliability[reliability["lens"] == lens].copy()
units["provider"] = units["unit_key"].map(lambda k: ui.provider_of(lens, k))
units = units.sort_values(["is_active", "flights"], ascending=False)
names = units["unit_name"].tolist()
provider_by_name = dict(zip(units["unit_name"], units["provider"]))

wanted = params.get("vehicle")
if wanted not in names:
    focus = st.session_state.get("focus_provider")
    mine = units[units["provider"] == focus]
    wanted = (mine if len(mine) else units)["unit_name"].iloc[0]

c1, c2 = st.columns([3, 1])
vehicle = c1.selectbox("Vehicle", names, index=names.index(wanted),
                       format_func=lambda n: f"{n} ({provider_by_name.get(n) or 'unknown'})")
lens_label = c2.segmented_control(
    "Count flights by", ["Family", "Configuration"], default=lens.capitalize(),
    help="Family counts every version together (all Falcon 9 blocks). "
         "Configuration treats each version separately.")
new_lens = (lens_label or "Family").lower()
if new_lens != lens:
    st.query_params.update({"lens": new_lens})
    st.query_params.pop("vehicle", None)
    st.rerun()
st.query_params.update({"vehicle": vehicle, "lens": lens})

v = units[units["unit_name"] == vehicle].iloc[0]
history = maturation[(maturation["lens"] == lens) & (maturation["unit_key"] == v["unit_key"])] \
    .sort_values("flight_number")

# ---- header ------------------------------------------------------------------------
status = "Active" if v["is_active"] else "Retired"
st.title(vehicle)
st.caption(f"{provider_by_name.get(vehicle) or 'Unknown provider'} · first flight "
           f"{v['first_flight_at'].strftime('%d %b %Y')} · latest "
           f"{v['latest_flight_at'].strftime('%d %b %Y')} · {status} · "
           f"first-flight era {v['era']}")

if st.button(f"Simulate {vehicle}'s future", type="primary", disabled=not v["is_active"],
             help=None if v["is_active"] else "The simulator covers active vehicles."):
    st.switch_page("views/simulator.py", query_params={"vehicle": vehicle})

# ---- the record -------------------------------------------------------------------
m1, m2, m3, m4 = st.columns(4)
m1.metric("Orbital flights", f"{int(v['flights']):,}")
m1.caption(f"{int(v['successes'])} successes · {int(v['failures'])} failures · "
           f"{int(v['partial_failures'])} partial")
m2.metric("Success rate", ui.pct(v["reliability"]))
m2.caption(f"95% lower bound {ui.pct(v['reliability_lower_95'])}")


def milestone(level, first):
    above = v["reliability_lower_95"] >= level
    if pd.isna(first):
        return "Not yet", "lower bound has never reached it"
    return ("Above now" if above else "Below now"), f"first reached at flight {int(first)}"


value, note = milestone(0.8, v["flights_to_lb_80"])
m3.metric("Proven at 80%", value)
m3.caption(note)
m4.metric("vs a typical vehicle", ui.pts(v["reliability_vs_expected"]),
          help="Gap in reliability points to a typical vehicle of the same era over the same "
               "flights, with this vehicle's own flights left out of the comparison.")
m4.caption(f"expected {ui.pct(v['expected_reliability'])} at this stage of life")

# recent vs lifetime: the same evidence rule, applied to the last flights only
if len(history) > RECENT:
    last = history.tail(RECENT)
    s = int((last["outcome"] == "success").sum())
    n = len(last)
    p = s / n
    lb = (p + 1.96**2 / (2 * n) - 1.96 * np.sqrt(p * (1 - p) / n + 1.96**2 / (4 * n**2))) \
        / (1 + 1.96**2 / n)
    st.markdown(
        f"**Last {RECENT} flights:** {s} of {n} successful ({ui.pct(p)}, lower bound "
        f"{ui.pct(lb)}), against {ui.pct(v['reliability'])} over all "
        f"{int(v['flights'])} flights. With only {RECENT} flights, the recent figure carries "
        f"more uncertainty than the lifetime one."
    )

st.divider()

# ---- charts -------------------------------------------------------------------------
left, right = st.columns(2, gap="large")

with left:
    st.subheader("Flights per year")
    per_year = history.assign(year=history["launched_at"].dt.year,
                              result=history["outcome"].map({
                                  "success": "Success", "failure": "Failure",
                                  "partial_failure": "Partial failure"}))
    per_year = per_year.groupby(["year", "result"], as_index=False).size()
    order = ["Success", "Partial failure", "Failure"]
    bars = alt.Chart(per_year).mark_bar().encode(
        x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0, labelOverlap=True)),
        y=alt.Y("size:Q", title="Flights", axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("result:N", sort=order,
                        scale=alt.Scale(domain=order, range=[ui.BLUE, ui.AMBER, "#E46F6F"])),
        order=alt.Order("result_rank:Q"),
        tooltip=[alt.Tooltip("year:O", title="Year"), alt.Tooltip("result:N", title="Result"),
                 alt.Tooltip("size:Q", title="Flights")],
    ).transform_calculate(result_rank="indexof(['Success', 'Partial failure', 'Failure'], datum.result)")
    ui.show(bars, 280)

with right:
    st.subheader("Proven reliability, flight by flight")
    x = alt.X("flight_number:Q", title="Flight number")
    line = alt.Chart(history).mark_line(color=ui.BLUE, strokeWidth=2.5, interpolate="step-after") \
        .encode(x=x, y=alt.Y("reliability_lower_95:Q", title="Lower bound",
                             axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
                tooltip=[alt.Tooltip("flight_number:Q", title="Flight"),
                         alt.Tooltip("launch_name:N", title="Launch"),
                         alt.Tooltip("reliability_lower_95:Q", title="Lower bound", format=".1%")])
    misses = alt.Chart(history[history["outcome"] != "success"]).mark_point(
        shape="cross", size=80, strokeWidth=2, color="#E46F6F").encode(
        x=x, y="reliability_lower_95:Q",
        tooltip=[alt.Tooltip("flight_number:Q", title="Flight"),
                 alt.Tooltip("launch_name:N", title="Launch"),
                 alt.Tooltip("outcome:N", title="Outcome")])
    targets = alt.Chart(pd.DataFrame({"y": [0.8, 0.9]})).mark_rule(
        strokeDash=[5, 4], color=ui.MUTED).encode(y="y:Q")
    ui.show(targets + line + misses, 280)
    st.caption("Crosses mark failures. Dashed lines: 80% and 90%.")

# ---- versions in the family -----------------------------------------------------------
if lens == "family":
    configs = vehicles[vehicles["family_name"] == v["unit_key"]][["vehicle_key", "vehicle_full_name"]]
    config_rel = reliability[(reliability["lens"] == "configuration")
                             & reliability["unit_key"].isin(configs["vehicle_key"])]
    if len(config_rel) > 1:
        st.subheader("Versions")
        st.dataframe(
            config_rel.sort_values("first_flight_at").assign(
                reliability=config_rel["reliability"] * 100)[
                ["unit_name", "flights", "reliability", "first_flight_at", "latest_flight_at"]],
            hide_index=True, width="stretch",
            column_config={
                "unit_name": st.column_config.TextColumn("Version"),
                "flights": st.column_config.NumberColumn("Flights"),
                "reliability": st.column_config.NumberColumn("Success rate", format="%.1f%%"),
                "first_flight_at": st.column_config.DateColumn("First flight", format="MMM YYYY"),
                "latest_flight_at": st.column_config.DateColumn("Latest flight", format="MMM YYYY"),
            },
        )

# ---- launch history -------------------------------------------------------------------
st.subheader("Launch history")
only_misses = st.toggle("Only failures and partial failures", value=False)
log = history.sort_values("flight_number", ascending=False)
if only_misses:
    log = log[log["outcome"] != "success"]
log = log.assign(outcome=log["outcome"].map({"success": "Success", "failure": "Failure",
                                             "partial_failure": "Partial failure"}))
st.dataframe(
    log[["flight_number", "launched_at", "launch_name", "outcome"]],
    hide_index=True, width="stretch", height=min(420, 38 + 35 * max(1, len(log))),
    column_config={
        "flight_number": st.column_config.NumberColumn("Flight"),
        "launched_at": st.column_config.DateColumn("Date", format="D MMM YYYY"),
        "launch_name": st.column_config.TextColumn("Launch"),
        "outcome": st.column_config.TextColumn("Outcome"),
    },
)

ui.footer()
