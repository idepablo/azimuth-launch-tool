# AZIMUTH scope document

*Last updated: 11 August 2026*

This document records the decisions made in Phase 0, before any transformation was written. The
purpose is to state what the data can honestly support, and to make the judgment calls explicit
so they can be challenged rather than hand-waved.

Source: [Launch Library 2](https://thespacedevs.com/llapi) (The Space Devs), version 2.3.0.

---

## Grain

**One row per launch attempt**, keyed on the launch UUID supplied by the API (`id`).

The UUID is stable and globally unique, so it is used as the merge key throughout the pipeline. It
is a string, not an integer.

A launch attempt is the unit because it is what the source records and what the analysis is about.
A scrubbed countdown that never lifts off is not a separate row; the API updates the existing
record rather than creating a new one.

---

## Scope: which launches are in

AZIMUTH models the **orbital** launch market. Scope is drawn on `mission.orbit`.

- **Suborbital** (orbit id 15) is excluded. New Shepard, HASTE, and sounding-rocket style flights
  are not competing in the market this platform models.
- **Unknown** (orbit id 25) is kept as its own third category. It is not silently folded into
  orbital. Roughly 5% of the recent sample falls here, which is small enough not to distort
  headline numbers but large enough that assuming it away would be dishonest.
- Everything else in the orbit reference list is treated as orbital, including deep-space and
  planetary trajectories, since reaching them requires an orbital-class vehicle.

An earlier hypothesis, that `orbital_launch_attempt_count` being null could serve as a suborbital
flag, was tested and rejected. Of four null records in the sample, three were suborbital and one
(a Soyuz-5 demo flight) was not. A filter that is right 75% of the time fails silently, so it is
not used.

---

## Vehicle identity

Vehicle identity is **`rocket.configuration.id`**, not `rocket.id`.

A "rocket" in the API is an instance of a flight. The configuration is the vehicle type. In one
sampled record, `rocket.id` was 8665 while `rocket.configuration.id` was 137 (New Shepard). The
maturation and reliability analysis compares vehicle types, so the configuration is the unit.

Launcher configurations are loaded separately rather than being extracted from launch records.
Fetching launches in detailed mode returns the full configuration object nested six levels deep,
including manufacturer descriptions, images, and licence metadata. That is unusable at bulk. A
separate load against `/launcher_configurations/` is both lighter and correct, since configurations
change rarely and should not be re-fetched with every launch.

---

## Outcomes and censoring

The API defines nine launch statuses. They are not one concept. They split into outcomes and
schedule states:

**Outcomes (the launch has happened and the result is known):**

| id | Name |
|----|------|
| 3 | Launch Successful |
| 4 | Launch Failure |
| 7 | Launch was a Partial Failure |
| 9 | Payload Deployed |

**Schedule states (the outcome is not yet known):**

| id | Name |
|----|------|
| 1 | Go for Launch |
| 2 | To Be Determined |
| 5 | On Hold |
| 6 | Launch in Flight |
| 8 | To Be Confirmed |

This split is the **censoring boundary**. Any reliability or maturation analysis treats records in
the second group as censored, not as absent. A vehicle still in development has not had its event
yet, which is exactly the situation survival analysis exists to handle. Excluding them instead
would bias reliability estimates.

A derived flag (`is_outcome_known`) carries this split into the silver layer so downstream logic
does not have to re-derive it from status ids.

### Statuses 3 and 9 are both successes

Status 3 means the vehicle inserted its payload into the target orbit. Status 9 means payload
deployment was confirmed. Status 3 is a judgment about the launch vehicle; status 9 is a judgment
about the payload. Both describe a launch that worked.

Anyone writing `WHERE status_id = 3` to count successes will silently drop every status 9 record.
Success is defined as `status_id IN (3, 9)`.

### Partial failures

Status 7 is ambiguous by design. Its own definition covers two different situations: the vehicle
reached orbit but did not deliver its payload to the targeted orbit, **or** an exceptional event
made the mission impossible to consider a success. The API provides no field distinguishing them.

This matters because AZIMUTH's central claim is about vehicle reliability. A vehicle that put a
payload in the wrong orbit failed. A vehicle that flew correctly while something else went wrong
did not. Both are status 7.

**Decision: partial failure is reported as its own outcome category, not collapsed into success or
failure.**

The alternatives were considered and rejected. Counting them as failures understates reliability
for vehicles that performed correctly. Counting them as successes is hard to defend to anyone who
knows the domain. Reporting three categories is more work in every view, but it is the only option
that does not assert something the source data cannot support.

Status 4 has a milder version of the same problem, covering both "did not reach orbit" and
"payloads failed to separate." It is left as a single failure category, but the ambiguity is noted.

---

## Dates

**`net` is the launch date.** It stands for "no earlier than" and represents T-0. For a launch that
has happened it is the actual launch time; for an upcoming launch it is the current estimate.

`window_start` and `window_end` describe the launch window, not the launch. `last_updated` is
metadata about the record, not about the launch, and is used only as the merge guard (a stored row
is updated only when the incoming `last_updated` is newer).

### `net_precision` is carried on the fact table

The API records how precise each `net` value is. For recent launches it is "Second." For historical
records it may be "Month" or "Year."

A 1961 launch with a precision of "Year" cannot honestly be joined to a specific calendar date. Any
monthly or daily aggregation that includes such records is wrong in a way nothing will flag. So
`net_precision` is carried onto the fact table, and time-series views must decide explicitly
whether to include coarse records rather than inheriting them by accident.

---

## Not modeled in v1

Two relationships in the source are genuinely many-to-many:

- **`program`** is a list on the launch. A launch can belong to zero, one, or several programs
  (Artemis, Commercial Crew, and so on).
- **`families`** is a list on the launcher configuration. A configuration can belong to more than
  one family.

Both would need bridge tables. They are parked for a later version rather than being flattened into
a single value, which would misrepresent the source.

A related open question, deliberately not answered in v1: whether the maturation analysis should
group by configuration or by family. Falcon 9 v1.0, v1.1, and Block 5 are separate configurations
of one family, and the reliability picture looks materially different depending on which unit is
chosen. v1 uses the configuration.

---

## Bronze typing

Every column in bronze is stored as a string.

Casting in bronze means one malformed value fails the load and the row is lost. Casting in silver
means a bad value surfaces as a failed test with the record still available for inspection. Bronze
holds data as it arrived.

---

## Data integrity check

Run against the 100 most recent launches:

- 0 records missing a mission
- 0 records missing an orbit
- 91 orbital, 5 Unknown, 4 suborbital

Orbit distribution: 60 Low Earth, 11 Sun-Synchronous, 10 Polar, 7 Geostationary Transfer, 2
Elliptical, 1 Medium Earth.

Every record had both a mission and an orbit, so `mission.orbit` is a clean filter on this sample
with no missing-data judgment required.

---

## Known limitations

**The integrity check is a best case.** It ran on the 100 most recent launches, taken from the
development mirror. Historical records from the 1960s and 70s are considerably more likely to have
gaps. Re-running this check against the full 7,598-record history is the first task of Phase 2, and
it may change the conclusions above.

**Row counts rule out duplicates, not gaps.** The API paginates by offset. If records are inserted
into the dataset while a five-hour backfill is running, offsets shift forward and a record can be
pushed past a boundary already read. It would be skipped, and the row count would not reveal it.
The backfill returned 7,598 records where the API had reported 7,589 earlier the same day; the
likely explanation is launches confirmed during the run, but this has not been verified. A
completeness comparison against the source count is on the data quality list.

**The development mirror is not representative.** It holds 354 records where production holds
7,589. It is suitable for testing code and unsuitable for any quantitative conclusion. Any figure
in this document sourced from the mirror is marked as such.

**Two candidate measures are unconfirmed.** Payload mass and booster reuse are both desirable on
the fact table but neither is confirmed obtainable. `payloads` returned an empty list in the
sampled record. Booster reuse lives inside `launcher_stage`, which is a list, so a single boolean
at launch grain would be a collapse decision rather than a field to read. Neither is promised until
verified.

---

## Change log

| Date | Change |
|------|--------|
| 2026-08-11 | Initial version, covering Phase 0 decisions and Phase 1 findings. |
