-- One row per Grand Prix. The grain every fact joins to.
with resultats as (
    select * from {{ ref('stg_resultats') }}
)
select
    saison * 100 + manche                            as course_id,
    saison,
    manche,
    any_value(nom_course)                            as nom_course,
    any_value(date_course)                           as date_course,
    any_value(circuit_id)                            as circuit_id,
    extract(year  from any_value(date_course))       as annee,
    extract(month from any_value(date_course))       as mois,
    count(*)                                         as nb_partants,
    count(*) filter (where position_classement is not null) as nb_classes,
    count(*) filter (where position_classement is null)     as nb_abandons
from resultats
group by saison, manche
