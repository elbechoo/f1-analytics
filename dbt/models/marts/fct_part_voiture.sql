-- Grain: one season.
--
-- How much of a finishing position is the car?
--
-- The question is usually argued with anecdotes. It has a measurable answer.
-- Take every classified finish in a season, group the finishing positions by
-- constructor, and ask what share of the total variation in position sits
-- BETWEEN the teams rather than WITHIN them. That ratio is eta squared, the
-- standard effect size for a categorical grouping.
--
--   part_ecurie = 0.9  ->  knowing the car tells you almost exactly where it
--                          finished. The grid is sorted by machinery.
--   part_ecurie = 0.3  ->  teammates finish all over the place relative to
--                          each other and to the field. Something other than
--                          the car is doing the work.
--
-- Read as a time series it is a measure of how much the sport is a constructor
-- championship in practice, season by season, and it moves with the things you
-- would expect: regulation resets, refuelling, tyre wars, budget caps.
--
-- Two cautions, both real:
--   * This is an association, not a causal decomposition. Teams also choose
--     drivers, and the better teams hire the better drivers, so some of what
--     is attributed to the car here is the driver the car attracted.
--   * Only classified finishes count. Retirements carry no position, and a
--     season where the slow cars broke more often will look slightly more
--     car-driven than it was.

with base as (

    select
        saison,
        ecurie_id,
        position_classement::double as position
    from {{ ref('fct_resultat') }}
    where est_classe
      and position_classement is not null

),

saison_moy as (

    select
        saison,
        avg(position)   as moyenne,
        count(*)        as n
    from base
    group by 1

),

ecurie_moy as (

    select
        b.saison,
        b.ecurie_id,
        avg(b.position) as moyenne_ecurie,
        count(*)        as n_ecurie
    from base b
    group by 1, 2

),

sommes as (

    select
        s.saison,
        s.n,
        -- Total sum of squares around the season mean.
        sum(power(b.position - s.moyenne, 2))   as sc_total
    from base b
    join saison_moy s using (saison)
    group by 1, 2

),

inter as (

    select
        e.saison,
        count(*)                                        as nb_ecuries,
        sum(e.n_ecurie * power(e.moyenne_ecurie - s.moyenne, 2)) as sc_inter
    from ecurie_moy e
    join saison_moy s using (saison)
    group by 1

)

select
    s.saison,
    s.n                                     as nb_arrivees,
    i.nb_ecuries,
    s.sc_total,
    i.sc_inter,
    -- Guard the division: a season with one constructor has no between-team
    -- variation to measure and should be null, not 0 or an error.
    case
        when s.sc_total > 0 and i.nb_ecuries > 1
        then i.sc_inter / s.sc_total
    end                                     as part_ecurie,
    case
        when s.sc_total > 0 and i.nb_ecuries > 1
        then 1 - i.sc_inter / s.sc_total
    end                                     as part_hors_ecurie
from sommes s
join inter i using (saison)
order by s.saison
