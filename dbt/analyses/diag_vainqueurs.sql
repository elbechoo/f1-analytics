select saison, manche, count(*) as nb_vainqueurs,
       string_agg(pilote_id, ' + ') as pilotes,
       string_agg(distinct ecurie_id, ' + ') as ecuries,
       string_agg(distinct statut, ' | ') as statuts
from main_marts.fct_resultat
where est_victoire
group by saison, manche
having count(*) <> 1
order by saison, manche
