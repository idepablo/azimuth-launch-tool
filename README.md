# AZIMUTH — Launch Market BI Platform 

A data analytics platform that tracks how the global launch market is evolving (cadence, reliability, reuse, mass to orbit, and market share) to assess where a new heavy-lift vehicle realistically stands against the field.

**Status:** In active development. Built as an end-to-end BI engineering project on Databricks.

---

## The question this answers

This project is built backward from a real business decision, not from the data.

**Stakeholder:** VP of Launch Services Strategy at a provider bringing a new heavy-lift vehicle to market.

**The decision:** how much to invest in production rate, what reliability to commit to leadership and customers, and when to go to market.

**The question:** *Where does our new vehicle realistically stand vs. competitors? How fast do new vehicles historically earn reliability? What launch cadence and reliability would make us a credible 2nd / 3rd company in the market within three years?*

**KPIs that inform it:** launch cadence, reliability (overall and by flight-number-in-life), market share (by count and by mass to orbit), reuse rate, schedule reliability.

---

## What it is

AZIMUTH ingests global launch data, models it into a clean analytical layer, and exposes it through an interactive product with four views:

- **Market Overview** — the KPI dashboard.
- **The Maturation Race** — every vehicle's reliability and cadence aligned to flight #1, with uncertainty bands.
- **Scenario Simulator** — what-if projections of a vehicle's future market position.
- **Ask AZIMUTH** — natural-language questions answered with a chart, grounded in the data.

The platform is provider-agnostic: it models the whole market and lets any vehicle be set as the focus.

---

## Architecture

Data flows through a medallion (bronze → silver → gold) lakehouse architecture:

```
Launch Library 2 API
        │  (Python ingestion)
        ▼
   Bronze (raw Delta)
        │  (dbt: clean, type, dedupe)
        ▼
   Silver (cleaned)
        │  (dbt: dimensional model)
        ▼
   Gold (fct_launches + dimensions)
        │
        ▼
   Analysis + dashboards
```

*(Diagram and details expand as the build progresses.)*

---

## Tech stack

| Layer | Tool |
|---|---|
| Platform | Databricks (Free Edition) |
| Storage | Delta Lake |
| Ingestion | Python (REST API) |
| Transformation | dbt |
| Analysis | SQL, pandas, lifelines |
| Visualization | Streamlit / Databricks dashboards |
| Version control | Git / GitHub / Databricks Repos |

**Data source:** [Launch Library 2 API](https://thespacedevs.com/llapi) by The Space Devs.

---

## Design decisions

---

## What I learned

---

## How I used AI

---

## Roadmap

- [ ] Ingestion → bronze layer
- [ ] dbt models → silver + gold (star schema)
- [ ] Data quality tests
- [ ] Core KPIs
- [ ] Maturation Race visualization
- [ ] Market Overview dashboard
- [ ] Scenario Simulator
- [ ] Ask AZIMUTH (AI query layer)

---

## Run it yourself

_Setup instructions coming soon._
