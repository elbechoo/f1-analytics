-- Grain: one pair of teammates in one race.
--
-- The question this exists to answer: how much of a driver's result is the
-- driver, and how much is the car?
--
-- Ranking drivers by wins mostly ranks cars. Teammates share the machinery,
-- the strategy and the upgrades, so comparing a driver only against the other
-- person in the same garage is the one comparison the data supports.
--
-- Rules, each of which throws away data on purpose:
--   * both drivers must be classified - if one retires, the comparison says
--     nothing about pace, only about reliability
--   * exactly two drivers per team per race - third cars and mid-season
--     substitutions make "the teammate" ambiguous
--   * they must be classified in DIFFERENT positions - see below
--   * each pair is emitted once per driver, so a season can be summed per
--     driver without double counting
--
-- The equal-position rule exists because of shared drives. Until 1958 two
-- drivers could share one car and both be credited with its result: Fangio
-- and Fagioli were both classified first at Reims in 1951. "Who beat whom"
-- has no answer when the answer is "they were the same car", and leaving
-- them in made the head-to-head asymmetric - A did not beat B and B did not
-- beat A, so both sides recorded a loss. A symmetry test caught it.

with resultats as (

    select * from {{ ref('fct_resultat') }}

),

paires as (

    select
        a.saison,
        a.manche,
        a.course_id,
        a.ecurie_id,
        a.pilote_id                     as pilote_id,
        b.pilote_id                     as coequipier_id,
        a.position_classement           as position_pilote,
        b.position_classement           as position_coequipier,
        a.position_grille               as grille_pilote,
        b.position_grille               as grille_coequipier,
        a.points                        as points_pilote,
        b.points                        as points_coequipier,
        -- DISTINCT drivers, not rows: a shared drive puts the same driver
        -- in the team twice and a plain count(*) would wrongly rule the
        -- race out of a perfectly valid two-driver comparison.
        count(distinct a.pilote_id) over (
            partition by a.saison, a.manche, a.ecurie_id
        )                               as nb_pilotes_ecurie
    from resultats a
    join resultats b
      on  b.saison    = a.saison
      and b.manche    = a.manche
      and b.ecurie_id = a.ecurie_id
      and b.pilote_id <> a.pilote_id
    where a.est_classe and b.est_classe
      -- Shared car: both credited with the same finishing position, so
      -- there is no head-to-head result to record.
      and a.position_classement <> b.position_classement

)

select
    {{ dbt_utils.generate_surrogate_key(['saison', 'manche', 'pilote_id', 'coequipier_id']) }} as duel_id,
    saison,
    manche,
    course_id,
    ecurie_id,
    pilote_id,
    coequipier_id,
    position_pilote,
    position_coequipier,
    grille_pilote,
    grille_coequipier,
    points_pilote,
    points_coequipier,
    position_pilote < position_coequipier   as bat_coequipier_course,
    case
        when grille_pilote is null or grille_coequipier is null
             or grille_pilote = 0 or grille_coequipier = 0 then null
        else grille_pilote < grille_coequipier
    end                                     as bat_coequipier_quali,
    position_coequipier - position_pilote   as ecart_positions
from paires
-- 2 means exactly one teammate, which is the only case the comparison is
-- well defined for. Three-car entries existed in the 1950s-60s.
where nb_pilotes_ecurie = 2
