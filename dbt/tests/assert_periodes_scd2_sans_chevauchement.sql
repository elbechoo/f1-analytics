-- A driver cannot be at two teams on the same day.
--
-- The whole value of a Type 2 dimension is that "who did X drive for on
-- date D" has exactly one answer. Overlapping validity ranges silently
-- double every metric joined through it, and nothing else would catch it.
select
    a.pilote_id,
    a.ecurie_id    as ecurie_a,
    b.ecurie_id    as ecurie_b,
    a.valide_de    as debut_a,
    a.valide_jusqu_a as fin_a,
    b.valide_de    as debut_b
from {{ ref('dim_pilote_ecurie_scd2') }} a
join {{ ref('dim_pilote_ecurie_scd2') }} b
  on  b.pilote_id  = a.pilote_id
  and b.no_periode > a.no_periode
where b.valide_de <= coalesce(a.valide_jusqu_a, date '9999-12-31')
