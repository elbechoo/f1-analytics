-- Grain: one pit stop by one driver in one race.
--
-- Same completeness guard as the lap timings: a round only counts once the
-- loader has marked it finished. A missing stop would merge two stints into
-- one and make the second look like a sudden return to fresh-tyre pace.

with reponses as (

    select r.saison, r.manche, r.charge
    from {{ source('raw', 'reponses') }} r
    join {{ source('raw', 'progression') }} p
      on  p.endpoint = 'pitstops'
      and p.saison   = r.saison
      and p.manche   = r.manche
    where r.endpoint = 'pitstops'

),

arrets as (

    select
        saison,
        manche,
        unnest(json_extract(charge, '$.RaceTable.Races[0].PitStops[*]')) as arret
    from reponses

)

select
    {{ dbt_utils.generate_surrogate_key([
        'saison', 'manche', 'pilote_id', 'numero_arret'
    ]) }}                                       as arret_id,
    saison,
    manche,
    saison * 100 + manche                       as course_id,
    pilote_id,
    numero_arret,
    tour,
    -- Seconds, and this is stationary time plus the pit lane, not just the
    -- stop itself. Useful for comparing teams, useless as an absolute.
    duree_s
from (
    select
        saison,
        manche,
        json_extract_string(arret, '$.driverId')                    as pilote_id,
        try_cast(json_extract_string(arret, '$.stop') as integer)   as numero_arret,
        try_cast(json_extract_string(arret, '$.lap') as integer)    as tour,
        try_cast(json_extract_string(arret, '$.duration') as double) as duree_s
    from arrets
)
where pilote_id is not null
  and tour is not null
