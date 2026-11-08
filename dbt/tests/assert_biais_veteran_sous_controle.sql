{{ config(severity = 'warn') }}

-- The known blind spot, watched rather than hidden.
--
-- Bradley-Terry here fits one strength per driver for an entire career. A
-- driver is therefore scored in their last season with a rating earned at
-- their peak, and pairings late in a veteran's career are predicted in the
-- veteran's favour more often than the results justify. The residuals from
-- the first full run showed exactly that, every large one of them a late
-- career pairing, and every one of them over-rating the older driver.
--
-- That is a property of the model, not a defect in the data, so failing the
-- build over it would be wrong. Leaving it undocumented would be worse: it
-- is the single thing most likely to make a number on the dashboard
-- misleading. So it warns, with the current size of the bias attached, and
-- whoever reads the build output sees how big it is today.
--
-- If this warning ever disappears, the model has started handling career
-- trajectory, and the comment above needs rewriting.

with tardives as (

    -- Pairings beginning well into at least one driver's career, with the
    -- residual signed so that positive means the model favoured the more
    -- senior driver more than the results did.
    select
        case
            when anciennete_a >= anciennete_b then  residu
            else                                   -residu
        end as residu_vers_le_veteran
    from {{ ref('fct_calibration_duel') }}
    where greatest(anciennete_a, anciennete_b) >= 8
      and abs(anciennete_a - anciennete_b)     >= 4

)

select
    count(*)                              as nb_paires_tardives,
    round(avg(residu_vers_le_veteran), 4) as biais_moyen
from tardives
having count(*) >= 5
   and avg(residu_vers_le_veteran) > 0.05
