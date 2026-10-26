# AZIMUTH scope document

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
| `non_earth_launch` | 3 | 11 | Launches not from Earth (see below) |
| `not_a_launch_vehicle` | 0 | 0 | Kept as a legal class; currently empty (see Apollo LM below) |

These are vehicle classes. The per-launch `scope_class` starts from them and adds two overrides:
`suborbital` where the launch's orbit says so, and `pre_launch_failure` for reviewed records that
never left the pad (see Failures before launch).

### Non-Earth launches

The source tracks launches from other celestial bodies. Eleven records in the dataset are **ascent
stages lifting off from the lunar surface**: the six Apollo Lunar Module ascents, Luna 16, 20, and
24, and Chang'e 5 and 6. Their dates are the lunar liftoffs, not the Earth launches (which appear
separately under their actual launch vehicles).

The count was found twice, independently. The seed review identified the Luna and Chang'e records
(5 launches). Then the pad's celestial body, added to bronze by re-flattening the raw archive,
returned 11 Moon launches, exposing that Apollo LM had been imprecisely classified as
`not_a_launch_vehicle`: the LM ascent stage is a launch vehicle, it just launches from the Moon.
After reclassification, `vehicle_class = 'non_earth_launch'` and `celestial_body = 'Moon'` agree
exactly (11 = 11), and each can serve as a test of the other. All eleven are excluded from the
Earth launch market.

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

The API can record how precise each `net` value is. The original assumption was that historical
records would carry coarse values like "Month" or "Year." The full history says otherwise: of
7,598 launches, 6,180 have no precision recorded at all, 951 are "Second," 462 "Minute," 4 "Hour,"
and 1 "Day." No launch is marked "Month" or "Year."

So a null precision means "not recorded," not "coarse." `net_precision` still rides the fact table,
and the yearly marts are unaffected, but any future monthly or daily view should treat null
precision as unknown rather than assume a launch date is exact to the day.

---

## Vehicle families

Phase 0 parked configuration families as many-to-many. The Phase 4 recon of the raw configuration
snapshot showed it is not: it is a hierarchy. A configuration lists its family plus every ancestor
of that family. Falcon 9 Block 5 lists "Falcon" (the root) and "Falcon 9" (whose parent is
"Falcon"). Titan configurations go three levels deep (Titan, Titan III, Titan IIIB). Of the 485
configurations in launch data, every one with more than one family has exactly one root and one
most specific family, with a single exception (Minotaur-C, listed under two roots).

The family used for analysis is the most specific one. It is resolved in `stg_vehicle_families`:

1. A reviewed override from `seeds/family_overrides.csv`, used for three Soyuz records the source
   lists with no family (Soyuz-U, Soyuz FG, Soyuz-FG Fregat). This also settles the Soyuz U /
   Soyuz-U duplicate: the two records stay separate configurations but share a family.
2. Otherwise, the most specific family in the source hierarchy. When there are two candidates
   (Minotaur-C), the one with a parent wins, then the longer and more specific name.
3. Otherwise, the configuration's own name. 53 configurations, such as Space Shuttle and Electron,
   have no family in the source and are their own family.

The root family is kept as `family_root_name` for program-level grouping.

### Configuration or family: the maturation unit

The maturation analysis reports both lenses, with family as the default for the Maturation Race.

A configuration is a specific hardware version. A family is a program. The difference matters for
the question AZIMUTH answers. Falcon 9 Block 5 is nearly flawless from its first flight, but it
inherited 57 flights of learning from v1.0 through Block 4, including the failures. Plotted beside
a genuinely new vehicle, the configuration lens claims vehicles can be reliable immediately.

The data shows the size of the effect. Among vehicles with 20 or more orbital flights, the median
number of flights before the 95% lower bound on reliability reaches 80% is 16 under the
configuration lens and 36.5 under the family lens.

## Reliability definitions

- **Reliability** is strict: successes divided by orbital launch attempts. Partial failures are
  not successes, and are counted separately so views can show them.
- **The interval** is a 95% Wilson score interval. A vehicle with 3 successes in 3 flights has a
  point estimate of 100% that says almost nothing; the interval says so. A perfect record needs
  about 35 flights before the lower bound reaches 90%.
- **Flights to proven reliability** is the flight number at which the lower bound first reached
  80% (or 90%). It answers "how fast do vehicles earn reliability" in terms of evidence rather
  than a point estimate.
- The maturation analysis covers orbital launch attempts only (`scope_class = 'orbital'`), so
  suborbital flights of orbital-class vehicles (HASTE on Electron, early Starship test flights)
  are excluded from those vehicles' curves.

### Failures before launch

Two records are failures that happened before liftoff. The source records both as launch failures.
They are treated differently because only one of them is a failure of the launch vehicle.

| Record | Decision | Why |
|--------|----------|-----|
| Apollo 1 (Saturn IB, 1967) | Excluded | A cabin fire in the command module during a ground test. The Saturn IB was not the cause and never left the pad. Counting it charges the vehicle with a failure it did not have. |
| Amos-6 (Falcon 9, 2016) | Kept | The vehicle itself failed during a pre-launch static fire and destroyed the customer payload. That is a vehicle failure a customer would weigh, even though most launch logs do not count it as an attempt. |

Apollo 1 is excluded through a reviewed seed (`launch_exclusions`) that sets its `scope_class` to
`pre_launch_failure`. The row stays in `fct_launches`, traceable, and drops out of every orbital
mart. With it removed, the Saturn IB orbital record is 7 for 7 (its other two flights were
suborbital).

Keeping Amos-6 lowers the Falcon 9 family reliability from 99.6% to 99.4%. The application's
methodology page discloses this, so a reader who follows the stricter convention can see the
difference.

## Maturity-adjusted reliability

A vehicle's record only means something next to vehicles at the same stage of life. Three models
build on the Wilson intervals to make that comparison. All three are SQL, rebuilt and tested on
every deploy.

**The debut curve** (`mart_debut_curve`) is the success rate by flight band: flights 1 to 5 one at
a time, then 6-10, 11-20, 21-50, 51-100 and 101+. It is split by era of the vehicle's first flight
(1957-1979, 1980-1999, 2000-present), with `all` pooling every era. Under the family lens, a first
flight succeeds 57.8% of the time. Past flight 100 the rate is 97.0%. Under the configuration lens
the first flight succeeds 78.5% of the time, which is the inheritance effect again: a new
configuration of an existing family is not a new vehicle.

**The opening-run survival curve** (`mart_failure_free_survival`) is a Kaplan-Meier estimate of the
probability that a vehicle flies its first n flights without a failure (or partial failure). A
vehicle that has never failed is censored at its latest flight rather than counted as a vehicle
that will never fail. Under the family lens, 37.5% of vehicles get through their first five flights
clean and 19.4% through their first ten. The median opening run ends on flight 3. The 95% band uses
Greenwood's variance on the log-log scale. The model output was checked against the Python
`lifelines` library on all eight curves (two lenses, four eras) and agrees to within 0.00001.

**The benchmark** (columns on `mart_vehicle_reliability`) applies the debut curve flight by flight
to each vehicle. `expected_successes` is how many successes a typical vehicle of the same era would
have logged over the same flights; `reliability_vs_expected` is the gap in reliability points. The
benchmark is leave-one-out: the vehicle's own flights are removed from the rates it is compared
against, so Soyuz is not measured against itself. Where a vehicle is alone in its era for a band,
the all-era rate is used.

Two limits belong on the methodology page:

- **Survivorship.** Retirement is not random. Vehicles that fail often are cancelled, so late bands
  are made of survivors, and long-lived vehicles tend to sit above the benchmark (35 of the 51
  families with 20 or more flights do). The benchmark is fairest between vehicles with similar
  flight counts.
- **Why not a Bayesian prior.** An empirical-Bayes beta-binomial (one prior fitted across all
  vehicles, then each record shrunk toward it) was tested and not adopted. Vehicles are too
  different for a single prior to carry information: the fitted prior was worth between 1 and 9
  flights depending on the cutoff, so it barely moved any estimate the Wilson interval does not
  already describe. Where a vehicle is in its life explains far more than a common prior, which is
  what the debut curve captures.

## Data operations

After the one-time backfill, the data is kept current by a scheduled refresh (`refresh.yml`, daily
on GitHub Actions, also runnable by hand).

- **Incremental fetch.** `refresh.py` asks the production API only for past launches whose record
  changed since the newest `last_updated` in bronze, minus a one-day overlap. The merge is
  idempotent, so the overlap costs a few repeated rows and protects against records edited during
  the previous run. A launch that has just flown is covered too: its status update moves its
  `last_updated` forward.
- **Page-by-page merge.** Results are ordered by `last_updated` and each page is merged as soon as
  it arrives, with its own audit row. An interrupted run keeps what it loaded, and the next run's
  watermark resumes from there. Raw pages are archived in the bronze volume, so the raw archive
  stays the source of truth.
- **Same deploy path as code changes.** After the load, the refresh calls the same workflow a push
  to `main` runs: build and test in the isolated `ci` schema, then deploy to silver and gold only if
  every test passed.
- **Completeness.** Bronze's row count is compared with the API's count of past launches. Fewer in
  bronze fails the run (the fix is a full backfill). More in bronze is reported, not failed, since
  bronze keeps records the source has since removed.
- **Freshness.** dbt source freshness on `bronze.launches`, measured on the newest launch date: a
  warning after 7 days, an error after 14. Something launches almost every day, so a week without a
  new launch means the refresh has stopped.
- **New vehicles.** A vehicle that is not yet in the classification seed no longer fails the build.
  The relationship test warns, the launch is scoped `unclassified` (and stays out of the orbital
  marts), and the run page names the vehicle so the seed can be updated. The first refresh found
  one, Pallas-1 (Galactic Energy, demo flight 2026-09-01), now classified as orbital.

Limits: GitHub disables scheduled workflows on a repository with no activity for 60 days, and the
Databricks token has an expiry date. Either one stops the refresh, and the freshness check is what
makes that visible.

## Not modeled in v1

**`program`** is a list on the launch. A launch can belong to zero, one, or several programs
(Artemis, Commercial Crew, and so on). It would need a bridge table and is parked for a later
version rather than being flattened into a single value, which would misrepresent the source.

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

- **517 launches have no mission record; 530 have no orbit**, about 7% of the dataset. Nearly
  every missing orbit is missing because the whole mission record is absent.
- Explicit orbit "Unknown" is a separate, rare case: 16 records, all in the 2020s.
- The missingness is **not concentrated in early history**. By decade, the missing-orbit rate runs
  0% (1950s), 5.8%, 1.9%, 3.2%, 7.7%, 8.9%, then spikes to **28.1% in the 2010s** before
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
completeness comparison against the source count now runs after every scheduled refresh (see
Data operations); on its first run, bronze and the API agreed at 7,659 launches.

**The development mirror is not representative.** It holds 354 records where production holds
7,598. It is suitable for testing code and unsuitable for any quantitative conclusion.

**Source data errors exist and are recorded, not silently corrected.** Example: the Scout X-2
flight P-21A is recorded with orbit "Low Earth Orbit," but the P-21/P-21A missions were
historically suborbital ionosphere probes. The record is noted in the classification seed rather
than altered.

**Duplicate configuration records** (Soyuz U / Soyuz-U, two Zenit records) mean per-vehicle
statistics computed by name are wrong. All joins are on configuration id; name normalization is a
silver task.

**Reference data (agencies, launcher configurations) was fetched from the development mirror**, not
production, to stay inside the production rate limit. The shortcut is justified by coverage
verification: every provider id (99) and every configuration id (485) appearing in launch data was
found in the mirror snapshots. If either check ever fails, the missing records get fetched from
production.

**Agency country is a list in the source** (agencies can be multinational, such as ESA members).
The flatten keeps the first entry plus a `country_count`; any agency with `country_count > 1` is
carrying a simplification, disclosed here rather than resolved in v1.

**Nullable numeric fields flattened through pandas carry a float artifact** (`15.0`, `2020.0`)
because pandas promotes integer columns containing nulls to float before stringification. The
artifact is normalized in the staging layer, and the pattern is documented so new columns get
checked for it.

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
| 2026-08-26 | Pad location and celestial body added to bronze by re-flattening the raw archive. Celestial body found 11 Moon launches against the seed's 5: Apollo LM reclassified from `not_a_launch_vehicle` to `non_earth_launch`, and the two derivations now cross-validate (11 = 11). Reference snapshots (agencies, configurations) ingested from the development mirror with coverage verified against launch data. |
| 2026-10-24 | Phase 4: configuration families resolved as a hierarchy (not many-to-many) with a reviewed override seed; family chosen as the default maturation unit with configuration as the second lens; reliability defined as strict success rate with a 95% Wilson interval; `net_precision` finding corrected (null means not recorded, no Month or Year values exist); pre-launch failures (Apollo 1, Amos-6) recorded as an open decision. |
| 2026-10-25 | Failures before launch decided: Apollo 1 excluded through the `launch_exclusions` seed (new `scope_class` value `pre_launch_failure`), Amos-6 kept and disclosed. |
| 2026-10-25 | Maturity-adjusted reliability: debut curve by flight band and era, Kaplan-Meier opening-run survival (verified against `lifelines`), and a leave-one-out benchmark per vehicle; empirical-Bayes prior tested and not adopted, with the reason recorded. |
| 2026-10-26 | Phase 5: daily incremental refresh with page-by-page merge, completeness check against the API count (gap closed), source freshness, and a warning path for vehicles new since the last seed review. Pallas-1 added to the seed. |
