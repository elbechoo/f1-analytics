-- Every drive carries a classification position, finished or not.
--
-- This replaces an earlier test that asserted the opposite - that retirements
-- have no position - which failed on 9,719 rows because the assumption was
-- wrong. `position` is the classification order and is always populated;
-- `positionText` is what says whether the car took the flag.
--
-- Keeping a corrected version rather than deleting the test: the invariant is
-- real and worth guarding, it was just stated backwards the first time.
select saison, manche, pilote_id, position_texte, statut
from {{ ref('fct_resultat') }}
where position_classement is null
