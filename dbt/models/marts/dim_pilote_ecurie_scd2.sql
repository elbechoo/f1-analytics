-- Type 2 dimension: one row per continuous spell a driver spent at a team.
--
-- Why this is built from history rather than with `dbt snapshot`
-- ---------------------------------------------------------------
-- A dbt snapshot records changes it observes BETWEEN RUNS. Run once, it
-- captures only today's state; the seventy-five years of team changes
-- already sitting in the source would never appear. Snapshots are the right
-- tool when the source overwrites itself and history would otherwise be
-- lost - which is not this case.
--
-- Here the history is already in the data, so the Type 2 structure is
-- derived from it: gaps-and-islands over each driver's races, opening a new
-- row whenever the constructor changes.
--
-- Drivers return to teams (Alonso at Renault twice, Hamilton to Ferrari),
-- so a spell is keyed by driver AND sequence, not driver and team.

with courses as (

    select
        r.pilote_id,
        r.ecurie_id,
        r.saison,
        r.manche,
        r.date_course
    from {{ ref('fct_resultat') }} r

),

marque as (

    select
        *,
        -- 1 on the race where the driver's team differs from the previous
        -- race. lag over the driver's own chronology, so a return to a
        -- former team opens a new spell rather than reopening the old one.
        case
            when lag(ecurie_id) over (
                     partition by pilote_id order by saison, manche
                 ) is distinct from ecurie_id
            then 1 else 0
        end as debut_periode
    from courses

),

numerote as (

    select
        *,
        sum(debut_periode) over (
            partition by pilote_id order by saison, manche
            rows between unbounded preceding and current row
        ) as no_periode
    from marque

),

periodes as (

    select
        pilote_id,
        ecurie_id,
        no_periode,
        min(date_course)    as valide_de,
        max(date_course)    as derniere_course,
        min(saison)         as saison_debut,
        max(saison)         as saison_fin,
        count(*)            as nb_courses
    from numerote
    group by pilote_id, ecurie_id, no_periode

)

select
    {{ dbt_utils.generate_surrogate_key(['pilote_id', 'no_periode']) }} as periode_id,
    p.pilote_id,
    p.ecurie_id,
    p.no_periode,
    p.valide_de,
    -- valide_jusqu_a is the day before the next spell starts, so the ranges
    -- tile the driver's career without overlapping. The current spell is
    -- left open rather than closed at today's date: a closed range would
    -- claim the driver left, which is a different fact.
    lead(p.valide_de) over (
        partition by p.pilote_id order by p.no_periode
    ) - interval 1 day                                  as valide_jusqu_a,
    lead(p.valide_de) over (
        partition by p.pilote_id order by p.no_periode
    ) is null                                           as est_periode_courante,
    p.saison_debut,
    p.saison_fin,
    p.derniere_course,
    p.nb_courses
from periodes p
