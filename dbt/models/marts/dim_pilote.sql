-- One row per driver who has started at least one race.
--
-- Names, nationality and date of birth are taken from the most recent result
-- rather than the first: the API occasionally corrects a record, and the
-- latest version is the one to trust.
with resultats as (
    select * from {{ ref('stg_resultats') }}
),

dernier as (
    select *, row_number() over (
        partition by pilote_id order by saison desc, manche desc
    ) as rang
    from resultats
)

select
    d.pilote_id,
    d.prenom_pilote || ' ' || d.nom_pilote           as nom_complet,
    d.nom_pilote,
    d.prenom_pilote,
    d.code_pilote,
    d.nationalite_pilote,
    d.naissance_pilote,
    min(r.saison)                                     as premiere_saison,
    max(r.saison)                                     as derniere_saison,
    count(distinct r.saison)                          as nb_saisons,
    count(*)                                          as nb_departs,
    count(*) filter (where r.position_classement = 1)    as nb_victoires,
    count(*) filter (where r.position_classement <= 3)   as nb_podiums,
    count(*) filter (where r.position_grille = 1)     as nb_poles,
    round(sum(r.points), 1)                           as points_carriere,
    count(distinct r.ecurie_id)                       as nb_ecuries
from dernier d
join resultats r on r.pilote_id = d.pilote_id
where d.rang = 1
group by d.pilote_id, d.prenom_pilote, d.nom_pilote, d.code_pilote,
         d.nationalite_pilote, d.naissance_pilote
