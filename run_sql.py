"""Run a .sql file against the warehouse and print the rows.

Exists because passing SQL inline through PowerShell mangles quoting often
enough to waste more time than a three-line script costs.

    python run_sql.py dbt/analyses/diag_vainqueurs.sql
"""
import sys
from pathlib import Path

import duckdb

requete = Path(sys.argv[1]).read_text(encoding="utf-8")
con = duckdb.connect("f1.duckdb", read_only=True)
cur = con.execute(requete)
colonnes = [d[0] for d in cur.description]
lignes = cur.fetchall()
print(" | ".join(colonnes))
print("-" * 80)
for l in lignes:
    print(" | ".join("" if v is None else str(v) for v in l))
print(f"\n{len(lignes)} row(s)")
con.close()
