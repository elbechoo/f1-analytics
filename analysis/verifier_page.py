"""Check the rendered page against the warehouse it claims to describe.

Every other test in this project asserts something about the data. None of
them assert anything about the page, and three wrong numbers reached the
published site through that gap in a single afternoon:

  * a duel count printed at twice its true value, because dividing in DuckDB
    returns a double and the formatter passed it through
  * a championship position computed by a subquery that counted a driver's
    own result rows instead of the drivers ahead of them
  * a format placeholder that resolved to a Python function object, whose
    repr contains angle brackets, so the browser read it as a tag and showed
    nothing at all

The third is the one worth dwelling on. A visibly broken page is a cheap
failure. A blank where a number should be is an expensive one, because it
looks like a design choice.

Run after build_dashboard.py and before publishing. Exits non-zero with a
list of what is wrong.

    python analysis/verifier_page.py
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "dashboard" / "index.html"
DB = ROOT / "f1.duckdb"

# Thin space, which is what the number formatter groups with.
FIN = " "


def texte(h: str) -> str:
    """The page as a reader sees it: tags stripped, entities resolved."""
    return html.unescape(re.sub(r"<[^>]+>", " ", h))


def verifier(h: str, con) -> list[str]:
    fautes: list[str] = []

    def exiger(condition, message):
        if not condition:
            fautes.append(message)

    lisible = texte(h)

    # --- things that must never appear ------------------------------------
    for motif, quoi in [
        (r"<function\s|<bound method|object at 0x", "a Python repr"),
        (r"\bNone\b", "the literal None"),
        (r"\bnan\b|\bNaN\b", "a NaN"),
        (r"\{[a-z_]+\}", "an unsubstituted format placeholder"),
    ]:
        for m in set(re.findall(motif, h)):
            fautes.append(f"page contains {quoi}: {m!r}")

    # Em dashes are a house rule for this project, checked rather than hoped.
    # chr() rather than the character itself, so that grepping the repository
    # for an em dash finds the offending copy rather than this check.
    exiger(chr(0x2014) not in h, "page contains an em dash")

    # --- the headline tiles must match the warehouse ----------------------
    # This is the check that would have caught the doubled duel count. The
    # page is not asked to be internally consistent, it is asked to agree
    # with the database it was built from.
    attendu = {
        "RACE RESULTS LOADED":
            "select count(*) from main_marts.fct_resultat",
        "GRANDS PRIX":
            "select count(*) from main_marts.dim_course",
        "DRIVERS":
            "select count(*) from main_marts.dim_pilote",
        "CONSTRUCTORS":
            "select count(*) from main_marts.dim_ecurie",
        "TEAM MATE DUELS FITTED":
            "select (count(*) / 2)::bigint from main_marts.fct_duel_coequipiers",
        "SCD2 PERIODS":
            "select count(*) from main_marts.dim_pilote_ecurie_scd2",
    }
    for etiquette, sql in attendu.items():
        trouve = re.search(
            r'class="val"[^>]*>([^<]+)</div>\s*<div class="et">' + re.escape(etiquette),
            h,
        )
        if not trouve:
            fautes.append(f"tile missing from the page: {etiquette}")
            continue
        affiche = trouve.group(1).replace(FIN, "").strip()
        exiger(
            affiche.isdigit(),
            f"tile {etiquette} is not a plain integer: {trouve.group(1)!r}",
        )
        if affiche.isdigit():
            reel = con.execute(sql).fetchone()[0]
            exiger(
                int(affiche) == int(reel),
                f"tile {etiquette} says {affiche}, warehouse says {reel}",
            )

    # --- the race pace table ----------------------------------------------
    pace = re.search(r'<span id="rythme">.*?<span id="bareme">', h, re.S)
    if not pace:
        fautes.append("the race pace section is missing")
    else:
        bloc = pace.group(0)

        # Ranks must be distinct. A subquery that returns the same number for
        # everyone is the exact shape of the bug this replaces, and it is
        # invisible to the eye once the list is long enough.
        rangs = [int(x) for x in re.findall(r"P(\d+) on points", bloc)]
        exiger(rangs, "no championship positions in the pace section")
        exiger(
            len(rangs) == len(set(rangs)),
            f"championship positions repeat: {sorted(rangs)}",
        )
        exiger(all(r >= 1 for r in rangs), "a championship position below 1")

        # Race counts must be present and positive. The function-object bug
        # left this blank, and a blank reads as deliberate.
        courses = [int(x) for x in re.findall(r"&middot; (\d+) races", bloc)]
        exiger(
            len(courses) == len(rangs),
            f"{len(rangs)} drivers listed but {len(courses)} race counts",
        )
        exiger(all(c > 0 for c in courses), "a race count of zero")

        # The table claims to be sorted by deficit, so it had better be.
        ecarts = [float(x) for x in re.findall(r"\+(\d+\.\d+)%", bloc)]
        exiger(
            ecarts == sorted(ecarts),
            "the pace table is not sorted by deficit",
        )

    # --- navigation ---------------------------------------------------------
    # A nav link to a section that does not exist is a dead click, and the
    # section numbering has been renumbered by hand several times.
    ancres = set(re.findall(r'<span id="([a-z0-9]+)"', h)) | set(
        re.findall(r'<header class="hero" id="([a-z0-9]+)"', h))
    for cible in re.findall(r'<a href="#([a-z0-9]+)"', h):
        exiger(cible in ancres, f"nav links to #{cible}, which does not exist")

    # --- names must be real -------------------------------------------------
    # Catches a join that silently produced an id where a name belongs.
    pilotes = {r[0] for r in
               con.execute("select nom_complet from main_marts.dim_pilote").fetchall()}
    for nom in re.findall(r'class="fo-n">([^<]+)<', h):
        exiger(nom.strip() in pilotes,
               f"driver name on the page is not in dim_pilote: {nom.strip()!r}")

    # --- the page is not empty ----------------------------------------------
    exiger(len(lisible) > 4000, "the page has suspiciously little text on it")

    return fautes


def main() -> None:
    if not PAGE.exists():
        print(f"no page at {PAGE}; run build_dashboard.py first", file=sys.stderr)
        raise SystemExit(1)

    h = PAGE.read_text(encoding="utf-8")
    con = duckdb.connect(str(DB), read_only=True)
    try:
        fautes = verifier(h, con)
    finally:
        con.close()

    if fautes:
        print(f"{len(fautes)} problem(s) with the rendered page:", file=sys.stderr)
        for f in fautes:
            print(f"  - {f}", file=sys.stderr)
        raise SystemExit(1)

    print("page checks passed")


if __name__ == "__main__":
    main()
