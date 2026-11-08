-- One row per constructor.
with resultats as (
    select * from {{ ref('stg_resultats') }}
),
dernier as (
    select *, row_number() over (
        partition by ecurie_id order by saison desc, manche desc
    ) as rang
    from resultats
)
select
    d.ecurie_id,
    d.nom_ecurie,
    d.nationalite_ecurie,
    min(r.saison)                                     as premiere_saison,
    max(r.saison)                                     as derniere_saison,
    count(distinct r.saison)                          as nb_saisons,
    count(*)                                          as nb_engagements,
    count(*) filter (where r.position_classement = 1)    as nb_victoires,
    count(*) filter (where r.position_classement <= 3)   as nb_podiums,
    round(sum(r.points), 1)                           as points_cumules,
    count(distinct r.pilote_id)                       as nb_pilotes
from dernier d
join resultats r on r.ecurie_id = d.ecurie_id
where d.rang = 1
group by d.ecurie_id, d.nom_ecurie, d.nationalite_ecurie
