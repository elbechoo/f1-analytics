"""Print the headline numbers, so documentation quotes the warehouse.

A README with figures typed in by hand goes stale the first time the data
changes and nobody notices, because nothing checks it. This prints the
current values in one block, ready to paste.

    python analysis/chiffres.py
"""
from __future__ import annotations

from pathlib import Path

import duckdb

DB = Path(__file__).resolve().parent.parent / "f1.duckdb"


REQUETES = [
    ("resultats",  "select count(*) from main_marts.fct_resultat"),
    ("saison_min", "select min(saison) from main_marts.dim_course"),
    ("saison_max", "select max(saison) from main_marts.dim_course"),
    ("courses",    "select count(*) from main_marts.dim_course"),
    ("pilotes",    "select count(*) from main_marts.dim_pilote"),
    ("ecuries",    "select count(*) from main_marts.dim_ecurie"),
    # Two rows per duel, one per driver, so the row count is twice the
    # number of duels. Dividing here rather than in the caller, because a
    # figure that needs a mental correction before use will eventually be
    # quoted without it.
    ("duels",      "select count(*) / 2 from main_marts.fct_duel_coequipiers"),
    ("scd2",       "select count(*) from main_marts.dim_pilote_ecurie_scd2"),
    ("classables", "select count(*) from main_marts.fct_force_pilote "
                   "where classable"),
    ("paires_cal", "select count(*) from main_marts.fct_calibration_duel"),
    ("erreur_moy", "select round(avg(ecart), 4) from main_marts.fct_calibration_duel"),
    ("pire_ecart", "select round(max(ecart), 4) from main_marts.fct_calibration_duel"),
    # The late-career bias the warn test watches. Printed whether or not it
    # trips, because "the test did not fire" is not the same as "there is no
    # bias" and the README should quote the number rather than the verdict.
    ("biais_paires",
     "select count(*) from main_marts.fct_calibration_duel "
     "where greatest(anciennete_a, anciennete_b) >= 8 "
     "  and abs(anciennete_a - anciennete_b) >= 4"),
    ("biais_moyen",
     "select round(avg(case when anciennete_a >= anciennete_b then residu "
     "                      else -residu end), 4) "
     "from main_marts.fct_calibration_duel "
     "where greatest(anciennete_a, anciennete_b) >= 8 "
     "  and abs(anciennete_a - anciennete_b) >= 4"),
    ("biais_top10",
     "select round(avg(case when anciennete_a >= anciennete_b then residu "
     "                      else -residu end), 4) from ("
     "  select * from main_marts.fct_calibration_duel "
     "  order by ecart desc limit 10)"),
    ("saisons_basculantes",
     "select count(*) from main_marts.fct_titre_sensible "
     "where titre_depend_du_bareme"),
    ("saisons_total", "select count(*) from main_marts.fct_titre_sensible"),
    ("part_voiture_moy",
     "select round(avg(part_ecurie), 3) from main_marts.fct_part_voiture"),
    ("part_voiture_recente",
     "select round(avg(part_ecurie), 3) from main_marts.fct_part_voiture "
     "where saison >= 2014"),
    ("part_voiture_ancienne",
     "select round(avg(part_ecurie), 3) from main_marts.fct_part_voiture "
     "where saison < 1980"),
]


def main() -> None:
    con = duckdb.connect(str(DB), read_only=True)
    try:
        for nom, sql in REQUETES:
            try:
                print(f"{nom:24} {con.execute(sql).fetchone()[0]}")
            except Exception as exc:                      # noqa: BLE001
                print(f"{nom:24} ERROR  {type(exc).__name__}: {exc}")

        print("\ntop 8 by fitted strength")
        for nom, note, b, h, nd in con.execute("""
            select p.nom_complet, round(f.note), round(f.note_basse),
                   round(f.note_haute), f.nb_duels
            from main_marts.fct_force_pilote f
            join main_marts.dim_pilote p using (pilote_id)
            where f.classable order by f.note desc limit 8""").fetchall():
            print(f"  {nom:28} {note:.0f}  [{b:.0f}, {h:.0f}]  {nd:.0f} duels")

        print("\nseasons where the scoring system changes the champion")
        for s, ch, poss in con.execute("""
            select saison, champion_du_jour, champions_possibles
            from main_marts.fct_titre_sensible
            where titre_depend_du_bareme order by saison desc limit 10""").fetchall():
            print(f"  {s}  {ch}  ->  {poss}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
