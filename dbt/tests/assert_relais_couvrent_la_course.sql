-- A driver who stopped twice ran three stints. Not two, not four.
--
-- Stint numbers are derived, not given: int_tour_relais counts how many pit
-- stops happened before each lap. That derivation has one way to go wrong
-- quietly, the off-by-one on the in-lap. Count a stop on lap L as belonging
-- to the stint it starts rather than the one it ends, and every boundary
-- shifts by a lap, every in-lap lands in the wrong stint, and nothing looks
-- broken: the slopes stay plausible and the build stays green.
--
-- The first version of this test read fct_rythme_relais and warned on 193
-- drives, none of which were wrong. That model drops stints with fewer than
-- six clean laps, so the stints it reports are a subset of the stints that
-- happened and the identity could never hold there. The test was measuring
-- the filter, not the derivation. It now reads int_tour_relais, where
-- nothing has been thrown away yet, and is an error rather than a warning
-- because at that layer there is no legitimate reason to disagree.
--
-- One real exception survives and is excluded explicitly: a driver can pit
-- and retire in the pit lane, recording a stop with no stint after it. That
-- shows up as the last stop landing on or after the driver's final lap.

with relais as (

    select
        saison, manche, pilote_id,
        max(no_relais)    as nb_relais,
        max(numero_tour)  as dernier_tour
    from {{ ref('int_tour_relais') }}
    group by 1, 2, 3

),

arrets as (

    select
        saison, manche, pilote_id,
        count(*)   as nb_arrets,
        max(tour)  as dernier_arret
    from {{ ref('stg_arrets') }}
    group by 1, 2, 3

)

select
    r.saison,
    r.manche,
    r.pilote_id,
    r.nb_relais,
    a.nb_arrets,
    r.dernier_tour,
    a.dernier_arret,
    r.nb_relais - (a.nb_arrets + 1) as ecart
from relais r
join arrets a
  on  a.saison    = r.saison
  and a.manche    = r.manche
  and a.pilote_id = r.pilote_id
-- Retired in the pit lane: the final stop has no racing lap after it.
where a.dernier_arret < r.dernier_tour
  and r.nb_relais <> a.nb_arrets + 1
