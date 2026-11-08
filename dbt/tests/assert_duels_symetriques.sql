-- Teammate duels must be symmetric: if A is recorded as beating B in a race,
-- the row for B must record losing to A. An asymmetry means the self-join
-- dropped a side, and every head-to-head record built on it would be wrong
-- in one direction only - the hardest kind of error to notice.
select
    a.saison, a.manche, a.ecurie_id,
    a.pilote_id        as pilote_a,
    a.coequipier_id    as pilote_b,
    a.bat_coequipier_course as a_bat_b,
    b.bat_coequipier_course as b_bat_a
from {{ ref('fct_duel_coequipiers') }} a
join {{ ref('fct_duel_coequipiers') }} b
  on  b.saison      = a.saison
  and b.manche      = a.manche
  and b.pilote_id   = a.coequipier_id
  and b.coequipier_id = a.pilote_id
where a.bat_coequipier_course = b.bat_coequipier_course
