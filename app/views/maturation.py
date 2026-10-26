"""The Maturation Race: how fast vehicles earn proven reliability."""
import altair as alt
import pandas as pd
import streamlit as st

import data
import ui

ui.header("The Maturation Race",
          "How fast vehicles earn proven reliability: the 95% lower bound on success rate, "
          "flight by flight.")

maturation = data.table("mart_maturation")
reliability = data.table("mart_vehicle_reliability")
debut = data.table("mart_debut_curve")
survival = data.table("mart_failure_free_survival")

DEFAULTS = {
    "family": ["Falcon 9", "Atlas V", "Electron", "Ariane 6", "Vulcan", "New Glenn"],
    "configuration": ["Falcon 9 Block 5", "Electron", "Ariane 64", "Ariane 62", "Vulcan VC2S",
                      "New Glenn"],
}

c1, c2, c3 = st.columns([1.2, 1.2, 1])
lens_label = c1.segmented_control(
    "Count flights by", ["Family", "Configuration"], default="Family",
    help="Family counts every version of a vehicle together, so Falcon 9 starts at its 2010 "
         "first flight. Configuration starts each version at flight 1, so Falcon 9 Block 5 "
         "inherits none of the earlier learning. Family is the fair comparison for a new vehicle.")
lens = (lens_label or "Family").lower()
measure = c2.segmented_control("Show", ["Lower bound", "Success rate"], default="Lower bound",
                               help="Lower bound: with this much evidence, reliability is at "
                                    "least this high (95% confidence). Success rate: successes "
                                    "divided by flights so far.")
measure = measure or "Lower bound"
max_flight = c3.slider("Flights shown", 10, 300, 100, step=10)

units = reliability[(reliability["lens"] == lens) & (reliability["flights"] >= 2)] \
    .sort_values(["is_active", "flights"], ascending=False)
names = units["unit_name"].tolist()
default = [n for n in DEFAULTS[lens] if n in names] or names[:5]
chosen = st.multiselect("Vehicles", names, default=default, max_selections=8)

if not chosen:
    st.info("Pick at least one vehicle.")
    st.stop()

curves = maturation[(maturation["lens"] == lens) & maturation["unit_name"].isin(chosen)
                    & (maturation["flight_number"] <= max_flight)]
y_field = "reliability_lower_95" if measure == "Lower bound" else "cum_reliability"
color = alt.Color("unit_name:N", sort=chosen,
                  scale=alt.Scale(domain=chosen, range=ui.SERIES[:len(chosen)]))

lines = alt.Chart(curves).mark_line(strokeWidth=2.5, interpolate="step-after").encode(
    x=alt.X("flight_number:Q", title="Flight number", scale=alt.Scale(domain=[1, max_flight])),
    y=alt.Y(f"{y_field}:Q", title=measure, axis=alt.Axis(format="%"),
            scale=alt.Scale(domain=[0, 1])),
    color=color,
    tooltip=[alt.Tooltip("unit_name:N", title="Vehicle"),
             alt.Tooltip("flight_number:Q", title="Flight"),
             alt.Tooltip("launch_name:N", title="Launch"),
             alt.Tooltip("outcome:N", title="Outcome"),
             alt.Tooltip("cum_reliability:Q", title="Success rate", format=".1%"),
             alt.Tooltip("reliability_lower_95:Q", title="Lower bound", format=".1%")],
)
failures = alt.Chart(curves[curves["outcome"] != "success"]).mark_point(
    shape="cross", size=70, strokeWidth=2, filled=False).encode(
    x="flight_number:Q", y=f"{y_field}:Q", color=color,
    tooltip=[alt.Tooltip("unit_name:N", title="Vehicle"),
             alt.Tooltip("flight_number:Q", title="Flight"),
             alt.Tooltip("launch_name:N", title="Launch"),
             alt.Tooltip("outcome:N", title="Outcome")])
targets = pd.DataFrame({"y": [0.8, 0.9], "label": ["proven at 80%", "proven at 90%"]})
rules = alt.Chart(targets).mark_rule(strokeDash=[5, 4], color=ui.MUTED).encode(y="y:Q")
rule_labels = alt.Chart(targets).mark_text(align="right", dy=-6, color=ui.MUTED, fontSize=11) \
    .encode(y="y:Q", x=alt.X("xpos:Q"), text="label:N") \
    .transform_calculate(xpos=str(max_flight))

st.subheader(f"{measure} by flight number")
ui.show(rules + rule_labels + lines + failures, 420)
st.caption("Crosses mark failures and partial failures. Lines step at each flight.")

# ---- the record table ---------------------------------------------------------
table = units[units["unit_name"].isin(chosen)].set_index("unit_name").loc[chosen].reset_index()
st.dataframe(
    table.assign(
        reliability=table["reliability"] * 100,
        reliability_lower_95=table["reliability_lower_95"] * 100,
        reliability_vs_expected=table["reliability_vs_expected"] * 100,
    )[["unit_name", "flights", "successes", "reliability", "reliability_lower_95",
       "flights_to_lb_80", "flights_to_lb_90", "reliability_vs_expected"]],
    hide_index=True, width="stretch",
    column_config={
        "unit_name": st.column_config.TextColumn("Vehicle"),
        "flights": st.column_config.NumberColumn("Flights"),
        "successes": st.column_config.NumberColumn("Successes"),
        "reliability": st.column_config.NumberColumn("Success rate", format="%.1f%%"),
        "reliability_lower_95": st.column_config.NumberColumn("Lower bound", format="%.1f%%"),
        "flights_to_lb_80": st.column_config.NumberColumn(
            "Proven at 80%, flight", help="Flight at which the lower bound first reached 80%. "
                                          "Empty: not yet."),
        "flights_to_lb_90": st.column_config.NumberColumn("Proven at 90%, flight"),
        "reliability_vs_expected": st.column_config.NumberColumn(
            "vs expected", format="%+.1f",
            help="Gap in reliability points to a typical vehicle of the same era over the same "
                 "flights. The vehicle's own flights are left out of the comparison."),
    },
)

# ---- headline -------------------------------------------------------------
established = reliability[reliability["flights"] >= 20]
medians = established.groupby("lens")["flights_to_lb_80"].median()
st.markdown(
    f"Among vehicles with 20 or more orbital flights, the median vehicle reached a lower bound "
    f"of 80% at flight **{medians.get('family', float('nan')):g}** counting by family and "
    f"**{medians.get('configuration', float('nan')):g}** counting by configuration. "
    "New versions of an existing vehicle inherit its learning, which is why the family "
    "count is the fair benchmark for a new vehicle."
)

st.divider()
left, right = st.columns(2, gap="large")
eras = ["all", "2000-present", "1980-1999", "1957-1979"]

with left:
    st.subheader("Success rate by flight number")
    era = st.selectbox("Era of first flight", eras, key="debut_era",
                       format_func=lambda e: "All eras" if e == "all" else e)
    curve = debut[(debut["lens"] == lens) & (debut["era"] == era)].sort_values("flight_band_start")
    order = curve["flight_band"].tolist()
    bars = alt.Chart(curve).mark_bar(color=ui.BLUE, cornerRadiusTopLeft=2,
                                     cornerRadiusTopRight=2).encode(
        x=alt.X("flight_band:N", sort=order, title="Flight", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("success_rate:Q", title="Success rate", axis=alt.Axis(format="%"),
                scale=alt.Scale(domain=[0, 1])),
        tooltip=[alt.Tooltip("flight_band:N", title="Flight"),
                 alt.Tooltip("success_rate:Q", title="Success rate", format=".1%"),
                 alt.Tooltip("success_rate_lower_95:Q", title="95% low", format=".1%"),
                 alt.Tooltip("success_rate_upper_95:Q", title="95% high", format=".1%"),
                 alt.Tooltip("attempts:Q", title="Flights"),
                 alt.Tooltip("vehicles:Q", title="Vehicles")])
    whiskers = alt.Chart(curve).mark_rule(color=ui.LIGHT).encode(
        x=alt.X("flight_band:N", sort=order), y="success_rate_lower_95:Q",
        y2="success_rate_upper_95:Q")
    ui.show(bars + whiskers, 300)
    first = curve.iloc[0]
    st.caption(f"A first flight succeeds {ui.pct(first['success_rate'])} of the time "
               f"({int(first['vehicles'])} vehicles). Lines show the 95% interval.")

with right:
    st.subheader("Clean opening run")
    era2 = st.selectbox("Era of first flight", eras, key="surv_era",
                        format_func=lambda e: "All eras" if e == "all" else e)
    km = survival[(survival["lens"] == lens) & (survival["era"] == era2)
                  & (survival["flight_number"] <= 30)].sort_values("flight_number")
    start = pd.DataFrame([{"flight_number": 0, "survival": 1.0, "survival_lower_95": 1.0,
                           "survival_upper_95": 1.0}])
    km = pd.concat([start, km], ignore_index=True)
    band = alt.Chart(km).mark_area(interpolate="step-after", color=ui.BLUE, opacity=0.18).encode(
        x=alt.X("flight_number:Q", title="Flights flown", scale=alt.Scale(domain=[0, 30])),
        y=alt.Y("survival_lower_95:Q", title="Still without a failure",
                axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
        y2="survival_upper_95:Q")
    step = alt.Chart(km).mark_line(interpolate="step-after", color=ui.BLUE, strokeWidth=2.5).encode(
        x="flight_number:Q", y="survival:Q",
        tooltip=[alt.Tooltip("flight_number:Q", title="After flight"),
                 alt.Tooltip("survival:Q", title="Still clean", format=".1%")])
    ui.show(band + step, 300)
    at = lambda n: km.loc[km["flight_number"] <= n, "survival"].iloc[-1]
    st.caption(f"{ui.pct(at(5))} of vehicles get through their first 5 flights without a "
               f"failure, {ui.pct(at(10))} through their first 10 (Kaplan-Meier, shaded 95% band).")

ui.footer()
