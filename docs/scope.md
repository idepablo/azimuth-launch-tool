# AZIMUTH scope document

*Last updated: 20 August 2026*

This document records the scoping decisions for AZIMUTH, made before transformation code and
revised as the data disproves them. The purpose is to state what the data can honestly support,
and to make the judgment calls explicit so they can be challenged rather than hand-waved.

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

AZIMUTH models the **Earth orbital launch market**. Scope is determined by the **vehicle**, not by
the mission's recorded orbit.

This is a revision. The original decision drew scope on `mission.orbit`, based on an audit of the
100 most recent launches in which every record had an orbit. Against the full 7,598-record
history, that assumption failed: 530 launches (7%) have no orbit recorded, and the missingness is
not random. It concentrates in Chinese, Russian, and classified military missions, peaking at 28%
of all launches in the 2010s and reaching 55% of CASC's launches in that decade. Filtering on the
orbit field would silently remove roughly half of China's 2010s launch activity, which is exactly
the market share the platform exists to measure. The field reflects what launching organizations
publish, not what they flew.

The scoping rule is therefore:

1. Every launch is classified by its **vehicle configuration**, using a curated seed table (see
   below). A Long March with no published orbit is still an orbital launch, because Long March is
   an orbital-class vehicle.
2. For the small set of configurations that genuinely flew both regimes, the **per-launch orbit
   field overrides** the vehicle class where it is explicitly "Suborbital." Scout X-1 flew five
   orbital attempts and one suborbital probe under one configuration; Electron may carry HASTE's
   suborbital flights; the earliest Mercury-Atlas flights were suborbital. The override handles
   these without weakening the vehicle-level default.
3. `mission.orbit` is retained for **orbit-class breakdown views** (LEO vs GTO vs SSO), with its
   coverage gap disclosed on those views rather than hidden.

### The vehicle classification seed

The classification lives in `seeds/vehicle_classification.csv`: one row per launcher
configuration appearing in the launch data (485 configurations), with a `vehicle_class` and a
`notes` column.

Automated classification was attempted first and rejected on the evidence. The API's
`leo_capacity` field is null for 183 of 532 configurations, and zero cannot be trusted either:
GSLV Mk II, Long March 3A, and Zenit all carry `leo_capacity = 0`, where zero evidently means
"not entered" for GTO-focused vehicles rather than "cannot reach orbit." The `apogee` field is
equally inconsistent (orbital Ariane 5 ECA records its GTO apogee; sibling configurations record
nothing).

The seed was built with AI assistance and human review: an initial classification was generated
for all 485 rows, 25 uncertain rows were flagged, and every flagged row was verified against the
actual launch records in bronze (plus one web check). Six of the 25 flags changed on review,
including two entire categories nobody anticipated. The `notes` column carries the verification
trail for every row that required judgment.

Classes:

| Class | Configs | Launches | Meaning |
|---|---|---|---|
| `orbital` | 456 | 7,399 | Orbital-class launch vehicle |
| `suborbital` | 26 | 188 | Suborbital by design: tourism, sounding rockets, rocket planes, abort and reentry tests |
| `non_earth_launch` | 2 | 5 | Launches not from Earth (see below) |
| `not_a_launch_vehicle` | 1 | 6 | Records that are not launch vehicles (Apollo Lunar Module) |

### Non-Earth launches

The source tracks launches from other celestial bodies. Five records in the dataset are **ascent
stages lifting off from the lunar surface**: Luna 16, 20, and 24, and Chang'e 5 and 6, all sample
return missions. Their dates are the lunar liftoffs, not the Earth launches (which appear
separately under their actual launch vehicles).

These are excluded from the Earth launch market via the seed. The principled long-term filter is
the launch pad's celestial body, which the API provides but the bronze flatten does not yet carry;
adding it requires re-flattening from the raw archive, not re-fetching.

---

## Vehicle identity

Vehicle identity is **`rocket.configuration.id`**, not `rocket.id`.

A "rocket" in the API is an instance of a flight. The configuration is the vehicle type. The
maturation and reliability analysis compares vehicle types, so the configuration is the unit.

Two data quality caveats, found during Phase 2:

- **Duplicate configuration records exist for the same vehicle.** "Soyuz U" and "Soyuz-U" are two
  distinct records (714 and 71 launches); "Zenit" appears twice. Joins are on configuration id,
  never on name, and name normalization is a silver-layer task.
- Configuration detail must be fetched with `mode=detailed`; the list-mode response strips every
  capacity and statistics field (verified: 532 of 532 null in list mode).

Launcher configurations are loaded separately rather than being extracted from launch records,
because launch records in detailed mode nest the full configuration object six levels deep,
including manufacturer biographies and image licences.

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

## Data integrity: full-history findings

The original audit ran against the 100 most recent launches on the development mirror and found
zero missing missions and zero missing orbits. That document flagged the result as a best case.
The full-history check (Phase 2, against all 7,598 production records) confirmed the warning:

- **517 launches have no mission record; 530 have no orbit** — about 7% of the dataset. Nearly
  every missing orbit is missing because the whole mission record is absent.
- Explicit orbit "Unknown" is a separate, rare case: 16 records, all in the 2020s.
- The missingness is **not concentrated in early history**. By decade, the missing-orbit rate runs
  0% (1950s), 5.8%, 1.9%, 3.2%, 7.7%, 8.9% — then spikes to **28.1% in the 2010s** before
  collapsing to 0.5% in the 2020s.
- The 2010s spike is explained by **provider transparency, not era**: 55% of CASC's 2010s launches
  lack an orbit, 61% of ILS's, 49% of Khrunichev's, and 100% of ISC Kosmotras's, against 3% for
  Arianespace. ULA's 15% likely reflects classified NRO payloads. The gap tracks what launching
  organizations publish.

This finding is what forced the scoping revision above: because the missingness correlates with
provider, any metric filtered on the orbit field is biased against exactly the providers whose
share the platform measures.

---

## Known limitations

**Row counts rule out duplicates, not gaps.** The API paginates by offset. If records are inserted
into the dataset while a five-hour backfill is running, offsets shift forward and a record can be
pushed past a boundary already read. It would be skipped, and the row count would not reveal it.
The backfill returned 7,598 records where the API had reported 7,589 earlier the same day; the
likely explanation is launches confirmed during the run, but this has not been verified. A
completeness comparison against the source count is on the data quality list.

**The development mirror is not representative.** It holds 354 records where production holds
7,598. It is suitable for testing code and unsuitable for any quantitative conclusion.

**Source data errors exist and are recorded, not silently corrected.** Example: the Scout X-2
flight P-21A is recorded with orbit "Low Earth Orbit," but the P-21/P-21A missions were
historically suborbital ionosphere probes. The record is noted in the classification seed rather
than altered.

**Duplicate configuration records** (Soyuz U / Soyuz-U, two Zenit records) mean per-vehicle
statistics computed by name are wrong. All joins are on configuration id; name normalization is a
silver task.

**The bronze flatten does not yet carry the pad's celestial body**, which is the principled filter
for non-Earth launches. The seed handles the five known cases; adding the column is a re-flatten
from the immutable raw archive, not a re-fetch.

**Two candidate measures remain unconfirmed.** Payload mass and booster reuse are both desirable on
the fact table but neither is confirmed obtainable. `payloads` returned an empty list in the
sampled record. Booster reuse lives inside `launcher_stage`, which is a list, so a single boolean
at launch grain would be a collapse decision rather than a field to read. Neither is promised until
verified.

---

## Change log

| Date | Change |
|------|--------|
| 2026-08-11 | Initial version, covering Phase 0 decisions and Phase 1 findings. |
| 2026-08-20 | Scoping revised after full-history audit: orbital scope moved from `mission.orbit` to the vehicle classification seed with per-launch orbit override; non-Earth launches identified and excluded; integrity section replaced with full-history findings (7% missing orbits, provider-transparency pattern); duplicate configs and the P-21A source error recorded. |
