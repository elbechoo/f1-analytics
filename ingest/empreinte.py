"""Print a fingerprint of the current season's stored results.

Used by the scheduled job to decide whether anything actually changed. During
a race weekend the job runs every half hour, and on all but one or two of
those runs the source has published nothing new. Rebuilding the warehouse,
refitting the model and redeploying the page anyway would burn several minutes
of compute to produce a byte-identical page.

The fingerprint is a hash of the stored payloads for the season, not a row
count: a race whose results are later amended, a penalty applied on Monday,
changes the content without changing the number of rows, and a count would
miss it.

    python ingest/empreinte.py          # current year
    python ingest/empreinte.py 2025
"""
from __future__ import annotations

import hashlib
import sys
from datetime import date
from pathlib import Path

import duckdb

DB = Path(__file__).resolve().parent.parent / "f1.duckdb"


def main() -> None:
    saison = int(sys.argv[1]) if len(sys.argv) > 1 else date.today().year

    if not DB.exists():
        # No warehouse yet is a real difference from any previous state, so
        # emit something that cannot collide with a real fingerprint.
        print("absent")
        return

    con = duckdb.connect(str(DB), read_only=True)
    try:
        tables = con.execute(
            "select count(*) from information_schema.tables "
            "where table_schema = 'raw' and table_name = 'reponses'"
        ).fetchone()[0]
        if not tables:
            print("vide")
            return

        lignes = con.execute(
            "select endpoint, manche, offset_, charge "
            "from raw.reponses where saison = ? "
            "order by endpoint, manche, offset_",
            [saison],
        ).fetchall()
    finally:
        con.close()

    if not lignes:
        print("vide")
        return

    h = hashlib.sha256()
    for endpoint, manche, offset, charge in lignes:
        h.update(f"{endpoint}|{manche}|{offset}|".encode())
        h.update(str(charge).encode())
    print(h.hexdigest())


if __name__ == "__main__":
    main()
