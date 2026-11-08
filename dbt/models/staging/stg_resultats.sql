-- One row per driver per race, 1950 to date.
--
-- The source is nested JSON: a response holds Races[], each race holds
-- Results[], and each result holds Driver and Constructor objects. Two
-- unnests flatten it. Doing this here rather than in the loader means the
-- shredding is version-controlled and the tests below it are meaningful.

with reponses as (

    select charge
    from {{ source('raw', 'reponses') }}
    where endpoint = 'results'

),

courses as (

    select unnest(json_extract(charge, '$.RaceTable.Races[*]')) as course
    from reponses

),

resultats as (

    select
        course,
        unnest(json_extract(course, '$.Results[*]')) as resultat
    from courses

)

select
    cast(json_extract_string(course, '$.season') as integer)        as saison,
    cast(json_extract_string(course, '$.round')  as integer)        as manche,
    json_extract_string(course, '$.raceName')                       as nom_course,
    cast(json_extract_string(course, '$.date') as date)             as date_course,
    json_extract_string(course, '$.Circuit.circuitId')              as circuit_id,
    json_extract_string(course, '$.Circuit.circuitName')            as nom_circuit,
    json_extract_string(course, '$.Circuit.Location.country')       as pays_circuit,
    json_extract_string(course, '$.Circuit.Location.locality')      as ville_circuit,

    json_extract_string(resultat, '$.Driver.driverId')              as pilote_id,
    json_extract_string(resultat, '$.Driver.givenName')             as prenom_pilote,
    json_extract_string(resultat, '$.Driver.familyName')            as nom_pilote,
    json_extract_string(resultat, '$.Driver.code')                  as code_pilote,
    json_extract_string(resultat, '$.Driver.nationality')           as nationalite_pilote,
    try_cast(json_extract_string(resultat, '$.Driver.dateOfBirth') as date) as naissance_pilote,

    json_extract_string(resultat, '$.Constructor.constructorId')    as ecurie_id,
    json_extract_string(resultat, '$.Constructor.name')             as nom_ecurie,
    json_extract_string(resultat, '$.Constructor.nationality')      as nationalite_ecurie,

    -- `position` is the CLASSIFICATION order and is always populated, including
    -- for retirements - it is where the car was ranked, not where it finished.
    -- `positionText` is what distinguishes them: a number for a classified
    -- finisher, 'R' retired, 'D' disqualified, 'W' withdrawn, 'E' excluded.
    --
    -- Getting this backwards is easy and expensive: a first attempt here
    -- assumed position was null for retirements and asserted it in a test,
    -- which failed on 9,719 rows. The name reflects the truth now.
    try_cast(json_extract_string(resultat, '$.position') as integer) as position_classement,
    json_extract_string(resultat, '$.positionText')                 as position_texte,
    try_cast(json_extract_string(resultat, '$.grid') as integer)     as position_grille,
    cast(json_extract_string(resultat, '$.points') as double)        as points,
    try_cast(json_extract_string(resultat, '$.laps') as integer)     as tours_couverts,
    json_extract_string(resultat, '$.status')                        as statut,
    try_cast(json_extract_string(resultat, '$.Time.millis') as bigint) as temps_total_ms,
    try_cast(json_extract_string(resultat, '$.FastestLap.rank') as integer) as rang_meilleur_tour

from resultats
