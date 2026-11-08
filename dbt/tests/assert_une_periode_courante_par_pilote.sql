-- Exactly one open spell per driver. Two open ranges means the lead() that
-- closes them is wrong, and every point-in-time join would return duplicates.
select pilote_id, count(*) as nb_ouvertes
from {{ ref('dim_pilote_ecurie_scd2') }}
where est_periode_courante
group by pilote_id
having count(*) <> 1
