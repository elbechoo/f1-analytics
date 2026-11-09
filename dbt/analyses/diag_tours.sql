-- What a stored lap response actually looks like, before any model is built
-- on top of it.
--
-- Written as a query rather than guessed from the API documentation, because
-- the loader stores whatever came back and the only authority on the shape is
-- the row itself.

select
    'fetched so far'                                      as question,
    (select count(*) from raw.reponses where endpoint = 'laps')::varchar
      || ' responses, '
      || (select count(*) from raw.progression
           where endpoint = 'laps')::varchar || ' rounds'  as reponse

union all

select
    'seasons and rounds',
    (select string_agg(x, ', ') from (
        select saison::varchar || ': ' || count(*)::varchar || ' rounds' as x
        from raw.progression where endpoint = 'laps'
        group by saison order by saison))

union all

select
    'top-level keys',
    (select string_agg(k, ', ')
     from (select distinct unnest(json_keys(charge)) as k
           from raw.reponses where endpoint = 'laps' limit 1) t)

union all

select
    'keys under a Race',
    (select string_agg(k, ', ')
     from (select distinct unnest(
             json_keys(json_extract(charge, '$.RaceTable.Races[0]'))) as k
           from raw.reponses where endpoint = 'laps' limit 1) t)

union all

select
    'keys under a Lap',
    (select string_agg(k, ', ')
     from (select distinct unnest(
             json_keys(json_extract(charge,
               '$.RaceTable.Races[0].Laps[0]'))) as k
           from raw.reponses where endpoint = 'laps' limit 1) t)

union all

select
    'keys under a Timing',
    (select string_agg(k, ', ')
     from (select distinct unnest(
             json_keys(json_extract(charge,
               '$.RaceTable.Races[0].Laps[0].Timings[0]'))) as k
           from raw.reponses where endpoint = 'laps' limit 1) t)

union all

select
    'one Timing, verbatim',
    (select json_extract(charge,
              '$.RaceTable.Races[0].Laps[0].Timings[0]')::varchar
     from raw.reponses where endpoint = 'laps' limit 1)

union all

select
    'one pit stop, verbatim',
    (select json_extract(charge,
              '$.RaceTable.Races[0].PitStops[0]')::varchar
     from raw.reponses where endpoint = 'pitstops' limit 1)
