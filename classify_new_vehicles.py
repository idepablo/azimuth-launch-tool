"""Classify vehicles that are new to the seed, where the data makes it clear.

Runs in the daily refresh after new launches land in bronze and before the
dbt build. For every launch vehicle (configuration) in bronze that has no row
in seeds/vehicle_classification.csv, it tries two rules in order:

1. Family. If the vehicle belongs to a family (from the source, or from
   seeds/family_overrides.csv) whose already-classified members all have the
   same class, the new vehicle gets that class. A new version of a known
   rocket, such as Vulcan VC6L next to VC2S and VC4S, is classified this way.
2. Launches. Otherwise its launches decide: a launch from the Moon makes it
   non_earth_launch; any launch with a known orbit other than suborbital
   makes it orbital (single suborbital flights of an orbital vehicle are
   already handled per launch in stg_launches).

Suborbital is never decided automatically: a new rocket's first flights are
often suborbital tests (Starship, Soyuz-5), and test vehicles sit in orbital
families. A vehicle with only suborbital flights waits, out of the orbital
figures as it should be, and is classified the day it flies to orbit. The
same applies when nothing decides (no family match, no known orbit yet): the
vehicle is left out and the existing warning names it.

Tested by hiding each hand-classified vehicle in turn and classifying it
with these rules: see docs/scope.md. Every row
added says which rule classified it, so it can be reviewed later.

Rows are appended to the seed file; the workflow commits the file back to
main after the build and tests pass.
"""
import csv
import os
import re
from datetime import datetime, timezone

import pandas as pd

import bronze_local

SEED = os.path.join("azimuth_dbt", "seeds", "vehicle_classification.csv")
FAMILY_OVERRIDES = os.path.join("azimuth_dbt", "seeds", "family_overrides.csv")
# names that mark a test or prototype vehicle, which may not share its family's class
TEST_VEHICLE = re.compile(r"prototype|\btlv\b|\btest|pp$", re.IGNORECASE)


def annotate(level, message):
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::{level} title=New vehicles::{message}")
    else:
        print(message)


def families_by_config():
    """config_id -> set of family names (source families plus overrides)."""
    fam = bronze_local.read("launcher_families")
    out = {}
    for config_id, family, parent in zip(fam["config_id"], fam["family_name"],
                                         fam["parent_family_name"]):
        names = out.setdefault(str(config_id), set())
        for name in (family, parent):
            if isinstance(name, str) and name:
                names.add(name)
    overrides = pd.read_csv(FAMILY_OVERRIDES, dtype=str)
    for config_id, family in zip(overrides["config_id"], overrides["family_name"]):
        out.setdefault(str(config_id), set()).add(family)
    return out


def known_orbits(launches):
    orbits = launches["orbit_name"].dropna()
    return orbits[~orbits.isin(["Unknown", ""])]


def by_family(config_id, launches, families, seed_class):
    """The class shared by every classified member of the vehicle's families.

    Only orbital and non_earth_launch are taken from the family, and not for a
    vehicle whose flights so far are all suborbital: test vehicles (KSLV 2 TLV,
    Starship Prototype, Angara-1.2pp) sit in orbital families.
    """
    mine = families.get(config_id, set())
    orbits = known_orbits(launches)
    if TEST_VEHICLE.search(launches["config_name"].iloc[0]):
        return None, None
    if not mine or (len(orbits) and (orbits == "Suborbital").all()):
        return None, None
    classes = {seed_class[c] for c, names in families.items()
               if c in seed_class and names & mine}
    if len(classes) == 1 and classes <= {"orbital", "non_earth_launch"}:
        return classes.pop(), "family " + " / ".join(sorted(mine))
    return None, None


def by_launches(launches):
    """Never decides suborbital: a new rocket's first flights are often
    suborbital tests (Starship, Soyuz-5). It waits instead, staying out of the
    orbital figures, and is classified once it flies to orbit."""
    if (launches["celestial_body"].fillna("") == "Moon").any():
        return "non_earth_launch", "launched from the Moon"
    orbits = known_orbits(launches)
    if len(orbits) and (orbits != "Suborbital").any():
        return "orbital", "launch orbit " + ", ".join(sorted(set(orbits[orbits != "Suborbital"])))
    return None, None


def main():
    seed = pd.read_csv(SEED, dtype=str)
    seed_class = dict(zip(seed["config_id"], seed["vehicle_class"]))

    launches = bronze_local.read("launches")
    new = launches[~launches["config_id"].isin(seed_class)]
    if new.empty:
        print("Every launched vehicle is already classified.")
        return

    configs = bronze_local.read("launcher_configurations").set_index("config_id")
    families = families_by_config()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    added, left = [], []
    for config_id, group in new.groupby("config_id"):
        name = group["config_name"].iloc[0]
        vehicle_class, reason = by_family(config_id, group, families, seed_class)
        if vehicle_class is None:
            vehicle_class, reason = by_launches(group)
        if vehicle_class is None:
            left.append(name)
            continue
        ref = configs.loc[config_id] if config_id in configs.index else None
        first = group["net"].min()[:10]
        added.append({
            "config_id": config_id,
            "config_name": name,
            "launch_count": str(len(group)),
            "leo_capacity": "" if ref is None or pd.isna(ref["leo_capacity"]) else ref["leo_capacity"],
            "apogee": "" if ref is None or pd.isna(ref["apogee"]) else ref["apogee"],
            "is_placeholder": "False" if ref is None or pd.isna(ref["is_placeholder"]) else ref["is_placeholder"],
            "vehicle_class": vehicle_class,
            "notes": f"Auto-classified {today} by the daily refresh ({reason}). "
                     f"First launch in the data {first}.",
        })

    if added:
        with open(SEED, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(seed.columns), lineterminator="\n")
            writer.writerows(added)
        annotate("notice", "Classified automatically: " + "; ".join(
            f"{r['config_name']} as {r['vehicle_class']} ({r['notes'].split('(')[1].split(')')[0]})"
            for r in added))
    if left:
        annotate("warning", "Not enough data yet to classify, left out until it is: "
                 + ", ".join(left))


if __name__ == "__main__":
    main()
