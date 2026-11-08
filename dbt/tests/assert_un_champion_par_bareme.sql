-- Every season, under every scoring system, must produce exactly one driver
-- at rank 1.
--
-- Fewer than one means a season produced no ranking at all, which happens if
-- a season's results were all outside the scoring positions of that system
-- and the join dropped them silently. More than one means the row_number
-- partition is wrong and the downstream "does the champion change" model is
-- counting ghosts.

select
    systeme,
    saison,
    count(*) as nb_en_tete
from {{ ref('fct_championnat_contrefactuel') }}
where rang = 1
group by 1, 2
having count(*) <> 1
