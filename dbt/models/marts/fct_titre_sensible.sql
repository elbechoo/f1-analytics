-- Grain: one season.
--
-- Reads the rescored championships and asks a single question of each season:
-- does the driver at the top of the table survive a change of scoring system?
--
-- A season where all five systems agree was decided by a margin wide enough
-- that the rulebook was irrelevant. A season where they disagree was close
-- enough that the shape of the points curve chose the champion. That is a
-- property of the season, not of any driver, and it is the kind of thing a
-- plain wins-and-points table cannot show.

with classements as (

    select
        c.*,
        p.nom_complet
    from {{ ref('fct_championnat_contrefactuel') }} c
    join {{ ref('dim_pilote') }} p using (pilote_id)
    where c.rang = 1

),

par_saison as (

    select
        saison,
        count(distinct pilote_id)                       as nb_champions_possibles,
        count(*)                                        as nb_systemes,
        min(avance_sur_suivant)                         as marge_mini,
        max(avance_sur_suivant)                         as marge_maxi,
        string_agg(distinct nom_complet, ' / ' order by nom_complet)
                                                        as champions_possibles
    from classements
    group by 1

),

reel as (

    -- The system actually in force that season, so the table can show the
    -- champion of record next to the alternatives.
    select
        c.saison,
        c.pilote_id                                     as champion_id,
        c.nom_complet                                   as champion_du_jour
    from classements c
    where c.systeme = (
        select max(s.systeme)
        from {{ ref('fct_championnat_contrefactuel') }} s
        where s.saison = c.saison
          and s.systeme_depuis <= c.saison
    )

)

select
    p.saison,
    p.nb_systemes,
    p.nb_champions_possibles,
    p.nb_champions_possibles > 1                        as titre_depend_du_bareme,
    p.champions_possibles,
    r.champion_id,
    r.champion_du_jour,
    p.marge_mini,
    p.marge_maxi
from par_saison p
left join reel r using (saison)
order by p.saison
