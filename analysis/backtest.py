"""Backtest the Scenario Simulator against real history.

For each cutoff date, the data is frozen: the benchmark (success rate by
flight band and era) is rebuilt from flights before the cutoff only. The
simulator's model is then run for every vehicle that was active at the
cutoff, and its predictions are compared with what those vehicles actually
did afterwards. Nothing after a cutoff is used to make a prediction.

Three checks:
  1. Per-flight probability. Is a flight predicted at 85% successful about
     85% of the time? Scored with the Brier score against two baselines: the
     vehicle's own record so far, and the market's overall success rate.
  2. "Next five flights all succeed". Predicted probability vs what happened.
  3. Flights until the lower bound reaches 80%. Does the real crossing land
     inside the simulator's 80% range about 80% of the time?

Dates are not tested: they depend on the cadence the user types in.

Usage:
    python analysis/backtest.py <snapshot_dir> <output_json>
The snapshot is the parquet export the app reads (export_snapshot.py).
"""
import json
import sys

import numpy as np
import pandas as pd

CUTOFFS = ["2000-01-01", "2005-01-01", "2010-01-01", "2015-01-01", "2020-01-01"]
BAND_STARTS = [1, 2, 3, 4, 5, 6, 11, 21, 51, 101]
MIN_BAND_FLIGHTS = 20     # same fallback rule as the app
RUNS = 2000
HORIZON = 300
Z = 1.96
MAX_SCORED_FLIGHTS = 30   # per vehicle, so long-lived vehicles do not dominate
ACTIVE_DAYS = 730
TARGET = 0.8
CALIBRATION_BINS = [0.0, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0001]


def band_index(n):
    return max(i for i, start in enumerate(BAND_STARTS) if n >= start)


def era_of(first_flight):
    if first_flight.year < 1980:
        return "1957-1979"
    if first_flight.year < 2000:
        return "1980-1999"
    return "2000-present"


def wilson_lower(s, n):
    s, n = np.asarray(s, float), np.asarray(n, float)
    p = s / n
    return (p + Z**2 / (2 * n) - Z * np.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2))) / (1 + Z**2 / n)


def benchmark(history):
    """Success counts by (era, band) and pooled across eras, from history only."""
    h = history.assign(band=history["flight_number"].map(band_index),
                       ok=(history["outcome"] == "success").astype(int))
    by_era = h.groupby(["era", "band"])["ok"].agg(["sum", "count"])
    pooled = h.groupby("band")["ok"].agg(["sum", "count"])
    return by_era, pooled


def band_counts(era, by_era, pooled):
    """(successes, attempts) per band for one era, with the app's fallback rule."""
    out = []
    for b in range(len(BAND_STARTS)):
        if (era, b) in by_era.index and by_era.loc[(era, b), "count"] >= MIN_BAND_FLIGHTS:
            row = by_era.loc[(era, b)]
        elif b in pooled.index:
            row = pooled.loc[b]
        else:
            row = pd.Series({"sum": 1, "count": 2})   # no history at all for this band
        out.append((int(row["sum"]), int(row["count"])))
    return out


def simulate(s0, n0, counts, rng):
    """The app's simulator: per-run Beta draw of band rates, then Bernoulli flights."""
    succ = np.array([c[0] for c in counts]) + 0.5
    fail = np.array([c[1] - c[0] for c in counts]) + 0.5
    rates = rng.beta(succ, fail, size=(RUNS, len(counts)))
    bands = np.array([band_index(n) for n in range(n0 + 1, n0 + HORIZON + 1)])
    wins = rng.random((RUNS, HORIZON)) < rates[:, bands]
    cum_s = s0 + np.cumsum(wins, axis=1)
    n = n0 + np.arange(1, HORIZON + 1)
    lower = wilson_lower(cum_s, n)
    return wins, lower


def brier(pred, actual):
    pred, actual = np.asarray(pred), np.asarray(actual)
    return float(np.mean((pred - actual) ** 2))


def calibration(pred, actual):
    df = pd.DataFrame({"pred": pred, "actual": actual})
    df["bin"] = pd.cut(df["pred"], CALIBRATION_BINS, right=False)
    g = df.groupby("bin", observed=True).agg(predicted=("pred", "mean"),
                                             observed=("actual", "mean"),
                                             flights=("actual", "size")).reset_index()
    g["bin"] = g["bin"].astype(str)
    return g.to_dict("records")


def main(snapshot_dir, out_path):
    m = pd.read_parquet(f"{snapshot_dir}/mart_maturation.parquet")
    m = m[m["lens"] == "family"].copy()
    m["launched_at"] = pd.to_datetime(m["launched_at"], utc=True).dt.tz_localize(None)
    m = m.sort_values(["unit_key", "flight_number"])
    rng = np.random.default_rng(42)

    per_flight, next_five, crossing = [], [], []

    for cutoff_str in CUTOFFS:
        cutoff = pd.Timestamp(cutoff_str)
        history = m[m["launched_at"] < cutoff].copy()
        # eras as they would have been known at the cutoff
        first = history.groupby("unit_key")["launched_at"].min()
        history["era"] = history["unit_key"].map(first).map(era_of)
        by_era, pooled = benchmark(history)
        market_rate = (history["outcome"] == "success").mean()

        last = history.groupby("unit_key")["launched_at"].max()
        floor = np.datetime64(cutoff - pd.Timedelta(days=ACTIVE_DAYS), "us")
        active = last.index[last.to_numpy() >= floor]

        for unit in active:
            past = history[history["unit_key"] == unit]
            future = m[(m["unit_key"] == unit) & (m["launched_at"] >= cutoff)]
            if future.empty:
                continue
            n0 = len(past)
            s0 = int((past["outcome"] == "success").sum())
            era = era_of(first[unit])
            counts = band_counts(era, by_era, pooled)
            outcomes = (future["outcome"] == "success").astype(int).to_numpy()

            # 1. per-flight probability vs two baselines
            own = (s0 + 1) / (n0 + 2)
            for k, ok in enumerate(outcomes[:MAX_SCORED_FLIGHTS], start=1):
                s, c = counts[band_index(n0 + k)]
                per_flight.append({"cutoff": cutoff_str, "unit": unit, "flight": n0 + k,
                                   "model": s / c, "own_record": own,
                                   "market": market_rate, "actual": int(ok)})

            wins, lower = simulate(s0, n0, counts, rng)

            # 2. next five flights
            if len(outcomes) >= 5:
                next_five.append({"cutoff": cutoff_str, "unit": unit,
                                  "predicted": float(wins[:, :5].all(axis=1).mean()),
                                  "actual": int(outcomes[:5].all())})

            # 3. flights until the lower bound reaches 80%
            if wilson_lower(s0, n0) < TARGET:
                reached = lower >= TARGET
                hit = np.where(reached.any(axis=1), reached.argmax(axis=1) + 1, np.inf)
                p10, p50, p90 = np.percentile(hit, [10, 50, 90])
                real = wilson_lower(s0 + np.cumsum(outcomes), n0 + np.arange(1, len(outcomes) + 1))
                crossed = np.nonzero(real >= TARGET)[0]
                actual = int(crossed[0] + 1) if len(crossed) else None
                observed = len(outcomes)
                if actual is not None:
                    status = "inside" if p10 <= actual <= p90 else (
                        "earlier" if actual < p10 else "later")
                elif p90 <= observed:
                    status = "later"       # 90% of futures would have crossed by now
                else:
                    status = "undetermined"  # not crossed yet, still inside the range
                crossing.append({"cutoff": cutoff_str, "unit": unit, "flights_at_cutoff": n0,
                                 "p10": p10, "p50": p50, "p90": p90, "actual": actual,
                                 "observed_after": observed, "status": status})

    pf = pd.DataFrame(per_flight)
    nf = pd.DataFrame(next_five)
    cr = pd.DataFrame(crossing)
    decided = cr[cr["status"] != "undetermined"]

    # Does the vehicle's own record add anything? Blend it with the benchmark
    # at increasing weights; k is how many flights the benchmark is worth.
    n0 = pf.groupby(["cutoff", "unit"])["flight"].transform("min") - 1
    s0 = (pf["own_record"] * (n0 + 2) - 1).round()
    blend = {str(k): brier((s0 + k * pf["model"]) / (n0 + k), pf["actual"])
             for k in [5, 10, 20, 40, 80]}

    results = {
        "cutoffs": CUTOFFS,
        "per_flight": {
            "flights_scored": len(pf),
            "vehicles": int(pf.groupby(["cutoff", "unit"]).ngroups),
            "actual_success_rate": float(pf["actual"].mean()),
            "mean_predicted": float(pf["model"].mean()),
            "brier": {"model": brier(pf["model"], pf["actual"]),
                      "own_record": brier(pf["own_record"], pf["actual"]),
                      "market_rate": brier(pf["market"], pf["actual"])},
            "brier_blend_with_own_record": blend,
            "calibration": calibration(pf["model"], pf["actual"]),
            "by_cutoff": [
                {"cutoff": c, "flights": len(g), "predicted": float(g["model"].mean()),
                 "observed": float(g["actual"].mean())}
                for c, g in pf.groupby("cutoff")],
        },
        "next_five": {
            "vehicles": len(nf),
            "mean_predicted": float(nf["predicted"].mean()),
            "observed": float(nf["actual"].mean()),
            "brier": brier(nf["predicted"], nf["actual"]),
            "brier_constant": brier(np.full(len(nf), nf["actual"].mean()), nf["actual"]),
            "calibration": calibration(nf["predicted"], nf["actual"]),
        },
        "crossing_80": {
            "vehicles": len(cr),
            "decided": len(decided),
            "inside": int((decided["status"] == "inside").sum()),
            "earlier": int((decided["status"] == "earlier").sum()),
            "later": int((decided["status"] == "later").sum()),
            "undetermined": int((cr["status"] == "undetermined").sum()),
            "coverage": float((decided["status"] == "inside").mean()) if len(decided) else None,
        },
    }

    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=float)
    pf.to_csv(out_path.replace(".json", "_flights.csv"), index=False)
    cr.to_csv(out_path.replace(".json", "_crossing.csv"), index=False)

    r = results
    print(f"Per-flight: {r['per_flight']['flights_scored']} flights, "
          f"{r['per_flight']['vehicles']} vehicle-cutoffs")
    print(f"  predicted {r['per_flight']['mean_predicted']:.3f}, "
          f"observed {r['per_flight']['actual_success_rate']:.3f}")
    print(f"  Brier: model {r['per_flight']['brier']['model']:.4f}, "
          f"own record {r['per_flight']['brier']['own_record']:.4f}, "
          f"market rate {r['per_flight']['brier']['market_rate']:.4f}")
    for row in r["per_flight"]["calibration"]:
        print(f"    {row['bin']:>14}: predicted {row['predicted']:.3f}, "
              f"observed {row['observed']:.3f} ({row['flights']} flights)")
    for row in r["per_flight"]["by_cutoff"]:
        print(f"    {row['cutoff']}: predicted {row['predicted']:.3f}, observed {row['observed']:.3f} "
              f"({row['flights']})")
    print(f"Next five: {r['next_five']['vehicles']} vehicles, predicted "
          f"{r['next_five']['mean_predicted']:.3f}, observed {r['next_five']['observed']:.3f}, "
          f"Brier {r['next_five']['brier']:.4f} (constant {r['next_five']['brier_constant']:.4f})")
    for row in r["next_five"]["calibration"]:
        print(f"    {row['bin']:>14}: predicted {row['predicted']:.3f}, "
              f"observed {row['observed']:.3f} ({row['flights']} vehicles)")
    c = r["crossing_80"]
    print(f"Crossing 80%: {c['vehicles']} vehicles, {c['decided']} decided: "
          f"{c['inside']} inside, {c['earlier']} earlier, {c['later']} later, "
          f"{c['undetermined']} undetermined; coverage {c['coverage']}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
