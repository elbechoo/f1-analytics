-- Why assert_force_pilote_calibree failed: show every well-observed pair,
-- worst disagreement first, with the names and the span of the partnership.
--
-- The span is the thing to look at. Bradley-Terry fits ONE strength per
-- driver for a whole career, so a pairing that ran for many seasons across a
-- change in one driver's level is expected to miss. A pairing that lasted two
-- seasons and still misses badly would mean something is wrong with the fit.

with paires as (

    select
        least(d.pilote_id, d.coequipier_id)     as a,
        greatest(d.pilote_id, d.coequipier_id)  as b,
        sum(case
                when d.bat_coequipier_course
                 and d.pilote_id = least(d.pilote_id, d.coequipier_id)
                then 1 else 0
            end)                                as victoires_a,
        count(*) / 2                            as nb_duels,
        min(d.saison)                           as premiere,
        max(d.saison)                           as derniere
    from main_marts.fct_duel_coequipiers d
    group by 1, 2
    having count(*) / 2 >= 20

)

select
    pa.nom_complet                                  as pilote_a,
    pb.nom_complet                                  as pilote_b,
    p.premiere,
    p.derniere,
    p.derniere - p.premiere + 1                     as saisons,
    p.nb_duels,
    round(p.victoires_a::double / p.nb_duels, 3)    as observe,
    round(fa.force / (fa.force + fb.force), 3)      as predit,
    round(abs(fa.force / (fa.force + fb.force)
              - p.victoires_a::double / p.nb_duels), 3) as ecart,
    round(fa.note)                                  as note_a,
    round(fb.note)                                  as note_b,
    fa.nb_duels                                     as duels_carriere_a,
    fb.nb_duels                                     as duels_carriere_b
from paires p
join main_marts.fct_force_pilote fa on fa.pilote_id = p.a
join main_marts.fct_force_pilote fb on fb.pilote_id = p.b
join main_marts.dim_pilote pa on pa.pilote_id = p.a
join main_marts.dim_pilote pb on pb.pilote_id = p.b
where fa.dans_composante_principale
  and fb.dans_composante_principale
order by ecart desc
limit 15
