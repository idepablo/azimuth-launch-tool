# AZIMUTH — Launch Market BI Platform

A data analytics platform that tracks how the global launch market is evolving (cadence, reliability, reuse, mass to orbit, and market share) to assess where a new heavy-lift vehicle realistically stands against the field.

**Status:** In active development. Phase 1 (bronze ingestion) complete as of 11 August 2026. Built as an end-to-end BI engineering project on Databricks.

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
- **Ask AZIMUTH** *(v2)* — natural-language questions answered with a chart, grounded in the data.

The platform is provider-agnostic: it models the whole market and lets any vehicle be set as the focus.

---

## Architecture

Data flows through a medallion (bronze → silver → gold) lakehouse architecture. Ingestion is deliberately split into two independent jobs:

```
Launch Library 2 API
        │  (Python: paginated, throttled, resumable)
        ▼
   raw/*.json  — immutable, date-stamped, one file per page
        │  (Python: flatten + lineage columns)
        ▼
   staging/launches.parquet
        │  (upload to Unity Catalog volume, MERGE on launch_id)
        ▼
   Bronze (raw Delta)  +  load_audit
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

The fetch and the load are separate scripts. The API is rate limited to roughly 15 calls an hour, so a full historical pull takes about five hours. If both jobs were one script, any bug in the load logic would cost another five hours of fetching. Split apart, the load re-runs against files already on disk in seconds.

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

## Repository structure

```
azimuth/
├── docs/
│   └── scope.md              # grain, scope, outcome definitions, known limitations
├── audit.ipynb               # Phase 0 exploratory data audit
├── fetch_launches.py         # paginated, throttled, resumable API fetch → raw/
├── flatten_launches.py       # nested JSON → flat parquet with lineage columns
├── load_to_bronze.py         # upload to volume, MERGE into Delta, write audit row
├── requirements.txt
└── .gitignore
```

`raw/` and `staging/` are generated artefacts and are not tracked.

---

## Design decisions

The full set of scoping decisions lives in **[docs/scope.md](docs/scope.md)**. The ones that most shape the codebase:

**Fetch and load are separate jobs.** Covered above. The second reason is that the raw JSON files become an immutable record of exactly what the API returned on a given date. If a number looks wrong three months from now, it is possible to check whether the source was wrong or the code was.

**Raw files are immutable and date-stamped.** Every page is written to `raw/launches_YYYYMMDD_pageNNN.json` and never overwritten. A re-run on a different day produces a new set rather than replacing the old one.

**Checkpoint state is written after the file, not before.** The fetch saves a small state file recording the next URL, the page number, and the ingest date of the original run. Saving state after the page is written means a crash between those two operations costs a repeated page rather than a silently skipped one. The ingest date is carried in state so a run that starts on the 11th and resumes on the 12th still stamps every file with the 11th; those files belong to one logical run.

**Bronze stores every column as a string.** Casting in bronze means one malformed value fails the entire load and the row is lost. Casting in silver means a bad value surfaces as a failed test with the record still available to inspect. Bronze holds data as it arrived.

**The merge is guarded on `last_updated`.** A stored row is only updated when the incoming record is newer. Without that guard, reprocessing an older raw file would overwrite a current record with stale data.

**Lineage columns are added at flatten time.** Every row carries `source_file` and `ingest_date`, neither of which comes from the API. They make it possible to trace any warehouse row back to the exact file it came from.

**Vehicle identity is `rocket.configuration.id`, not `rocket.id`.** A "rocket" in the API is an instance of a flight; the configuration is the vehicle type, and the vehicle type is the unit of comparison. Configurations are loaded separately rather than extracted from launch records, because fetching launches in detailed mode returns configuration objects nested six levels deep including manufacturer biographies and image licences.

**Launch status is split into outcomes and schedule states.** The API defines nine statuses that are really two concepts. Four describe a known outcome; five describe where a launch sits in the schedule. That split is the censoring boundary for any reliability or maturation analysis. Vehicles still in development have not had their event yet, which is the situation survival analysis exists to handle; excluding them would bias the estimates.

**Partial failures are reported as their own category.** Status 7 covers two genuinely different situations and the API provides no field distinguishing them. Collapsing it into either success or failure asserts something the source cannot support. The reasoning is in the scope document.

---

## Data quality

A `load_audit` table records one row per load: run id, timestamp, source file, rows in source, rows inserted, rows updated, duration, and status. It is written whether the merge succeeds or fails, so failed runs stay on the record.

This is what makes the idempotency claim checkable rather than asserted:

| Run | Rows in source | Inserted | Updated | Rows in bronze |
|---|---|---|---|---|
| 1 | 7,598 | 7,598 | 0 | 7,598 |
| 2 | 7,598 | 0 | 0 | 7,598 |

Known limitations, including a pagination gap risk that row counts would not reveal, are documented in [docs/scope.md](docs/scope.md#known-limitations).

---

## What I learned

**A config value that is silently wrong is worse than one that errors.** Switching from the development API to production, I meant to set `SLEEP_SECONDS` to 240 and set `PAGE_SIZE` to 240 instead. The two constants sit next to each other. Nothing errored: the API capped the page size at its own maximum and kept serving pages with no delay between them. Ten pages went through in about twenty seconds before I noticed the timing was wrong. The fix was retry logic on 429s; the better fix, still to do, is validating configuration against the API's documented limits at startup.

**Read the traceback, not the summary line.** An installation failure that looked like a Python version incompatibility turned out, four lines down the stack, to be an SSL certificate problem specific to macOS Python installs. I changed Python versions on the strength of the summary before reading far enough to find the actual cause.

**`.gitignore` only ignores what git is not already tracking.** The project folder had a `.git` in it from an earlier experiment, with `.venv` committed. Adding `.venv/` to `.gitignore` afterwards changed nothing. Nothing had been pushed, so the history was rebuilt clean.

**Development mirrors are for code, not for conclusions.** The Space Devs run a development endpoint without rate limits. It holds 354 records where production holds 7,589. Every null rate and coverage figure measured against it had to be re-checked against production before it meant anything.

**Matching row counts prove less than they appear to.** 7,598 rows and 7,598 unique launch ids rules out duplicates. It does not rule out gaps: offset pagination on a dataset that changes mid-run can push a record past a boundary already read, and nothing in the count would show it.

**Resilience features are worth building before you need them.** Both the checkpoint resume and the 429 retry were exercised by real failures during the production backfill, not by tests. The laptop lid closed at page 10; the API rate limited at page 40 while unattended. Neither cost any data.

---

## How I used AI

I used Claude throughout this project, and it is worth being specific about where, because "I used AI" covers everything from autocomplete to having a model do the work.

**Where it helped:** scaffolding the phase plan; writing first drafts of the ingestion scripts; explaining unfamiliar concepts (Unity Catalog volumes, MERGE semantics, survival analysis censoring); reviewing my reasoning and catching gaps; and rubber-ducking design decisions before I committed to them.

**Where I did the work:** every scoping and modeling decision in `docs/scope.md` is mine. The choice to treat partial failures as their own category, to scope orbital via `mission.orbit` with Unknown as a third bucket, to identify vehicles by configuration rather than instance, and to split fetch from load, were decisions I made and can defend. I ran the data audit that produced them.

**Where it was wrong:** it guessed an API endpoint name that did not exist (`config/launch_status/` rather than `config/launch_statuses/`), and it misdiagnosed an SSL certificate failure as a Python version problem, which cost me an unnecessary reinstall. Both were caught by reading actual output rather than trusting the explanation.

The working pattern that came out of this: use it to move faster on things I understand, use it to learn things I do not, and verify anything it asserts about an external system against that system.

---

## Roadmap

- [x] Ingestion → bronze layer
- [x] Load audit table
- [ ] Re-run data-integrity checks against full history
- [ ] dbt models → silver + gold (star schema)
- [ ] Data quality tests
- [ ] Core KPIs
- [ ] Maturation Race visualization
- [ ] Market Overview dashboard
- [ ] Scenario Simulator
- [ ] Ask AZIMUTH (AI query layer, v2)

---

## Run it yourself

Requires Python 3.12 and a Databricks workspace (Free Edition is sufficient).

**1. Clone and set up the environment**

```bash
git clone https://github.com/idepablo/azimuth-launch-tool.git
cd azimuth-launch-tool
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**2. Create the Databricks objects**

In your workspace, create a catalog `azimuth`, a schema `bronze` inside it, and a managed volume `raw` inside that. Generate a personal access token from Settings → Developer → Access tokens.

**3. Configure credentials**

Create a `.env` file in the project root:

```
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=your-token
```

`.env` is gitignored and must stay that way.

**4. Fetch the data**

```bash
python fetch_launches.py
```

The script defaults to the production API with a 240-second delay between calls, which keeps it inside the rate limit. A full backfill is 76 pages and takes roughly five hours. It is resumable: if it stops, re-running picks up from the last completed page.

For development, point `BASE_URL` at `https://lldev.thespacedevs.com/2.3.0/launches/previous/` and set `SLEEP_SECONDS = 0`. The development mirror has no rate limit and a much smaller dataset.

On macOS, prevent the machine sleeping mid-run:

```bash
caffeinate -dis python fetch_launches.py
```

**5. Flatten and load**

```bash
python flatten_launches.py
python load_to_bronze.py
```

`load_to_bronze.py` is idempotent. Running it twice against the same source produces zero inserts and zero updates on the second run.

---

## Acknowledgements

Launch data from the [Launch Library 2 API](https://thespacedevs.com/llapi), maintained by [The Space Devs](https://thespacedevs.com/), and available free of charge.
