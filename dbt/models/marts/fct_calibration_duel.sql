-- Grain: one pair of drivers who were teammates often enough to measure.
--
-- The model's own residuals, materialised. For each well-observed pairing:
-- what share did driver A really take, what share does the fitted strength
-- predict, and how far apart are they.
--
-- This exists as a model rather than as a query inside a test for two
-- reasons. The test reads it, so the test and the chart cannot drift apart.
-- And the residuals are worth looking at: they are not noise. They carry a
-- sign, and the sign says something the single-number ranking cannot.

with paires as (

    select
        least(pilote_id, coequipier_id)     as pilote_a,
        greatest(pilote_id, coequipier_id)  as pilote_b,
        sum(case
                when bat_coequipier_course
                 and pilote_id = least(pilote_id, coequipier_id)
                then 1 else 0
            end)                            as victoires_a,
        -- Each race pair is emitted once per driver, so the row count is
        -- twice the number of duels.
        count(*) / 2                        as nb_duels,
        min(saison)                         as premiere_saison,
        max(saison)                         as derniere_saison
    from {{ ref('fct_duel_coequipiers') }}
    group by 1, 2
    having count(*) / 2 >= 20

),

debuts as (

    select pilote_id, min(saison) as saison_debut
    from {{ ref('fct_resultat') }}
    group by 1

)

select
    {{ dbt_utils.generate_surrogate_key(['pilote_a', 'pilote_b']) }} as paire_id,
    p.pilote_a,
    p.pilote_b,
    na.nom_complet                                      as nom_a,
    nb.nom_complet                                      as nom_b,
    p.premiere_saison,
    p.derniere_saison,
    p.nb_duels,
    p.victoires_a::double / p.nb_duels                  as part_observee,
    fa.force / (fa.force + fb.force)                    as part_predite,
    fa.force / (fa.force + fb.force)
      - p.victoires_a::double / p.nb_duels              as residu,
    abs(fa.force / (fa.force + fb.force)
        - p.victoires_a::double / p.nb_duels)           as ecart,
    fa.note                                             as note_a,
    fb.note                                             as note_b,

    -- Seasons each driver was into their career when the pairing began. The
    -- residuals correlate with this, which is the model's main blind spot:
    -- one strength is fitted per driver for a whole career, so a pairing late
    -- in a veteran's career is scored against a rating earned at their peak.
    p.premiere_saison - da.saison_debut                 as anciennete_a,
    p.premiere_saison - db.saison_debut                 as anciennete_b,
    greatest(p.premiere_saison - da.saison_debut,
             p.premiere_saison - db.saison_debut)       as anciennete_maxi

from paires p
join {{ ref('fct_force_pilote') }} fa on fa.pilote_id = p.pilote_a
join {{ ref('fct_force_pilote') }} fb on fb.pilote_id = p.pilote_b
join {{ ref('dim_pilote') }} na      on na.pilote_id = p.pilote_a
join {{ ref('dim_pilote') }} nb      on nb.pilote_id = p.pilote_b
join debuts da                       on da.pilote_id = p.pilote_a
join debuts db                       on db.pilote_id = p.pilote_b
where fa.dans_composante_principale
  and fb.dans_composante_principale
