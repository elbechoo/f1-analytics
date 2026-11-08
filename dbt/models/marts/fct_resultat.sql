-- Grain: one driver's drive in one race.
--
-- "One driver per race" is NOT the grain, and that is the interesting part.
-- Until the mid-1960s a driver could take over a teammate's car mid-race, or
-- start one car and finish in another. Ascari retired his Ferrari at Spa in
-- 1950, took over Villoresi's, and was classified second - two rows, same
-- driver, same race, same constructor.
--
-- So the key carries an occurrence number. Widening it with the constructor
-- alone would not work: both of Ascari's drives were Ferraris. 83 drives are
-- affected, all between 1950 and 1964, and the 1953-54 spikes are the
-- Indianapolis 500, which counted for the championship and was full of
-- relief drivers.
--
-- Deduplicating would have been the easy call and would have silently
-- deleted real results.

with resultats as (

    select
        *,
        row_number() over (
            partition by saison, manche, pilote_id
            order by position_classement, statut
        ) as no_relais
    from {{ ref('stg_resultats') }}

)

select
    {{ dbt_utils.generate_surrogate_key([
        'saison', 'manche', 'pilote_id', 'no_relais'
    ]) }}                                       as resultat_id,
    saison * 100 + manche                       as course_id,
    saison,
    manche,
    date_course,
    pilote_id,
    ecurie_id,
    circuit_id,
    no_relais,
    no_relais > 1                               as est_relais,

    position_grille,
    position_classement,
    position_texte,
    points,
    tours_couverts,
    statut,
    temps_total_ms,
    rang_meilleur_tour,

    -- Classified means positionText is a number. Everything else - R, D, W,
    -- E, F - is some flavour of "did not take the flag", and lumping them in
    -- with finishers inflates every finishing-position average.
    regexp_matches(position_texte, '^[0-9]+$')  as est_classe,
    statut = 'Finished'                         as a_termine,

    position_texte = '1'                        as est_victoire,
    regexp_matches(position_texte, '^[1-3]$')   as est_podium,
    position_grille = 1                         as est_pole,

    -- Only meaningful for a classified finisher. Null otherwise, so a
    -- retirement does not register as losing twenty places.
    case
        when not regexp_matches(position_texte, '^[0-9]+$') then null
        when position_grille is null or position_grille = 0 then null
        else position_grille - position_classement
    end                                         as gain_places
from resultats
