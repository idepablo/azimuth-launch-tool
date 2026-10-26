"""Ask AZIMUTH: plain-language questions answered from the app's own data.

Flow for each question:
  1. The model reads the table descriptions and AZIMUTH's definitions, and
     either writes one SQL query or says the question is out of scope.
  2. The query runs in DuckDB over the same snapshot the app shows. The
     connection cannot read files, reach the network or write anything, and
     only a single SELECT is accepted.
  3. If the query fails, the model gets the error and one chance to fix it.
  4. The model turns the result rows into a short answer, in the language
     of the question. The SQL is always shown with the answer.

Nothing outside the snapshot is used, so the answers can only be as good as
the data the rest of the app shows.
"""
import json
import os

import duckdb
import pandas as pd

import data
import ui

MODEL = "claude-haiku-5-5"
MAX_ROWS = 50

SCHEMA = """
Tables (DuckDB SQL). Provider names are short forms: SpaceX, CASC, Roscosmos, Rocket Lab,
Arianespace, United Launch Alliance, Blue Origin, ISRO, JAXA, MHI, NASA, Khrunichev, etc.

launches: one row per launch in the source, 1957 to the data date.
  launch_id, launch_name, launched_at (timestamp), launch_year (int), provider, vehicle
  (configuration full name, e.g. 'Falcon 9 Block 5'), vehicle_family (e.g. 'Falcon 9'),
  orbit_name, pad_name, status_name, scope_class ('orbital', 'suborbital', 'non_earth_launch',
  'pre_launch_failure', 'unclassified'), is_outcome_known (bool), outcome ('success',
  'failure', 'partial_failure', or NULL when not yet known).

vehicles: current reliability record per vehicle, orbital flights with a known outcome only.
  lens ('family' or 'configuration'), vehicle (family or configuration name), provider (operator
  of its latest launch), era ('1957-1979', '1980-1999', '2000-present', by first flight),
  flights, successes, failures, partial_failures, reliability (successes / flights, 0 to 1),
  reliability_lower_95 (95% Wilson lower bound, 0 to 1), first_flight_at, latest_flight_at,
  flights_to_lb_80 / flights_to_lb_90 (flight at which the lower bound first reached 80% / 90%,
  NULL if never), reliability_vs_expected (gap in reliability to a typical vehicle of the same
  era at the same stage of life, 0.05 = 5 points), is_active (flew in the two years before the
  data date).

yearly_share: orbital attempts per provider per year.
  launch_year, provider, country, sector, attempts, successes, share_of_attempts (0 to 1),
  rank_by_attempts, is_partial_year.

debut_curve: success rate by how far into its life a vehicle is.
  lens, era ('all' or an era), flight_band (e.g. '1', '6-10', '101+'), flight_band_start,
  vehicles, attempts, successes, success_rate (0 to 1).
"""

RULES = """
AZIMUTH definitions, which every query must follow:
- Count launches as orbital attempts with a known outcome: scope_class = 'orbital' AND
  is_outcome_known, unless the user explicitly asks about suborbital or all launches.
- Success is strict: partial failures are not successes. Success rate = successes / attempts.
- For vehicle reliability, use the vehicles table with lens = 'family' unless the user names a
  specific version (then 'configuration'). 'Reliable' or 'proven' means a high
  reliability_lower_95, not just a high reliability; require a sensible minimum of flights.
- Match names case-insensitively (ILIKE). "This year" means the year of the data date.
- Percentages in the data are fractions between 0 and 1.
- Return at most 50 rows, ordered usefully. Name columns clearly.
- Follow-ups: earlier turns of the conversation are given for context. "And in 2024?" or "what
  about Rocket Lab?" reuse the previous question with the change. If the user asks to explain or
  give more detail about a previous answer, it is in scope: write a query that returns the detail
  behind it (for example the rows that make up a total).

Scope: only questions answerable from these tables are in scope: launches, providers, vehicles,
reliability, cadence and market share. Out of scope: anything needing other data (payloads,
customers, prices, costs, mission details beyond the name, reasons for a failure, people, news,
predictions or opinions), and anything unrelated to space launches.
"""

PLAN_TOOL = {
    "name": "plan",
    "description": "Decide whether the question is in scope and, if so, give one DuckDB query.",
    "input_schema": {
        "type": "object",
        "properties": {
            "in_scope": {"type": "boolean"},
            "sql": {"type": "string", "description": "One SELECT query, or empty if out of scope."},
            "note": {"type": "string",
                     "description": "One short sentence, in the language of the question and in plain words, on how it was interpreted (no SQL, table or column names)."},
        },
        "required": ["in_scope", "sql", "note"],
    },
}


class AskError(Exception):
    pass


def api_key():
    try:
        import streamlit as st
        key = st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:
        key = None
    return key or os.environ.get("ANTHROPIC_API_KEY")


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=api_key())


def tables():
    """The four question-facing tables, built from the snapshot."""
    launches = data.table("fct_launches")
    vehicles = data.table("dim_vehicle")[["vehicle_key", "vehicle_full_name", "family_name"]]
    providers = data.table("dim_provider")[["provider_key", "provider_name"]]
    df = launches.merge(vehicles, on="vehicle_key", how="left").merge(providers, on="provider_key", how="left")
    status = df["status_name"].fillna("").str.lower()
    outcome = pd.Series(pd.NA, index=df.index, dtype="object")
    outcome[df["is_outcome_known"] & df["is_success"].fillna(False)] = "success"
    outcome[df["is_outcome_known"] & ~df["is_success"].fillna(False)
            & status.str.contains("partial")] = "partial_failure"
    outcome[df["is_outcome_known"] & ~df["is_success"].fillna(False)
            & ~status.str.contains("partial")] = "failure"
    launched = pd.to_datetime(df["launched_at"], utc=True).dt.tz_localize(None)
    launches_t = pd.DataFrame({
        "launch_id": df["launch_id"], "launch_name": df["launch_name"],
        "launched_at": launched, "launch_year": launched.dt.year,
        "provider": df["provider_name"].map(ui.short), "vehicle": df["vehicle_full_name"],
        "vehicle_family": df["family_name"], "orbit_name": df["orbit_name"],
        "pad_name": df["pad_name"], "status_name": df["status_name"],
        "scope_class": df["scope_class"], "is_outcome_known": df["is_outcome_known"],
        "outcome": outcome,
    })

    rel = data.table("mart_vehicle_reliability").copy()
    rel["provider"] = [ui.provider_of(lens, key) for lens, key in zip(rel["lens"], rel["unit_key"])]
    vehicles_t = rel.rename(columns={"unit_name": "vehicle"})[[
        "lens", "vehicle", "provider", "era", "flights", "successes", "failures",
        "partial_failures", "reliability", "reliability_lower_95", "first_flight_at",
        "latest_flight_at", "flights_to_lb_80", "flights_to_lb_90", "reliability_vs_expected",
        "is_active"]]

    share = data.table("mart_market_share_yearly")
    share_t = share.assign(provider=share["provider_name"].map(ui.short))[[
        "launch_year", "provider", "country", "sector", "attempts", "successes",
        "share_of_attempts", "rank_by_attempts", "is_partial_year"]]

    debut_t = data.table("mart_debut_curve")[[
        "lens", "era", "flight_band", "flight_band_start", "vehicles", "attempts", "successes",
        "success_rate"]]

    return {"launches": launches_t, "vehicles": vehicles_t, "yearly_share": share_t,
            "debut_curve": debut_t}


def run_sql(sql, frames):
    """Run one SELECT in a DuckDB that cannot touch files, the network or anything else."""
    con = duckdb.connect(config={"enable_external_access": False})
    try:
        statements = con.extract_statements(sql)
        if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
            raise AskError("Only a single SELECT query is allowed.")
        for name, frame in frames.items():
            con.register(name, frame)
        return con.execute(sql).fetchdf().head(MAX_ROWS)
    finally:
        con.close()


def _system(as_of):
    return [{"type": "text",
             "text": (f"You answer questions about AZIMUTH, a launch-market analytics app. "
                      f"The data runs through {as_of}.\n{SCHEMA}\n{RULES}"),
             "cache_control": {"type": "ephemeral"}}]


def _turns(context):
    """Earlier exchanges as alternating user/assistant messages."""
    messages = []
    for previous_question, previous_answer in context or []:
        messages.append({"role": "user", "content": previous_question})
        messages.append({"role": "assistant", "content": previous_answer or "(no answer)"})
    return messages


def plan(question, as_of, error=None, previous_sql=None, context=None):
    content = question
    if error:
        content += (f"\n\nYour previous query failed.\nQuery: {previous_sql}\nError: {error}\n"
                    "Write a corrected query.")
    messages = _turns(context) + [{"role": "user", "content": content}]
    response = _client().messages.create(
        model=MODEL, max_tokens=800, system=_system(as_of), messages=messages,
        tools=[PLAN_TOOL], tool_choice={"type": "tool", "name": "plan"})
    block = next(b for b in response.content if b.type == "tool_use")
    return block.input


def answer_text(question, note, sql, rows, as_of, context=None):
    table = rows.to_csv(index=False) if len(rows) else "(no rows)"
    prompt = (f"Question: {question}\nHow it was interpreted: {note}\nSQL: {sql}\n"
              f"Result (first {MAX_ROWS} rows):\n{table}\n\n"
              "Answer the question from this result only, in the same language as the question, "
              "in one to three plain sentences. Give the key numbers. Percentages in the data are "
              "fractions: 0.95 means 95%. If the result is empty, say that nothing matched. If the "
              "question asks to explain, say in plain words how the figure was worked out, using "
              "AZIMUTH's definitions. Never mention SQL, queries, tables or column names. Do not "
              "add facts that are not in the result. Do not use em dashes.")
    response = _client().messages.create(
        model=MODEL, max_tokens=400, system=_system(as_of),
        messages=_turns(context) + [{"role": "user", "content": prompt}])
    return "".join(b.text for b in response.content if b.type == "text").strip()


def ask(question, frames, as_of, context=None):
    """Return a dict: in_scope, answer, sql, rows, note, error.

    context: earlier (question, answer) pairs, so follow-ups make sense.
    """
    p = plan(question, as_of, context=context)
    if not p.get("in_scope") or not p.get("sql", "").strip():
        return {"in_scope": False, "answer": None, "sql": None, "rows": None,
                "note": p.get("note"), "error": None}
    sql = p["sql"].strip().rstrip(";")
    try:
        rows = run_sql(sql, frames)
    except Exception as first_error:
        p = plan(question, as_of, error=str(first_error)[:500], previous_sql=sql, context=context)
        sql = p.get("sql", "").strip().rstrip(";")
        try:
            rows = run_sql(sql, frames)
        except Exception as second_error:
            return {"in_scope": True, "answer": None, "sql": sql, "rows": None,
                    "note": p.get("note"), "error": str(second_error)[:300]}
    return {"in_scope": True,
            "answer": answer_text(question, p.get("note"), sql, rows, as_of, context),
            "sql": sql, "rows": rows, "note": p.get("note"), "error": None}
