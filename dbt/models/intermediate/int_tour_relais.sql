-- Grain: one driver's lap, labelled with the stint it belongs to.
--
-- This exists so that the stint derivation lives in exactly one place and
-- can be checked on its own. It was originally inlined in
-- fct_rythme_relais, which made the derivation untestable: that model drops
-- stints with fewer than six clean laps, so the stints it reports are a
-- subset of the stints that happened, and a test comparing them against the
-- pit stop count can never hold. The first run of that test warned on 193
-- drives, none of which were wrong.
--
-- A driver pitting on lap L drives L as the in-lap, so the stint containing
-- lap N is numbered by how many stops happened strictly before N. Nothing is
-- filtered here: short stints, retirements and neutralised laps all keep
-- their label, and the filtering happens downstream where it can be stated.

with tours as (

    select * from {{ ref('stg_tours') }}

),

arrets as (

    select * from {{ ref('stg_arrets') }}

)

select
    t.saison,
    t.manche,
    t.course_id,
    t.pilote_id,
    t.numero_tour,
    t.temps_ms,
    t.position_sur_le_tour,
    1 + (
        select count(*)
        from arrets a
        where a.saison    = t.saison
          and a.manche    = t.manche
          and a.pilote_id = t.pilote_id
          and a.tour      < t.numero_tour
    ) as no_relais
from tours t
