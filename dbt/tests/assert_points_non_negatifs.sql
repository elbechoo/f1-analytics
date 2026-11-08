-- Points are never negative. They were deducted exactly once in F1 history
-- (Tyrrell, 1984) and that is recorded as disqualification, not a negative
-- score, so a negative here means a parsing error rather than a fact.
select saison, manche, pilote_id, points
from {{ ref('fct_resultat') }}
where points < 0
