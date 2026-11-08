-- Which teammate pairs break symmetry, and why?
select a.saison, a.manche, a.ecurie_id,
       a.pilote_id, a.coequipier_id,
       a.position_pilote, a.position_coequipier,
       a.bat_coequipier_course as a_bat_b,
       b.bat_coequipier_course as b_bat_a
from main_marts.fct_duel_coequipiers a
join main_marts.fct_duel_coequipiers b
  on b.saison = a.saison and b.manche = a.manche
 and b.pilote_id = a.coequipier_id and b.coequipier_id = a.pilote_id
where a.bat_coequipier_course = b.bat_coequipier_course
order by a.saison, a.manche
