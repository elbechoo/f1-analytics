-- Grain: one driver's lap time on one lap of one race.
--
-- Lap timings only exist from the season named in vars.laps_depuis. A race is
-- around 1,100 timings and the API pages at 100, so history is expensive and
-- was not fetched. Anything built on this model must say which seasons it
-- covers rather than imply the whole archive.
--
-- Only rounds that appear in raw.progression are read. The loader writes that
-- row when a round finishes downloading, so a round interrupted halfway has
-- pages in raw.reponses but no progress marker. Including it would produce a
-- race that quietly stops at lap 40 and a confident, wrong pace number for
-- everyone in it. This is the one place to catch that, because by the time it
-- reaches a mart it looks like data.

with reponses as (

    select r.saison, r.manche, r.charge
    from {{ source('raw', 'reponses') }} r
    join {{ source('raw', 'progression') }} p
      on  p.endpoint = 'laps'
      and p.saison   = r.saison
      and p.manche   = r.manche
    where r.endpoint = 'laps'

),

tours as (

    select
        saison,
        manche,
        unnest(json_extract(charge, '$.RaceTable.Races[0].Laps[*]')) as tour
    from reponses

),

chronos as (

    select
        saison,
        manche,
        try_cast(json_extract_string(tour, '$.number') as integer) as numero_tour,
        unnest(json_extract(tour, '$.Timings[*]'))                 as chrono
    from tours

)

select
    {{ dbt_utils.generate_surrogate_key([
        'saison', 'manche', 'numero_tour', 'pilote_id'
    ]) }}                                                   as tour_id,
    saison,
    manche,
    saison * 100 + manche                                   as course_id,
    numero_tour,
    pilote_id,
    position_sur_le_tour,
    temps_texte,

    -- "1:39.019". Minutes and seconds, never hours: the slowest lap in the
    -- data is a wet safety-car lap and still well under ten minutes. Parsed
    -- rather than cast, because there is no interval type that reads this
    -- format directly, and a silent null here would delete a lap from a
    -- stint and bias its slope.
    case
        when temps_texte is null then null
        when length(temps_texte) - length(replace(temps_texte, ':', '')) = 1
        then (
            try_cast(split_part(temps_texte, ':', 1) as integer) * 60000
          + try_cast(split_part(temps_texte, ':', 2) as double) * 1000
        )::bigint
    end                                                     as temps_ms

from (
    select
        saison,
        manche,
        numero_tour,
        json_extract_string(chrono, '$.driverId')                   as pilote_id,
        try_cast(json_extract_string(chrono, '$.position') as integer)
                                                                    as position_sur_le_tour,
        json_extract_string(chrono, '$.time')                       as temps_texte
    from chronos
)
where pilote_id is not null
  and numero_tour is not null
