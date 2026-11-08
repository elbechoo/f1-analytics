-- One row per circuit.
with resultats as (
    select * from {{ ref('stg_resultats') }}
)
select
    circuit_id,
    any_value(nom_circuit)                  as nom_circuit,
    any_value(pays_circuit)                 as pays,
    any_value(ville_circuit)                as ville,
    min(saison)                             as premiere_saison,
    max(saison)                             as derniere_saison,
    count(distinct saison || '-' || manche) as nb_courses
from resultats
group by circuit_id
