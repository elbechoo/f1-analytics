{{ config(severity = 'warn') }}

-- Shared victories should stay rare and historical.
--
-- Severity warn, not error: this is a sanity check on the shape of history
-- rather than an invariant. Three races until 1957, none after - the rule
-- changed in 1958. A shared win appearing in a modern season would mean the
-- grain broke somewhere, and this surfaces it in the build output instead of
-- leaving it to be noticed by accident.
select saison, manche, count(*) as nb_vainqueurs,
       string_agg(pilote_id, ' + ') as pilotes
from {{ ref('fct_resultat') }}
where est_victoire
group by saison, manche
having count(*) > 1
   and max(saison) > 1960
