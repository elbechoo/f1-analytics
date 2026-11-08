-- One row per driver per qualifying session. Only exists from 1994.
--
-- Q1/Q2/Q3 are lap times as text ("1:29.123"); the three-part format only
-- applies from 2006, before which there is a single time. They are kept as
-- text here and converted where they are used, so staging stays a faithful
-- flattening.

with reponses as (

    select charge
    from {{ source('raw', 'reponses') }}
    where endpoint = 'qualifying'

),

courses as (
    select unnest(json_extract(charge, '$.RaceTable.Races[*]')) as course
    from reponses
),

quali as (
    select course, unnest(json_extract(course, '$.QualifyingResults[*]')) as q
    from courses
)

select
    cast(json_extract_string(course, '$.season') as integer)    as saison,
    cast(json_extract_string(course, '$.round')  as integer)    as manche,
    json_extract_string(q, '$.Driver.driverId')                 as pilote_id,
    json_extract_string(q, '$.Constructor.constructorId')       as ecurie_id,
    try_cast(json_extract_string(q, '$.position') as integer)   as position_quali,
    json_extract_string(q, '$.Q1')                              as q1,
    json_extract_string(q, '$.Q2')                              as q2,
    json_extract_string(q, '$.Q3')                              as q3
from quali
