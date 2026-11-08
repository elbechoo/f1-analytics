-- One example in full: same driver, same race, what differs?
select saison, manche, pilote_id, ecurie_id, position_classement,
       position_texte, points, tours_couverts, statut
from main_staging.stg_resultats
where (saison, manche, pilote_id) in (
    select saison, manche, pilote_id
    from main_staging.stg_resultats
    group by saison, manche, pilote_id
    having count(*) > 1
)
order by saison, manche, pilote_id
limit 12
