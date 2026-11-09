-- Every race with lap timings must have them for every lap, with no holes.
--
-- The loader pages at 100 timings and a race is around 1,100 of them, so a
-- race is eleven or twelve calls. If one of those pages were lost, the race
-- would be missing a band of laps in the middle, the stint containing them
-- would be split or shortened, and the slope fitted through what remained
-- would be computed with complete confidence on half a stint.
--
-- Nothing else would notice. The round would be marked finished, the model
-- would build, the numbers would look like numbers. So this asserts that the
-- lap numbers present for a race run 1..max with nothing skipped.

with couverture as (

    select
        saison,
        manche,
        count(distinct numero_tour) as tours_distincts,
        max(numero_tour)            as dernier_tour
    from {{ ref('stg_tours') }}
    group by 1, 2

)

select
    saison,
    manche,
    tours_distincts,
    dernier_tour,
    dernier_tour - tours_distincts as tours_manquants
from couverture
where tours_distincts <> dernier_tour
