{{ config(severity = 'warn') }}

-- The whole claim of the strength model is that the teammate graph is one
-- chain running from 1950 to now. If the main connected component stops
-- holding most of the rankable drivers, that claim has quietly stopped being
-- true and the ratings are no longer on a single scale.
--
-- Warn rather than error: a newly fetched season can briefly add an isolated
-- driver, and that is not a reason to fail a build. It is a reason to look.

with repartition as (

    select
        count(*) filter (where dans_composante_principale and nb_duels >= 40)
            as principale,
        count(*) filter (where nb_duels >= 40)
            as total
    from {{ ref('fct_force_pilote') }}

)

select
    principale,
    total,
    principale::double / nullif(total, 0) as part
from repartition
where principale::double / nullif(total, 0) < 0.90
