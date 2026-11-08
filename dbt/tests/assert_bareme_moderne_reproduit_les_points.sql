-- The counterfactual scoring model is only worth looking at if it can
-- reproduce reality where reality is known.
--
-- From 2010 the current points table has been in force, so rescoring those
-- seasons under `2010_now` must give back exactly the points the drivers
-- actually scored. If it does not, the scoring table in the model is wrong and
-- every alternative history built on it is worthless.
--
-- The window stops at 2018 and skips 2014, for reasons that are themselves
-- the point of writing the test narrowly:
--   * 2014 awarded double points at the final round, a one-season rule.
--   * 2019 added a bonus point for the fastest lap inside the top ten.
--   * 2021 added sprint races, which award points outside the race result.
-- Each of those is a real divergence, not a bug, so including those seasons
-- would turn a sharp test into a vague one. The years that remain have no
-- such wrinkle and must match to the point.

with attendu as (

    select
        saison,
        pilote_id,
        sum(points) as points_reels
    from {{ ref('fct_resultat') }}
    where saison between 2010 and 2018
      and saison <> 2014
    group by 1, 2

),

obtenu as (

    select
        saison,
        pilote_id,
        points as points_modele
    from {{ ref('fct_championnat_contrefactuel') }}
    where systeme = '2010_now'
      and saison between 2010 and 2018
      and saison <> 2014

)

select
    coalesce(a.saison, o.saison)        as saison,
    coalesce(a.pilote_id, o.pilote_id)  as pilote_id,
    a.points_reels,
    o.points_modele
from attendu a
full outer join obtenu o
  on  o.saison    = a.saison
  and o.pilote_id = a.pilote_id
-- A driver who scored nothing has no row on the model side, which is correct,
-- so only a non-zero real total without a match is a failure.
where coalesce(a.points_reels, 0) <> coalesce(o.points_modele, 0)
