-- Why are there duplicate (season, round, driver) rows?
--
-- Two candidate causes needing opposite fixes:
--   real     - a driver drove two cars in one race (shared drives, pre-1960)
--   corrupt  - the fetcher re-fetched a season and appended duplicate pages
--
-- If the duplicates have DIFFERENT constructors, it is real.
-- If they are byte-identical, the ingestion duplicated them.
--
--   ..\.venv\Scripts\python -c "import duckdb;con=duckdb.connect('f1.duckdb',read_only=True);[print(r) for r in con.execute(open('dbt/analyses/diag_doublons.sql').read().split(';')[0]).fetchall()]"

select
    saison,
    count(*)                                        as nb_doublons,
    count(distinct ecurie_id)                       as ecuries_distinctes,
    string_agg(distinct pilote_id, ', ')            as pilotes
from (
    select saison, manche, pilote_id, ecurie_id,
           count(*) over (partition by saison, manche, pilote_id) as n
    from main_staging.stg_resultats
)
where n > 1
group by saison
order by saison
