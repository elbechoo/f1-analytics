-- Every race has a winner, and co-winners only ever shared one car.
--
-- The first version of this test asserted exactly one winner per race and
-- failed on three. All three are real:
--
--   1951 R4  Fangio + Fagioli   Alfa     French GP, Reims
--   1956 R1  Musso  + Fangio    Ferrari  Argentine GP
--   1957 R5  Moss   + Brooks    Vanwall  British GP, Aintree
--
-- Until 1958 a driver could hand his car to a teammate mid-race and both
-- were credited with the result. "One winner per race" is a modern rule
-- projected backwards onto seventy-five years of history.
--
-- Rather than relax the test to ">= 1 winner", which would stop catching
-- anything, it now states what is actually true: a race has at least one
-- winner, and if it has more than one they were in the SAME CAR. Two
-- winners from different constructors would be a genuine bug.
with vainqueurs as (

    select
        course_id,
        saison,
        manche,
        count(*)                        as nb_vainqueurs,
        count(distinct ecurie_id)       as nb_ecuries_gagnantes
    from {{ ref('fct_resultat') }}
    where est_victoire
    group by course_id, saison, manche

),

courses as (

    select course_id, saison, manche from {{ ref('dim_course') }}

)

-- A race with no winner at all.
select
    c.course_id, c.saison, c.manche,
    'aucun vainqueur' as probleme,
    0 as nb_vainqueurs
from courses c
left join vainqueurs v on v.course_id = c.course_id
where v.course_id is null

union all

-- Co-winners from different teams: impossible, they cannot have shared a car.
select
    v.course_id, v.saison, v.manche,
    'vainqueurs multiples dans des ecuries differentes' as probleme,
    v.nb_vainqueurs
from vainqueurs v
where v.nb_vainqueurs > 1
  and v.nb_ecuries_gagnantes > 1
