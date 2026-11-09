"""Fetch Formula 1 data from the Jolpica API into DuckDB.

Source: https://api.jolpi.ca/ergast/f1 - the maintained successor to Ergast,
which was retired after the 2024 season. Same response shape, so the old
Ergast documentation still applies.

Three constraints shape this script, and they are the interesting part:

1. The API caps `limit` at 100 regardless of what you ask for. One race's lap
   timings is roughly 1,100 records, so a single race costs ~12 requests.

2. Unauthenticated callers get 500 requests/hour. A full history of results,
   qualifying, pit stops and laps is well past that, so a naive loop dies
   partway through and leaves a half-populated database.

3. Therefore this is RESUMABLE. Every response is written to DuckDB as it
   arrives and a progress table records which (endpoint, season, round) pairs
   are done. Re-running skips finished work, so hitting the rate limit is an
   interruption rather than a failure - stop it, run it again tomorrow, and it
   carries on.

Usage
    python ingest/fetch_f1.py                      # default scope
    python ingest/fetch_f1.py --laps-from 2023     # more lap history
    python ingest/fetch_f1.py --only results       # one endpoint
    python ingest/fetch_f1.py --status             # what is already fetched
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import duckdb
import requests

BASE = "https://api.jolpi.ca/ergast/f1"
ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "f1.duckdb"

PAGE = 100          # the API's hard ceiling; asking for more is ignored
PAUSE = 0.30        # ~3 req/s, under the 4/s burst limit
MAX_RETRIES = 5


class RateLimited(Exception):
    pass


class Injoignable(Exception):
    """The API could not be reached at all, as opposed to refusing us."""


def get(session: requests.Session, chemin: str, offset: int = 0) -> dict:
    """One GET with backoff on 429, on 5xx, and on the network itself.

    Retries double the wait each time. A 429 that survives five retries is
    the hourly quota rather than a burst, and no amount of waiting inside one
    run will fix it - so it raises and the caller stops cleanly, leaving the
    progress table intact for the next run.

    Connection failures are retried the same way and were not, originally.
    A DNS lookup failing for a few seconds midway through a long fetch is
    ordinary, and it used to escape as a raw requests exception: a forty-line
    traceback for a blip the loader could have slept through. Treating "I
    could not reach the server" as a different thing from "the server said
    no" is the point, because only one of them is worth stopping for.
    """
    url = f"{BASE}/{chemin}?limit={PAGE}&offset={offset}"
    attente = 2.0
    for essai in range(MAX_RETRIES):
        try:
            r = session.get(url, timeout=60)
        except requests.exceptions.RequestException as exc:
            if essai == MAX_RETRIES - 1:
                raise Injoignable(f"{type(exc).__name__} after "
                                  f"{MAX_RETRIES} tries: {url}") from exc
            time.sleep(attente)
            attente *= 2
            continue
        if r.status_code == 200:
            time.sleep(PAUSE)
            return r.json()["MRData"]
        if r.status_code in (429, 500, 502, 503, 504):
            if essai == MAX_RETRIES - 1:
                raise RateLimited(f"{r.status_code} after {MAX_RETRIES} tries: {url}")
            time.sleep(attente)
            attente *= 2
            continue
        r.raise_for_status()
    raise RateLimited(url)


def pages(session: requests.Session, chemin: str):
    """Yield every page of a paginated endpoint."""
    offset = 0
    while True:
        data = get(session, chemin, offset)
        yield data
        total = int(data["total"])
        offset += PAGE
        if offset >= total:
            return


# --------------------------------------------------------------- storage ---

def init_db(con) -> None:
    """Raw JSON, one row per API response.

    Responses are stored whole rather than shredded into columns here. The
    shredding is dbt's job, where it is visible and tested; a loader that
    reshapes data is a loader that silently loses some.
    """
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute("""
        CREATE TABLE IF NOT EXISTS raw.reponses (
            endpoint   VARCHAR,
            saison     INTEGER,
            manche     INTEGER,
            offset_    INTEGER,
            recupere_a TIMESTAMP,
            charge     JSON
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS raw.progression (
            endpoint   VARCHAR,
            saison     INTEGER,
            manche     INTEGER,
            n_lignes   INTEGER,
            termine_a  TIMESTAMP,
            PRIMARY KEY (endpoint, saison, manche)
        )
    """)


def deja_fait(con, endpoint: str, saison: int, manche: int) -> bool:
    return con.execute(
        "select count(*) from raw.progression "
        "where endpoint = ? and saison = ? and manche = ?",
        [endpoint, saison, manche],
    ).fetchone()[0] > 0


def enregistrer(con, endpoint, saison, manche, offset, charge) -> None:
    con.execute(
        "insert into raw.reponses values (?, ?, ?, ?, now(), ?)",
        [endpoint, saison, manche, offset, json.dumps(charge)],
    )


def marquer(con, endpoint, saison, manche, n) -> None:
    con.execute(
        "insert or replace into raw.progression values (?, ?, ?, ?, now())",
        [endpoint, saison, manche, n],
    )


# ---------------------------------------------------------------- fetching ---

def fetch_saison(con, session, endpoint: str, saison: int) -> int:
    """Season-level endpoint: results, qualifying, driverstandings..."""
    if deja_fait(con, endpoint, saison, -1):
        return 0
    total = 0
    for data in pages(session, f"{saison}/{endpoint}/"):
        enregistrer(con, endpoint, saison, -1, total, data)
        total += PAGE
    n = int(data["total"])
    marquer(con, endpoint, saison, -1, n)
    return n


def fetch_manche(con, session, endpoint: str, saison: int, manche: int) -> int:
    """Round-level endpoint: laps, pitstops."""
    if deja_fait(con, endpoint, saison, manche):
        return 0
    total = 0
    for data in pages(session, f"{saison}/{manche}/{endpoint}/"):
        enregistrer(con, endpoint, saison, manche, total, data)
        total += PAGE
    n = int(data["total"])
    marquer(con, endpoint, saison, manche, n)
    return n


def manches_de(con, session, saison: int) -> int:
    """How many rounds a season has. Cheap, and cached in progression."""
    data = get(session, f"{saison}/races/")
    return len(data["RaceTable"]["Races"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="debut", type=int, default=1950,
                    help="First season for season-level endpoints.")
    # Not a hard-coded year: a scheduled run in January must pick up the new
    # season on its own, without someone remembering to edit this file.
    ap.add_argument("--to", dest="fin", type=int, default=date.today().year,
                    help="Last season. Defaults to the current calendar year.")
    ap.add_argument("--refresh-from", type=int, metavar="SAISON",
                    help="Forget what was already fetched from this season on, so "
                         "it is pulled again. A season in progress is marked done "
                         "the first time it is fetched and would otherwise freeze "
                         "at whatever round had been run that day. A scheduled job "
                         "passes the current year here.")
    ap.add_argument("--laps-from", type=int, default=2023,
                    help="First season to fetch lap times for, through --to. "
                         "A race is ~1,100 timings and the API pages at 100, so "
                         "each race costs ~12 requests: 2023-2026 is roughly "
                         "1,100 calls. Past the 500/hour limit, hence resumable.")
    ap.add_argument("--pits-from", type=int, default=2023,
                    help="First season to fetch pit stops for (1 request per race).")
    ap.add_argument("--only", choices=["results", "qualifying", "driverstandings",
                                       "constructorstandings", "pitstops", "laps"],
                    help="Fetch a single endpoint.")
    ap.add_argument("--status", action="store_true",
                    help="Show what has already been fetched and exit.")
    args = ap.parse_args()

    con = duckdb.connect(str(DB))
    init_db(con)

    if args.refresh_from is not None:
        # Drop the stored pages too, not just the progress marker. Re-fetching
        # on top of the old rows would leave two versions of the same round in
        # raw.reponses and silently double every result in the staging unnest.
        oublie = con.execute(
            "select count(*) from raw.progression where saison >= ?",
            [args.refresh_from]).fetchone()[0]
        con.execute("delete from raw.reponses   where saison >= ?", [args.refresh_from])
        con.execute("delete from raw.progression where saison >= ?", [args.refresh_from])
        print(f"refresh: forgot {oublie} fetched unit(s) from "
              f"{args.refresh_from} on, they will be pulled again")

    if args.status:
        lignes = con.execute("""
            select endpoint, count(*) as appels, sum(n_lignes) as lignes,
                   min(saison) as de, max(saison) as a
            from raw.progression group by endpoint order by endpoint
        """).fetchall()
        if not lignes:
            print("nothing fetched yet")
        for e, appels, n, de, a in lignes:
            print(f"  {e:<22} {appels:>5} calls  {n or 0:>8,} rows  {de}-{a}".replace(",", " "))
        con.close()
        return

    session = requests.Session()
    session.headers["User-Agent"] = "f1-analytics (github.com/elbechoo)"

    saison_endpoints = ["results", "qualifying", "driverstandings", "constructorstandings"]
    if args.only in saison_endpoints:
        saison_endpoints = [args.only]
    elif args.only:
        saison_endpoints = []

    try:
        for endpoint in saison_endpoints:
            print(f"\n{endpoint}")
            for saison in range(args.debut, args.fin + 1):
                n = fetch_saison(con, session, endpoint, saison)
                if n:
                    print(f"  {saison}  {n:>5} rows")

        for endpoint, depuis in (("pitstops", args.pits_from), ("laps", args.laps_from)):
            if args.only and args.only != endpoint:
                continue
            print(f"\n{endpoint} (from {depuis})")
            for saison in range(depuis, args.fin + 1):
                nb = manches_de(con, session, saison)
                total_saison = 0
                for manche in range(1, nb + 1):
                    total_saison += fetch_manche(con, session, endpoint, saison, manche)
                print(f"  {saison}  {nb} rounds, {total_saison:>6} rows")

    except RateLimited as exc:
        print(f"\nrate limited: {exc}", file=sys.stderr)
        print("Progress is saved. Re-run this command later and it will "
              "continue from where it stopped.", file=sys.stderr)
        con.close()
        raise SystemExit(2)
    except Injoignable as exc:
        # A different exit code from the rate limit, because they call for
        # different responses: one means wait an hour, the other means check
        # the network and try again now. The scheduled job only tolerates 2.
        print(f"\ncannot reach the API: {exc}", file=sys.stderr)
        print("Progress is saved. Check the connection and re-run; it will "
              "continue from where it stopped.", file=sys.stderr)
        con.close()
        raise SystemExit(3)
    except KeyboardInterrupt:
        print("\ninterrupted - progress saved, re-run to continue", file=sys.stderr)
        con.close()
        raise SystemExit(130)

    total = con.execute("select coalesce(sum(n_lignes), 0) from raw.progression").fetchone()[0]
    appels = con.execute("select count(*) from raw.reponses").fetchone()[0]
    con.close()
    print(f"\ndone: {total:,} rows from {appels:,} API calls".replace(",", " "))


if __name__ == "__main__":
    main()
