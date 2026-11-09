# Apex Data

A dbt warehouse over the complete results history of world championship motor
racing, 1950 to the current season, with a statistical layer that tries to
answer a question the raw results cannot: how much of a driver's record is the
driver.

**Live page:** https://elbechoo.github.io/f1-analytics/

It refreshes itself. Every thirty minutes during a race weekend a scheduled job
asks the source whether anything changed, and when something has, it fetches,
rebuilds the warehouse, runs every test and republishes the page. Nobody runs
anything by hand, including when a new season starts.

---

## Why this exists

Ranking drivers by wins mostly ranks cars. The driver in the quickest car wins
and the same driver in the tenth-quickest does not, so a wins table measures
the pairing rather than the person. Almost every F1 data project stops there.

The only comparison the data genuinely supports is a driver against the other
person in the same garage: same car, same upgrades, same strategy, same race.
The difficulty is that almost no two drivers were ever teammates, so that
comparison is thousands of disconnected two-driver islands.

This project joins the islands.

---

## What it does

### Teammate-adjusted driver strength

`fct_force_pilote` is a Python model inside the dbt DAG. It fits a
Bradley-Terry model over every teammate duel in the warehouse: each driver gets
a latent strength, and the probability that i finishes ahead of j in equal
machinery is `p_i / (p_i + p_j)`. Fitting those strengths turns the teammate
graph into one scale, so A who raced B, who raced C, who raced D, becomes
comparable with D across forty years and a dozen regulation eras.

The fit uses minorization-maximization, which is the standard solver for this
likelihood and increases it at every step. Three things keep the output honest:

- **Regularisation.** A driver who beat one teammate once and never lost has an
  unbounded maximum-likelihood strength. Everyone gets two pseudo-duels against
  a virtual average opponent, which pulls thin records toward the middle and
  leaves long records untouched.
- **Connected components.** Strengths are only comparable inside a connected
  piece of the graph. Drivers whose careers never touch the main chain are
  labelled and excluded from the ranking rather than quietly mixed in.
- **Uncertainty.** The duels are resampled and the model refitted 300 times,
  giving each driver a percentile interval. The chart shows the interval, so a
  300-duel career and a 45-duel career do not look alike.

### Where the model is wrong

`fct_calibration_duel` materialises the residuals, and both the test suite and
the page read it, so they cannot drift apart.

Across 67 well-observed pairings the mean absolute error is 0.060 and the worst
single miss is 0.258.

The largest residuals are not randomly distributed. The worst of them are
**late-career** pairings in which the model favours the veteran: Ricciardo
against Tsunoda in 2023-24, Stroll against Vettel in 2021-22, Schumacher
against Rosberg in 2010-12. One strength is fitted per driver for an entire
career, so a driver is scored in their final season with a rating earned at
their peak.

What is **not** supported is a claim that this bias holds across all late
pairings. A warn-level test measures exactly that and does not currently fire,
so the effect is visible in the tail and small in aggregate. The test prints
the number on every build precisely so the claim stays tied to the data rather
than to the first pattern someone noticed.

### The rules as a variable

`fct_championnat_contrefactuel` rescores every season under all five scoring
systems the sport has used. Some championships survive every system; in others
the points table, not the racing, chose the champion.

Dropped scores, used until 1990, are deliberately not applied: carrying one
era's drop rule into another era's calendar compares nothing. What is compared
is the shape of the scoring curve, with all results counting in each case, and
the 1950s champions here can therefore differ from the record books.

### Car or driver, measured

`fct_part_voiture` computes eta squared per season: the share of variance in
finishing position sitting between constructors rather than within them. High
means the grid is sorted by machinery. Read as a time series it is a measure of
how much the sport is a constructors' championship in practice.

It is an association, not a causal split, and the model says so: better teams
also hire better drivers, so some of what lands on the car is the driver the
car attracted.

---

## What it found

The warehouse holds 26,313 results across 1,169 races, 820 drivers and 205
constructors, 1950 to 2026, from which 5,353 decided teammate duels and 2,288
driver-and-constructor periods are derived. 70 drivers clear the 40-duel floor
and sit in the connected part of the teammate graph.

### The sport became roughly twice as car-determined

Share of variance in finishing position explained by the constructor:

| Period | eta squared |
| --- | --- |
| Before 1980 | 0.34 |
| All seasons | 0.47 |
| 2014 onward | 0.61 |

In the first thirty years, knowing the car told you about a third of where it
finished. In the hybrid era it tells you nearly two thirds. The drivers did not
get less important; the cars got further apart.

### In 12 of 77 seasons the scoring system picks the champion

Rescored under all five systems, the name at the top of the table changes in
twelve seasons, and the list is its own validation: 2016, 2012, 2008, 1999,
1997, 1994, 1983, 1981, 1976, 1970. Those are, independently, the famously
close championships. A model built with no knowledge of which title fights were
tight recovered them from the points alone.

Hamilton and Massa in 2008 swap under three of the five systems. Hunt and Lauda
in 1976 swap under two.

### The strength ranking, and why you should read it carefully

The top of the table is Verstappen, Leclerc, Senna, Alonso, Norris, Schumacher,
Sainz, Russell. Senna's interval spans 1755 to 1958 on 72 duels; Alonso's spans
1781 to 1876 on 298. That width difference is the honest part of the output.

The ranking leans modern, and that deserves scepticism rather than a defence.
Drivers on the current grid have raced each other, directly and often, so their
relative order is well determined. Eras connect only through a handful of
bridging careers, so a cross-era comparison passes through a long chain of
inferences and is far less certain than a within-era one. The bootstrap
interval captures sampling noise in the duels; it does **not** capture the
structural uncertainty of chaining through the graph, so the true uncertainty
on "Norris versus Schumacher" is wider than the bars suggest. Treat the
within-era orderings as the result and the cross-era ones as indicative.

---

## The test I would point an interviewer at

`assert_bareme_moderne_reproduit_les_points` rescores 2010 to 2018 from nothing
and requires the answer to equal the points those drivers actually took. If the
scoring tables are wrong, the build goes red instead of producing a plausible
alternative history that happens to be fiction.

The window is narrow on purpose. It skips 2014, which awarded double points at
the finale; it stops before 2019, when the fastest-lap bonus arrived; and well
before sprint races. Each of those is a real divergence rather than a bug, and
including them would turn a sharp test into a vague one.

There is also a story in `assert_force_pilote_calibree`. It was first written as
a hard per-pair bound: fail if any well-observed pairing is out by more than
0.20. That is the wrong statistic. Across a couple of hundred pairings some tail
deviation is expected from a model that is working, so the bound measured the
size of the tail rather than the quality of the fit, and it went red on correct
behaviour. It now checks the distribution and keeps one very loose per-pair
bound to catch the failure averaging could hide: a win matrix built with winner
and loser reversed.

---

## Architecture

```
ingest/fetch_f1.py     resumable loader, rate-limit backoff, progress table
  -> raw.reponses      one row per API response, JSON kept whole
  -> raw.progression   what has been fetched, so a killed run resumes

dbt/models/staging     JSON unnested and typed, views
dbt/models/marts       Kimball star schema, a Type 2 dimension,
                       the Bradley-Terry fit, the counterfactual scoring
dbt/tests              singular assertions, including the ground-truth one

analysis/build_dashboard.py   reads the marts, writes one self-contained page
```

Every chart on the page is SVG written by hand in that script. No chart
library, no build step, no JavaScript framework: the output is text git can
diff, and the only external request is the webfont stylesheet.

---

## Running it

```bash
pip install -r requirements.txt
python ingest/fetch_f1.py          # resumable, re-run after a rate limit
cd dbt && dbt build && cd ..
python analysis/build_dashboard.py # writes dashboard/index.html
```

`python analysis/chiffres.py` prints the headline numbers straight from the
warehouse.

---

## How the refresh works

`.github/workflows/refresh.yml` polls every thirty minutes from Friday to
Monday, which covers every session in every time zone the calendar visits, and
twice midweek for amendments.

Each poll makes **one** API call, hashes the season's stored payloads and
compares that with the hash the previous run left in the cache. Nothing new,
the job stops. Something new, it fetches the rest, rebuilds, tests, renders and
deploys. A hash rather than a row count, because a penalty applied on Monday
rewrites a classification without adding a row.

The warehouse is not in git. It is a binary build output that would make every
diff useless, so it lives in the Actions cache. A cache miss is survivable
rather than fatal, which is the entire reason the fetcher is resumable: with no
cache the job starts from an empty database and converges over several runs
under the rate limit, unattended.

`ci.yml` runs on every push but only claims what it can prove. The data tests
cannot run there, because the warehouse is a build output and rebuilding it
inside a pull request would exceed the rate limit. It checks that the graph
resolves and the Python imports. The data tests run in the scheduled job
against the real warehouse, and that job going red is the real signal.

---

## What this does not do

- **It is not live timing.** The source publishes a classification once it is
  official, some time after the flag. No polling interval turns an
  after-the-fact results feed into live timing, and the page says so.
- **Lap times and pit stops are not loaded yet.** The loader supports them and
  `vars.laps_depuis` reserves the window, but no model consumes them, so race
  pace and stint degradation are not here.
- **Beating your teammate is not the same as being the best driver.** The model
  cannot see a driver who never had a competitive seat, cannot see a teammate
  held back, and treats a 1952 duel and a 2026 duel as the same kind of event.
- **Reliability is excluded on purpose.** Duels where one car retired are
  dropped upstream: a broken gearbox is not a comment on pace.
- **Cross-era strength comparisons are weaker than they look.** The bootstrap
  interval measures sampling noise in the duels, not the uncertainty added by
  chaining through a graph whose eras touch at only a few points.

---

## Source and marks

Results come from the Jolpica mirror of the Ergast API. All marks, colours and
artwork here are my own.
