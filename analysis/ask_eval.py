"""Exam for Ask AZIMUTH: how often does it get the answer right?

Each in-scope question has a reference query written by hand. The reference
runs on the same snapshot, so the expected answer stays current as the data
changes. A question passes if every value the reference returns appears in
the model's result (numbers within 0.5%, fractions also accepted as
percentages, text case-insensitively). Out-of-scope questions pass if the
model declines them.

Usage (needs ANTHROPIC_API_KEY):
    python analysis/ask_eval.py <snapshot_dir> <output_json>
"""
import json
import math
import os
import sys
from datetime import datetime, timezone

QUESTIONS = [
    # --- market -------------------------------------------------------------------
    ("How many orbital launch attempts were there in 2025?",
     "select count(*) from launches where scope_class='orbital' and is_outcome_known and launch_year=2025"),
    ("Which provider launched the most in 2025?",
     "select provider from yearly_share where launch_year=2025 order by attempts desc limit 1"),
    ("What was SpaceX's share of orbital attempts in 2025?",
     "select share_of_attempts from yearly_share where launch_year=2025 and provider='SpaceX'"),
    ("How many orbital attempts did Rocket Lab make in 2025?",
     "select attempts from yearly_share where launch_year=2025 and provider='Rocket Lab'"),
    ("What was the overall orbital success rate in 2025?",
     "select sum(case when outcome='success' then 1 else 0 end)::double / count(*) from launches "
     "where scope_class='orbital' and is_outcome_known and launch_year=2025"),
    ("How many orbital launches did CASC make in 2024?",
     "select attempts from yearly_share where launch_year=2024 and provider='CASC'"),
    ("¿Cuántos lanzamientos orbitales hubo en 2020?",
     "select count(*) from launches where scope_class='orbital' and is_outcome_known and launch_year=2020"),
    ("¿Qué proveedor tuvo más lanzamientos orbitales en 2010?",
     "select provider from yearly_share where launch_year=2010 order by attempts desc limit 1"),
    ("In which year did SpaceX first make more than 100 orbital launch attempts?",
     "select min(launch_year) from yearly_share where provider='SpaceX' and attempts > 100"),
    ("How many providers made at least one orbital attempt in 2025?",
     "select count(*) from yearly_share where launch_year=2025 and attempts > 0"),
    ("How many orbital launch failures were there in 2023?",
     "select count(*) from launches where scope_class='orbital' and outcome='failure' and launch_year=2023"),
    ("Which year had the most orbital launch attempts?",
     "select launch_year from launches where scope_class='orbital' and is_outcome_known "
     "group by 1 order by count(*) desc limit 1"),
    ("How many orbital attempts did Blue Origin make in 2025?",
     "select attempts from yearly_share where launch_year=2025 and provider='Blue Origin'"),
    ("What was Arianespace's rank by orbital attempts in 2025?",
     "select rank_by_attempts from yearly_share where launch_year=2025 and provider='Arianespace'"),
    ("Which provider has had the most orbital launch failures in total?",
     "select provider from launches where scope_class='orbital' and outcome='failure' "
     "group by 1 order by count(*) desc limit 1"),
    ("How many orbital launch attempts were there in the 1960s?",
     "select count(*) from launches where scope_class='orbital' and is_outcome_known "
     "and launch_year between 1960 and 1969"),
    ("¿Cuántos lanzamientos orbitales hizo SpaceX en 2024?",
     "select attempts from yearly_share where launch_year=2024 and provider='SpaceX'"),
    # --- vehicles -------------------------------------------------------------------
    ("How many failures has Electron had?",
     "select failures from vehicles where lens='family' and vehicle='Electron'"),
    ("How many orbital flights has Falcon 9 flown?",
     "select flights from vehicles where lens='family' and vehicle='Falcon 9'"),
    ("What is Atlas V's success rate?",
     "select reliability from vehicles where lens='family' and vehicle='Atlas V'"),
    ("When was Ariane 6's first flight?",
     "select strftime(first_flight_at, '%Y-%m-%d') from vehicles where lens='family' and vehicle='Ariane 6'"),
    ("Which vehicle family has flown the most orbital flights?",
     "select vehicle from vehicles where lens='family' order by flights desc limit 1"),
    ("What is the 95% lower bound on Falcon 9's reliability?",
     "select reliability_lower_95 from vehicles where lens='family' and vehicle='Falcon 9'"),
    ("At which flight did Atlas V's lower bound first reach 90%?",
     "select flights_to_lb_90 from vehicles where lens='family' and vehicle='Atlas V'"),
    ("How many vehicle families are currently active?",
     "select count(*) from vehicles where lens='family' and is_active"),
    ("How many flights has the Long March 2 family made?",
     "select flights from vehicles where lens='family' and vehicle='Long March 2'"),
    ("¿Cuál es la tasa de éxito de Soyuz 2?",
     "select reliability from vehicles where lens='family' and vehicle='Soyuz 2'"),
    ("How many partial failures has Falcon 9 had?",
     "select partial_failures from vehicles where lens='family' and vehicle='Falcon 9'"),
    ("How many vehicle families made their first orbital flight in 2025?",
     "select count(*) from vehicles where lens='family' and year(first_flight_at)=2025"),
    # --- benchmarks -----------------------------------------------------------------
    ("Across all vehicles, what share of first flights succeed, counting by family?",
     "select success_rate from debut_curve where lens='family' and era='all' and flight_band='1'"),
    # --- out of scope: the model should decline -----------------------------------
    ("What does a Falcon 9 launch cost?", None),
    ("Why did the Amos-6 explosion happen?", None),
    ("Who is the CEO of Rocket Lab?", None),
    ("What will the weather be at Cape Canaveral tomorrow?", None),
    ("How much payload can Starship carry to orbit?", None),
    ("¿Cuál es la capital de Francia?", None),
]


def values(frame):
    return [v for row in frame.itertuples(index=False) for v in row]


def number(v):
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def matches(expected, got_cells):
    exp_num = number(expected)
    for cell in got_cells:
        if exp_num is not None:
            got = number(cell)
            if got is None:
                continue
            # rates are fractions (floats up to 1); accept them as percentages too
            is_rate = isinstance(expected, float) and 0 < abs(exp_num) <= 1
            for target in (exp_num, exp_num * 100) if is_rate else (exp_num,):
                if math.isclose(got, target, rel_tol=0.005, abs_tol=0.051 if target != exp_num else 1e-9):
                    return True
        elif str(expected).strip().lower() == str(cell).strip().lower():
            return True
        # a date matches a timestamp on the same day ("2024-07-09" vs "2024-07-09 13:00:00")
        elif len(str(expected)) == 10 and str(cell).startswith(str(expected)):
            return True
    return False


def main(snapshot_dir, out_path):
    os.environ["AZIMUTH_DATA_DIR"] = snapshot_dir
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
    import ask
    import data

    if not ask.api_key():
        print("No ANTHROPIC_API_KEY: skipping the Ask AZIMUTH exam.")
        return

    frames = ask.tables()
    as_of = data.manifest()["data_as_of"]
    results = []
    for question, reference in QUESTIONS:
        try:
            r = ask.ask(question, frames, as_of)
        except Exception as e:
            r = {"in_scope": True, "rows": None, "sql": None, "answer": None, "error": str(e)[:200]}
        if reference is None:
            passed = not r["in_scope"]
            expected = "decline"
        else:
            expected = values(ask.run_sql(reference, frames))
            got = values(r["rows"]) if r.get("rows") is not None else []
            passed = bool(r["in_scope"]) and r.get("error") is None and \
                all(matches(e, got) for e in expected)
        results.append({"question": question, "passed": passed, "expected": str(expected),
                        "in_scope": r["in_scope"], "sql": r.get("sql"), "answer": r.get("answer"),
                        "error": r.get("error")})
        print(("PASS " if passed else "FAIL ") + question)

    in_scope = [x for x in results if x["expected"] != "decline"]
    out_scope = [x for x in results if x["expected"] == "decline"]
    summary = {
        "model": ask.MODEL,
        "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_as_of": as_of,
        "questions": len(results),
        "passed": sum(x["passed"] for x in results),
        "in_scope_questions": len(in_scope),
        "in_scope_passed": sum(x["passed"] for x in in_scope),
        "out_of_scope_questions": len(out_scope),
        "out_of_scope_declined": sum(x["passed"] for x in out_scope),
        "results": results,
    }
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"{summary['passed']} of {summary['questions']} passed "
          f"({summary['in_scope_passed']}/{summary['in_scope_questions']} answerable, "
          f"{summary['out_of_scope_declined']}/{summary['out_of_scope_questions']} declined)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
