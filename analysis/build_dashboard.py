"""Render the race-data dashboard as one self-contained HTML file.

No bundler, no server, no chart library: open it from disk or from a Pages URL
and it works. Every chart is SVG written by hand here, so the output is text
that git can diff and there is nothing to install. The only external request is
the webfont stylesheet; without a network the page falls back to system faces
and still reads correctly.

    python analysis/build_dashboard.py
"""
from __future__ import annotations
import html
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "f1.duckdb"
OUT = ROOT / "dashboard" / "index.html"

TEAM = {
 "mercedes":"#00d7b6","ferrari":"#ff2800","red_bull":"#3671f5","mclaren":"#ff8000",
 "alpine":"#00a8e8","aston_martin":"#00897b","williams":"#2f55d4","rb":"#6692ff",
 "sauber":"#00e701","haas":"#d0d4d8","alfa":"#c01212","lotus":"#00703c",
 "brabham":"#5ad17f","renault":"#ffe800","benetton":"#00a0de","tyrrell":"#2a7de1",
 "brawn":"#b8fd6e","cooper":"#2fae68","vanwall":"#0e8a52","maserati":"#4a84d6",
 "matra":"#2a68cc","jordan":"#f5c518","toro_rosso":"#5a76e0","force_india":"#ff7fd0",
 "audi":"#bb0a30","cadillac":"#c9a227",
}
PALETTE = ["#ff2800","#00d7b6","#3671f5","#ff8000","#ffd400","#b06bff","#00e701","#ff6ec7"]

def tc(eid, i=0): return TEAM.get(eid, PALETTE[i % len(PALETTE)])
def e(s): return html.escape(str(s if s is not None else ""))
def nb(x): return f"{x:,}".replace(",", " ")

# ─────────────────────────────────────────────────────────────── queries ──
def collecter(con):
    d = {}
    d["kpi"] = con.execute("""select
        (select count(*) from main_marts.fct_resultat),
        (select count(*) from main_marts.dim_course),
        (select count(*) from main_marts.dim_pilote),
        (select count(*) from main_marts.dim_ecurie),
        (select count(*) from main_marts.dim_pilote_ecurie_scd2),
        (select count(*) / 2 from main_marts.fct_duel_coequipiers),
        (select min(saison) from main_marts.dim_course),
        (select max(saison) from main_marts.dim_course)""").fetchone()

    d["h2h"] = con.execute("""
        select p.nom_complet,
               sum(case when d.bat_coequipier_course then 1 else 0 end) g,
               sum(case when d.bat_coequipier_course then 0 else 1 end) pd,
               count(*) n
        from main_marts.fct_duel_coequipiers d
        join main_marts.dim_pilote p using (pilote_id)
        group by 1 having count(*) >= 40
        order by g::double/count(*) desc limit 10""").fetchall()

    d["h2h_bas"] = con.execute("""
        select p.nom_complet,
               sum(case when d.bat_coequipier_course then 1 else 0 end) g,
               sum(case when d.bat_coequipier_course then 0 else 1 end) pd,
               count(*) n
        from main_marts.fct_duel_coequipiers d
        join main_marts.dim_pilote p using (pilote_id)
        group by 1 having count(*) >= 40
        order by g::double/count(*) asc limit 5""").fetchall()

    d["vp"] = con.execute("""select nom_complet, nb_victoires from main_marts.dim_pilote
        order by nb_victoires desc limit 8""").fetchall()
    d["ve"] = con.execute("""select ecurie_id, nom_ecurie, nb_victoires from main_marts.dim_ecurie
        order by nb_victoires desc limit 8""").fetchall()

    top = [r[0] for r in con.execute("""select ecurie_id from main_marts.dim_ecurie
        order by nb_victoires desc limit 8""").fetchall()]
    saisons = [r[0] for r in con.execute(
        "select distinct saison from main_marts.dim_course order by saison").fetchall()]
    noms = dict(con.execute("select ecurie_id, nom_ecurie from main_marts.dim_ecurie").fetchall())
    series = []
    for i, eid in enumerate(top):
        rows = dict(con.execute("""select saison,
            count(*) filter (where est_victoire and ecurie_id = ?)::double
            / nullif(count(*) filter (where est_victoire),0)
            from main_marts.fct_resultat group by saison""", [eid]).fetchall())
        series.append((noms.get(eid, eid), tc(eid, i), {s:(rows.get(s) or 0.0) for s in saisons}))
    d["saisons"], d["series"] = saisons, series

    an_max = d["kpi"][7]
    d["bataille"] = con.execute("""
        with pts as (
          select r.manche, p.nom_complet, any_value(r.ecurie_id) eid, sum(r.points) p
          from main_marts.fct_resultat r
          join main_marts.dim_pilote p using (pilote_id)
          where r.saison = ? group by r.manche, p.nom_complet),
        cum as (
          select nom_complet, eid, manche,
                 sum(p) over (partition by nom_complet order by manche) c
          from pts),
        top as (
          select nom_complet from cum
          where manche = (select max(manche) from cum)
          order by c desc limit 6)
        select cum.nom_complet, any_value(cum.eid), cum.manche, cum.c
        from cum join top using (nom_complet)
        group by cum.nom_complet, cum.manche, cum.c order by 1, 3""", [an_max]).fetchall()

    d["classement"] = con.execute("""
        select p.nom_complet, ec.nom_ecurie, r.ecurie_id,
               round(sum(r.points),0) pts, count(*) filter (where r.est_victoire) v
        from main_marts.fct_resultat r
        join main_marts.dim_pilote p using (pilote_id)
        join main_marts.dim_ecurie ec using (ecurie_id)
        where r.saison = ? group by 1,2,3 order by pts desc limit 10""", [an_max]).fetchall()

    mv = [r[0] for r in con.execute("""select pilote_id from main_marts.dim_pilote_ecurie_scd2
        group by 1 having count(*) >= 3 order by count(*) desc limit 8""").fetchall()]
    if mv:
        q = ",".join("?"*len(mv))
        d["frise"] = con.execute(f"""select p.nom_complet, s.ecurie_id, ec.nom_ecurie,
            s.saison_debut, s.saison_fin
            from main_marts.dim_pilote_ecurie_scd2 s
            join main_marts.dim_pilote p using (pilote_id)
            join main_marts.dim_ecurie ec using (ecurie_id)
            where s.pilote_id in ({q}) order by 1,4""", mv).fetchall()
    else: d["frise"] = []

    d["force"] = con.execute("""
        select p.nom_complet, f.note, f.note_basse, f.note_haute,
               f.nb_duels, f.taux_duels,
               (select ec.nom_ecurie
                  from main_marts.dim_pilote_ecurie_scd2 s
                  join main_marts.dim_ecurie ec using (ecurie_id)
                 where s.pilote_id = f.pilote_id
                 order by s.saison_fin - s.saison_debut desc limit 1) as ecurie,
               (select s.ecurie_id
                  from main_marts.dim_pilote_ecurie_scd2 s
                 where s.pilote_id = f.pilote_id
                 order by s.saison_fin - s.saison_debut desc limit 1) as eid,
               (select min(saison) from main_marts.fct_resultat r
                 where r.pilote_id = f.pilote_id) as debut,
               (select max(saison) from main_marts.fct_resultat r
                 where r.pilote_id = f.pilote_id) as fin
        from main_marts.fct_force_pilote f
        join main_marts.dim_pilote p using (pilote_id)
        where f.classable
        order by f.note desc limit 14""").fetchall()

    d["force_stats"] = con.execute("""
        select count(*) filter (where classable),
               count(*),
               round(min(incertitude) filter (where classable)),
               round(max(incertitude) filter (where classable))
        from main_marts.fct_force_pilote""").fetchone()

    d["residus"] = con.execute("""
        select nom_a, nom_b, premiere_saison, derniere_saison, nb_duels,
               part_observee, part_predite, residu
        from main_marts.fct_calibration_duel
        order by ecart desc limit 8""").fetchall()

    d["residu_stats"] = con.execute("""
        select count(*), avg(ecart),
               count(*) filter (where ecart <= 0.20)::double / count(*),
               avg(case when anciennete_a >= anciennete_b then residu
                        else -residu end)
                 filter (where greatest(anciennete_a, anciennete_b) >= 8
                           and abs(anciennete_a - anciennete_b) >= 4)
        from main_marts.fct_calibration_duel""").fetchone()

    d["bascules"] = con.execute("""
        select t.saison, t.champion_du_jour, t.champions_possibles,
               t.marge_mini
        from main_marts.fct_titre_sensible t
        where t.titre_depend_du_bareme
        order by t.saison desc limit 12""").fetchall()

    d["bascule_n"] = con.execute("""
        select count(*) filter (where titre_depend_du_bareme), count(*)
        from main_marts.fct_titre_sensible""").fetchone()

    d["baremes"] = con.execute("""
        select systeme, any_value(systeme_libelle), systeme_depuis
        from main_marts.fct_championnat_contrefactuel
        group by systeme, systeme_depuis order by systeme_depuis""").fetchall()

    d["voiture"] = con.execute("""
        select saison, part_ecurie, nb_ecuries
        from main_marts.fct_part_voiture
        where part_ecurie is not null order by saison""").fetchall()

    d["partages"] = con.execute("""
        select r.saison, r.manche, string_agg(p.nom_complet,' + ') pil,
               any_value(ec.nom_ecurie) ec
        from main_marts.fct_resultat r
        join main_marts.dim_pilote p using (pilote_id)
        join main_marts.dim_ecurie ec using (ecurie_id)
        where r.est_victoire group by r.saison, r.manche
        having count(*) > 1 order by r.saison""").fetchall()
    return d

# ──────────────────────────────────────────────────────────── components ──
MARQUE = """<svg class="mk" viewBox="0 0 86 40" aria-hidden="true">
  <g stroke-linecap="square" fill="none">
    <path d="M4 34 L22 6"  stroke="var(--rouge)" stroke-width="7"/>
    <path d="M18 34 L36 6" stroke="var(--rouge)" stroke-width="7" opacity=".58"/>
    <path d="M32 34 L50 6" stroke="var(--rouge)" stroke-width="7" opacity=".26"/>
  </g>
  <path d="M54 34 L68 6 L82 34 L74 34 L68 21 L62 34 Z" fill="var(--txt)"/>
</svg>"""


CIRCUIT = """<svg class="trk" viewBox="0 0 520 360" aria-hidden="true">
  <path id="lap" d="M70 300 C40 250 46 190 92 166 C140 141 196 168 232 140
    C272 109 258 58 306 44 C356 29 404 56 430 96 C458 138 470 190 448 238
    C426 286 372 306 316 300 C258 294 214 258 164 266 C122 272 96 300 70 300 Z"/>
  <use href="#lap" class="trk-b"/>
  <use href="#lap" class="trk-f"/>
  <circle r="6" class="trk-c"><animateMotion dur="7s" repeatCount="indefinite"
    rotate="auto"><mpath href="#lap"/></animateMotion></circle>
</svg>"""

ONDES = """<svg class="ondes" viewBox="0 0 1200 90" preserveAspectRatio="none"
  aria-hidden="true">
  <path d="M0 62 L250 62 L268 30 L292 86 L316 48 L340 62 L1200 62" class="tel"/>
</svg>"""

def tuile(valeur, etiquette, note="", grand=False):
    cl = "tuile grande" if grand else "tuile"
    n = f'<div class="note">{e(note)}</div>' if note else ""
    return (f'<div class="{cl}"><div class="val">{e(valeur)}</div>'
            f'<div class="et">{e(etiquette)}</div>{n}</div>')

def titre(num, t, st=None):
    """Section heading.

    `st` is accepted and ignored. Every section used to carry a second
    all-caps label to the right of its title, which on inspection restated
    the title in different words ("Where the model is wrong" / "RESIDUALS")
    and appeared often enough to read as furniture rather than as
    information. The number stays: the sections build on each other in order
    and the reader is told where they are.
    """
    return (f'<div class="shead"><span class="snum">{num}</span>'
            f'<h2>{e(t)}</h2><span class="srule"></span></div>')

def chart_bataille(rows, an):
    """Cumulative points by round for the leading drivers of the season."""
    if not rows: return ""
    par = {}
    for nom, eid, manche, cum in rows:
        par.setdefault(nom, {"eid": eid, "pts": []})["pts"].append((int(manche), float(cum)))
    mx_r = max(m for d in par.values() for m, _ in d["pts"])
    mx_p = max(p for d in par.values() for _, p in d["pts"]) or 1
    W, H, L, R, T, B = 1000, 420, 48, 150, 24, 44
    iw, ih = W - L - R, H - T - B
    def X(m): return L + (m - 1) / max(mx_r - 1, 1) * iw
    def Y(p): return T + ih - p / mx_p * ih
    g = []
    for k in range(5):
        y = T + ih * k / 4
        g.append(f'<line x1="{L}" y1="{y:.0f}" x2="{L+iw}" y2="{y:.0f}" class="gl"/>')
        g.append(f'<text x="{L-10}" y="{y+4:.0f}" class="ax ar">{mx_p*(4-k)/4:.0f}</text>')
    for m in range(1, mx_r + 1):
        if m == 1 or m % 4 == 0 or m == mx_r:
            g.append(f'<text x="{X(m):.0f}" y="{T+ih+22}" class="ax am">R{m}</text>')
    for i, (nom, d) in enumerate(sorted(par.items(), key=lambda kv: -kv[1]["pts"][-1][1])):
        pts = sorted(d["pts"])
        c = tc(d["eid"], i)
        path = " ".join(f'{"M" if j==0 else "L"}{X(m):.1f},{Y(p):.1f}' for j,(m,p) in enumerate(pts))
        lm, lp = pts[-1]
        court = nom.split()[-1].upper()
        g.append(f'<path d="{path}" class="ln" style="stroke:{c};--dl:{len(pts)*60}"/>')
        g.append(f'<circle cx="{X(lm):.1f}" cy="{Y(lp):.1f}" r="4.5" fill="{c}"/>')
        g.append(f'<text x="{X(lm)+12:.1f}" y="{Y(lp)+4:.1f}" class="lb" '
                 f'style="fill:{c}">{e(court)} <tspan class="lbp">{lp:.0f}</tspan></text>')
    return (f'<div class="carte large"><div class="chd"><h3>Championship battle, {an}</h3>'
            f'<span class="chs">points accumulated after each round</span></div>'
            f'<svg viewBox="0 0 {W} {H}" class="cv">{"".join(g)}</svg></div>')

def table_classement(rows, an):
    tr = []
    for i, (pil, ec, eid, pts, v) in enumerate(rows, 1):
        c = tc(eid, i)
        lrg = float(pts) / float(rows[0][3] or 1) * 100
        tr.append(f'<tr><td class="pos">{i:02d}</td>'
                  f'<td class="pil"><span class="tb" style="background:{c}"></span>{e(pil)}</td>'
                  f'<td class="ecn">{e(ec)}</td>'
                  f'<td class="num">{int(v)}</td>'
                  f'<td class="num fort">{int(pts)}</td>'
                  f'<td class="bar"><i style="--w:{lrg:.1f}%;background:{c}"></i></td></tr>')
    return (f'<div class="carte"><div class="chd"><h3>Drivers standings, {an}</h3>'
            f'<span class="chs">from the race results in the warehouse</span></div>'
            f'<table class="tb-cl"><thead><tr><th></th><th>Driver</th><th>Constructor</th>'
            f'<th class="num">Wins</th><th class="num">Pts</th><th></th></tr></thead>'
            f'<tbody>{"".join(tr)}</tbody></table></div>')

def duels(hauts, bas):
    def bloc(rows, ton):
        out = []
        for nom, g, pd_, n in rows:
            pc = g / n * 100
            out.append(f'<div class="duel"><div class="dnom">{e(nom)}'
                       f'<span class="dn">{nb(n)} races</span></div>'
                       f'<div class="dbar"><i class="dg {ton}" style="--w:{pc:.1f}%">'
                       f'<b>{int(g)}</b></i><i class="dp"><b>{int(pd_)}</b></i></div>'
                       f'<div class="dpc">{pc:.0f}%</div></div>')
        return "".join(out)
    return (f'<div class="carte"><div class="chd"><h3>Beaten by a team mate</h3>'
            f'<span class="chs">same car, same race, both classified. 40 duels minimum</span></div>'
            f'<div class="dlg"><span class="k1"></span>ahead<span class="k2"></span>behind</div>'
            f'{bloc(hauts,"v")}<div class="sep">weakest records</div>{bloc(bas,"r")}</div>')

def aires(saisons, series):
    if not saisons: return ""
    W, H, L, R, T, B = 1000, 320, 52, 24, 20, 40
    iw, ih = W - L - R, H - T - B
    s0, s1 = saisons[0], saisons[-1]
    def X(s): return L + (s - s0) / max(s1 - s0, 1) * iw
    bas = {s: 0.0 for s in saisons}
    g = []
    for k in range(5):
        y = T + ih * k / 4
        g.append(f'<line x1="{L}" y1="{y:.0f}" x2="{L+iw}" y2="{y:.0f}" class="gl"/>')
        g.append(f'<text x="{L-10}" y="{y+4:.0f}" class="ax ar">{(4-k)*25}%</text>')
    for s in saisons:
        if s % 10 == 0:
            g.append(f'<text x="{X(s):.0f}" y="{T+ih+22}" class="ax am">{s}</text>')
    def lisser(parts):
        # A season is 16 to 24 races, so a single year of win share swings hard.
        # Three-season centred mean keeps the eras readable without hiding them.
        out = {}
        for i, s in enumerate(saisons):
            fen = saisons[max(i-1,0):i+2]
            out[s] = sum(parts.get(x, 0.0) for x in fen) / len(fen)
        return out

    for nom, c, parts in series:
        parts = lisser(parts)
        haut = {s: bas[s] + parts.get(s, 0.0) for s in saisons}
        up = " ".join(f'{"M" if i==0 else "L"}{X(s):.1f},{T+ih-haut[s]*ih:.1f}'
                      for i, s in enumerate(saisons))
        dn = " ".join(f'L{X(s):.1f},{T+ih-bas[s]*ih:.1f}' for s in reversed(saisons))
        g.append(f'<path d="{up} {dn} Z" fill="{c}" opacity=".80"/>')
        bas = haut
    lg = "".join(f'<span class="li"><i style="background:{c}"></i>{e(n)}</span>'
                 for n, c, _ in series)
    return (f'<div class="carte large"><div class="chd"><h3>Who was winning, by season</h3>'
            f'<span class="chs">share of wins taken by the eight most successful '
            f'constructors, {s0} to {s1}. Three-season rolling mean</span></div>'
            f'<svg viewBox="0 0 {W} {H}" class="cv">{"".join(g)}</svg>'
            f'<div class="lgd">{lg}</div></div>')

def frise(rows, s0, s1):
    if not rows: return ""
    ordre, vus = [], set()
    for r in rows:
        if r[0] not in vus: vus.add(r[0]); ordre.append(r[0])
    lignes = []
    for nom in ordre:
        segs = [r for r in rows if r[0] == nom]
        bl = []
        for i, (_, eid, ecn, a, b) in enumerate(segs):
            b = b or s1
            g_ = (a - s0) / max(s1 - s0, 1) * 100
            w_ = max((b - a + 1) / max(s1 - s0, 1) * 100, 0.9)
            bl.append(f'<i style="left:{g_:.2f}%;width:{w_:.2f}%;background:{tc(eid,i)}" '
                      f'title="{e(ecn)} {a}-{b}"><s>{e(ecn)}</s></i>')
        lignes.append(f'<div class="fl"><div class="fn">{e(nom)}</div>'
                      f'<div class="fp">{"".join(bl)}</div></div>')
    ticks = "".join(f'<span style="left:{(a-s0)/max(s1-s0,1)*100:.2f}%">{a}</span>'
                    for a in range(((s0+9)//10)*10, s1+1, 10))
    return (f'<div class="carte large"><div class="chd"><h3>Career moves, rebuilt as '
            f'Type 2 history</h3><span class="chs">one row per driver and constructor '
            f'period, with its own validity range</span></div>'
            f'<div class="frise">{"".join(lignes)}<div class="fax">{ticks}</div></div></div>')

def barres(titre_, sous, rows, cle_couleur=False):
    mx = max(r[-1] for r in rows) or 1
    out = []
    for i, r in enumerate(rows):
        nom, val = (r[1], r[2]) if cle_couleur else (r[0], r[1])
        c = tc(r[0], i) if cle_couleur else PALETTE[i % len(PALETTE)]
        out.append(f'<div class="bl"><div class="bn">{e(nom)}</div>'
                   f'<div class="bp"><i style="--w:{val/mx*100:.1f}%;background:{c}"></i></div>'
                   f'<div class="bv">{nb(val)}</div></div>')
    return (f'<div class="carte"><div class="chd"><h3>{e(titre_)}</h3>'
            f'<span class="chs">{e(sous)}</span></div>{"".join(out)}</div>')

def classement_force(rows, stats):
    """Interval chart: fitted strength with its bootstrap range."""
    if not rows: return ""
    lo = min(r[2] for r in rows) - 25
    hi = max(r[3] for r in rows) + 25
    span = hi - lo
    def X(v): return (v - lo) / span * 100
    out = []
    for i, (nom, note, b, h, nd, taux, ecn, eid, deb, fin) in enumerate(rows, 1):
        c = tc(eid, i)
        out.append(
          f'<div class="fo"><div class="fo-r">{i:02d}</div>'
          f'<div class="fo-n">{e(nom)}<span>{e(deb)} to {e(fin)} '
          f'&middot; {nb(int(nd))} duels &middot; {taux*100:.0f}% ahead</span></div>'
          f'<div class="fo-p"><i class="fo-i" style="left:{X(b):.2f}%;'
          f'width:{X(h)-X(b):.2f}%;background:{c}"></i>'
          f'<b class="fo-d" style="left:{X(note):.2f}%;background:{c}"></b></div>'
          f'<div class="fo-v">{note:.0f}</div></div>')
    cl, tot, imin, imax = stats
    return (f'<div class="carte large"><div class="chd">'
            f'<h3>Teammate-adjusted driver strength</h3>'
            f'<span class="chs">Bradley-Terry fit over every teammate duel in the '
            f'warehouse. The bar is a 90% bootstrap interval, the dot is the point '
            f'estimate. A 400 point gap means ten-to-one odds in equal machinery. '
            f'{nb(int(cl))} of {nb(int(tot))} drivers clear the 40 duel floor and sit '
            f'in the connected part of the teammate graph.</span></div>'
            f'{"".join(out)}'
            f'<p class="avert">This measures beating your teammate, which is not the '
            f'same as being the best driver. It cannot see a driver who never had a '
            f'competitive seat, and it fits one strength per career, so a long '
            f'decline is averaged into the peak.</p></div>')


def residus(rows, stats):
    """Where the fit misses, and the direction it misses in."""
    if not rows: return ""
    n, mae, part, biais = stats
    lignes = []
    for nom_a, nom_b, a0, a1, nd, obs, pred, res in rows:
        gauche, droite = (50 + res*120), abs(res)*120
        if res >= 0:
            barre = (f'<i class="rs-p" style="left:50%;width:{abs(res)*120:.1f}%">'
                     f'</i>')
        else:
            barre = (f'<i class="rs-n" style="left:{50-abs(res)*120:.1f}%;'
                     f'width:{abs(res)*120:.1f}%"></i>')
        lignes.append(
          f'<div class="rs"><div class="rs-n2">{e(nom_a)} v {e(nom_b)}'
          f'<span>{e(a0)} to {e(a1)} &middot; {nb(int(nd))} duels &middot; '
          f'model {pred*100:.0f}%, actual {obs*100:.0f}%</span></div>'
          f'<div class="rs-t"><u></u>{barre}</div>'
          f'<div class="rs-v">{res*100:+.0f}</div></div>')
    return (f'<div class="carte large"><div class="chd">'
            f'<h3>Where the model is wrong</h3>'
            f'<span class="chs">Residuals on the {nb(int(n))} pairings with twenty '
            f'duels or more. Mean absolute error {mae*100:.1f} points, '
            f'{part*100:.0f}% inside twenty points. Bars to the right mean the model '
            f'rated the first driver higher than the results did.</span></div>'
            f'{"".join(lignes)}'
            f'<p class="avert">The misses are not random. Every large one is a late '
            f'career pairing, and in each the model favours the veteran: across '
            f'pairings starting at least eight seasons into one driver\'s career, '
            f'the average residual runs {biais*100:+.1f} points in the senior '
            f'driver\'s favour. One strength is fitted per driver for a whole '
            f'career, so Ricciardo in 2024 is scored with a rating earned at Red '
            f'Bull a decade earlier. A build-time check watches the size of this '
            f'and warns when it grows.</p></div>')


def bascules_tbl(rows, compte):
    n, tot = compte
    tr = "".join(
        f'<tr><td class="num fort">{e(s_)}</td><td>{e(ch)}</td>'
        f'<td class="ecn">{e(poss)}</td>'
        f'<td class="num">{(m if m is not None else 0):.0f}</td></tr>'
        for s_, ch, poss, m in rows)
    return (f'<div class="carte"><div class="chd">'
            f'<h3>Seasons the rulebook decided</h3>'
            f'<span class="chs">Every season rescored under all five scoring systems '
            f'the sport has used. In {nb(int(n))} of {nb(int(tot))} seasons the driver '
            f'at the top of the table changes depending on which system you apply, '
            f'with all results counting in each case.</span></div>'
            f'<table class="tb-cl"><thead><tr><th>Season</th>'
            f'<th>Champion of record</th><th>Possible champions across systems</th>'
            f'<th class="num">Margin</th></tr></thead><tbody>{tr}</tbody></table>'
            f'<p class="avert">Dropped scores, used until 1990, are not applied: '
            f'carrying one era\'s drop rule into another era\'s calendar compares '
            f'nothing. What is compared here is the shape of the scoring curve.</p>'
            f'</div>')


def courbe_voiture(rows):
    if not rows: return ""
    W, H, L, R, T, B = 1000, 340, 54, 26, 22, 42
    iw, ih = W - L - R, H - T - B
    s0, s1 = rows[0][0], rows[-1][0]
    def X(s_): return L + (s_ - s0) / max(s1 - s0, 1) * iw
    def Y(v): return T + ih - v * ih
    g = []
    for k in range(5):
        y = T + ih * k / 4
        g.append(f'<line x1="{L}" y1="{y:.0f}" x2="{L+iw}" y2="{y:.0f}" class="gl"/>')
        g.append(f'<text x="{L-10}" y="{y+4:.0f}" class="ax ar">{(4-k)*25}%</text>')
    for s_, _, _ in rows:
        if s_ % 10 == 0:
            g.append(f'<text x="{X(s_):.0f}" y="{T+ih+22}" class="ax am">{s_}</text>')
    aire = (" ".join(f'{"M" if i==0 else "L"}{X(s_):.1f},{Y(v):.1f}'
                     for i, (s_, v, _) in enumerate(rows))
            + f' L{X(s1):.1f},{T+ih} L{X(s0):.1f},{T+ih} Z')
    trait = " ".join(f'{"M" if i==0 else "L"}{X(s_):.1f},{Y(v):.1f}'
                     for i, (s_, v, _) in enumerate(rows))
    moy = sum(v for _, v, _ in rows) / len(rows)
    g.append(f'<defs><linearGradient id="gv" x1="0" y1="0" x2="0" y2="1">'
             f'<stop offset="0" stop-color="var(--rouge)" stop-opacity=".40"/>'
             f'<stop offset="1" stop-color="var(--rouge)" stop-opacity="0"/>'
             f'</linearGradient></defs>')
    g.append(f'<path d="{aire}" fill="url(#gv)"/>')
    g.append(f'<path d="{trait}" class="ln doux" style="stroke:var(--rouge);--dl:3000"/>')
    g.append(f'<line x1="{L}" y1="{Y(moy):.1f}" x2="{L+iw}" y2="{Y(moy):.1f}" '
             f'class="gl" stroke-dasharray="5 5"/>')
    g.append(f'<text x="{L+6}" y="{Y(moy)-9:.1f}" class="ax">'
             f'mean {moy*100:.0f}%</text>')
    return (f'<div class="carte large"><div class="chd">'
            f'<h3>How much of a result is the car</h3>'
            f'<span class="chs">Share of the variance in finishing position that sits '
            f'between constructors rather than within them, by season. High means the '
            f'grid is sorted by machinery, low means teammates scatter and something '
            f'other than the car is doing the work.</span></div>'
            f'<svg viewBox="0 0 {W} {H}" class="cv">{"".join(g)}</svg>'
            f'<p class="avert">An association, not a causal split. Better teams also '
            f'hire better drivers, so part of what lands on the car here is the driver '
            f'the car attracted.</p></div>')


def partages(rows):
    tr = "".join(f'<tr><td class="num">{e(s)}</td><td class="num">R{e(m)}</td>'
                 f'<td>{e(p)}</td><td class="ecn">{e(ec)}</td></tr>' for s, m, p, ec in rows)
    return (f'<div class="carte"><div class="chd"><h3>Races with more than one winner'
            f'</h3><span class="chs">shared drives, all before the practice was banned. '
            f'These broke four of the tests until the rules were written to allow them</span>'
            f'</div><table class="tb-cl"><thead><tr><th>Season</th><th>Round</th>'
            f'<th>Drivers</th><th>Constructor</th></tr></thead><tbody>{tr}</tbody>'
            f'</table></div>')

# ───────────────────────────────────────────────────────────────── styles ──
CSS = """
:root{
  --fond:#06070b; --fond2:#0b0d14; --carte:#10131d; --bord:#1e2331;
  --txt:#f2f4f8; --txt2:#9aa3b5; --txt3:#7d8796;
  --rouge:#ff2800; --rouge2:#ff6a4d; --cyan:#00d7b6; --bleu:#3671f5;
  --mono:"Azeret Mono",ui-monospace,"SF Mono",Consolas,monospace;
  --sans:"Chivo","Segoe UI",Helvetica,Arial,sans-serif;
  --disp:"Bricolage Grotesque","Arial Narrow",Helvetica,sans-serif;
  --r:14px;
  /* One scale. Every margin, gap and pad below comes from it, so related
     elements line up without anyone eyeballing a value. */
  --e1:4px; --e2:8px; --e3:12px; --e4:16px; --e5:24px; --e6:32px;
  --e7:48px; --e8:72px;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth;scroll-padding-top:86px}
body{
  background:var(--fond);color:var(--txt);font-family:var(--sans);
  -webkit-font-smoothing:antialiased;line-height:1.5;
  background-image:
    radial-gradient(900px 480px at 12% -8%, rgba(255,40,0,.16), transparent 70%),
    radial-gradient(760px 420px at 92% 2%, rgba(54,113,245,.13), transparent 70%),
    linear-gradient(rgba(255,255,255,.022) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.022) 1px, transparent 1px);
  background-size:auto,auto,64px 64px,64px 64px;
}
.wrap{max-width:1360px;margin:0 auto;padding:0 var(--e5) var(--e8)}

/* en-tete */
header.hero{padding:var(--e8) 0 var(--e6);position:relative}
.marque{display:flex;align-items:center;gap:16px}
.mk{width:58px;height:33px;flex:none}
.wm{font-family:var(--disp);font-weight:800;letter-spacing:.01em;font-size:26px;
  line-height:1;font-stretch:84%}
.wm b{color:var(--rouge)}
.wm span{display:block;font-size:9.5px;font-weight:500;letter-spacing:.3em;
  color:var(--txt3);margin-top:5px}
h1{font-family:var(--disp);font-size:clamp(42px,7.8vw,92px);line-height:.9;
  letter-spacing:-.035em;font-weight:800;font-stretch:86%;text-transform:uppercase;
  margin:40px 0 0;max-width:15ch}
h1 i{font-style:normal;color:var(--txt3)}
.sstitre{margin-top:22px;max-width:62ch;color:var(--txt2);font-size:16.5px}
.specs{display:grid;grid-template-columns:repeat(2,1fr);gap:var(--e5) var(--e6);
  margin-top:var(--e6);padding-top:var(--e5);border-top:1px solid var(--bord);
  max-width:900px}
.specs div{font-size:13.5px;color:var(--txt2);line-height:1.62}
.specs b{display:block;font-family:var(--mono);font-size:10px;letter-spacing:.17em;
  color:var(--rouge2);text-transform:uppercase;font-weight:500;margin-bottom:9px}
@media(max-width:820px){.specs{grid-template-columns:1fr;gap:var(--e4)}}
.puces{display:flex;gap:var(--e2);flex-wrap:wrap;margin-top:var(--e5)}
.puce{font-family:var(--mono);font-size:10.5px;letter-spacing:.16em;
  padding:7px 13px;border:1px solid var(--bord);border-radius:999px;
  color:var(--txt2);background:rgba(255,255,255,.025)}
.puce.on{border-color:rgba(255,40,0,.5);color:var(--rouge2);
  background:rgba(255,40,0,.09)}

/* nav */
nav{position:sticky;top:0;z-index:40;backdrop-filter:blur(16px);
  background:rgba(6,7,11,.84);border-bottom:1px solid var(--bord);margin-bottom:44px}
nav .in{max-width:1360px;margin:0 auto;padding:0 28px;display:flex;gap:2px;
  align-items:center;overflow-x:auto;scrollbar-width:none}
nav .nmk{display:flex;align-items:center;gap:9px;padding-right:20px;margin-right:12px;
  border-right:1px solid var(--bord);flex:none;text-decoration:none}
nav .nmk .mk{width:34px;height:19px;position:static;opacity:1}
nav .nmk span{font-family:var(--disp);font-weight:800;font-size:14px;
  font-stretch:84%;letter-spacing:.02em;color:var(--txt)}
nav .nmk span i{font-style:normal;color:var(--rouge)}
nav .in::-webkit-scrollbar{display:none}
nav a{font-family:var(--sans);font-size:11.5px;font-weight:600;
  letter-spacing:.085em;text-transform:uppercase;color:var(--txt3);
  text-decoration:none;padding:17px 13px;white-space:nowrap;
  border-bottom:2px solid transparent;transition:.16s}
nav a:hover{color:var(--txt);border-bottom-color:var(--rouge)}

/* bento */
.bento{display:grid;grid-template-columns:repeat(12,1fr);gap:var(--e3);
  margin-bottom:var(--e4)}
.tuile{grid-column:span 3;background:
   linear-gradient(145deg,rgba(255,255,255,.045),rgba(255,255,255,.012));
  border:1px solid var(--bord);border-radius:var(--r);padding:22px 22px 20px;
  position:relative;overflow:hidden}
.tuile::after{content:"";position:absolute;inset:0;border-radius:var(--r);
  pointer-events:none;box-shadow:inset 0 1px 0 rgba(255,255,255,.055)}
.tuile.grande{grid-column:span 6;padding:30px 28px 26px}
.tuile .val{font-family:var(--mono);font-weight:700;letter-spacing:-.045em;
  font-size:clamp(34px,4.1vw,52px);line-height:1;color:var(--txt)}
/* Solid, not a gradient. A gradient across a numeral fades its last digits
   toward the background, which costs legibility on the one element the page
   exists to show. The hero figure is distinguished by size, not by colour. */
.tuile.grande .val{font-size:clamp(46px,6.6vw,80px)}
.tuile .et{font-family:var(--mono);font-size:10.5px;letter-spacing:.17em;
  color:var(--txt3);margin-top:13px}
.tuile .note{color:var(--txt2);font-size:13px;margin-top:9px;max-width:40ch}
@media(max-width:1000px){.tuile{grid-column:span 6}.tuile.grande{grid-column:span 12}}
@media(max-width:620px){.tuile{grid-column:span 12}}

/* sections */
.shead{display:flex;align-items:baseline;gap:var(--e3);
  margin:var(--e8) 0 var(--e4);flex-wrap:wrap}
.snum{font-family:var(--mono);font-size:11px;color:var(--rouge);letter-spacing:.14em}
.shead h2{font-family:var(--disp);font-size:clamp(22px,2.7vw,32px);
  letter-spacing:-.02em;font-weight:800;font-stretch:88%;text-transform:uppercase}
.srule{flex:1;height:1px;background:linear-gradient(90deg,var(--bord),transparent);
  min-width:30px}
.ssub{font-family:var(--mono);font-size:10.5px;color:var(--txt3);letter-spacing:.09em}
.grille{display:grid;grid-template-columns:repeat(12,1fr);gap:var(--e3)}
.carte{grid-column:span 6;background:var(--carte);border:1px solid var(--bord);
  border-radius:var(--r);padding:22px 24px 26px;overflow:hidden}
.carte.large{grid-column:span 12}
@media(max-width:960px){.carte{grid-column:span 12}}
.chd{margin-bottom:var(--e4)}
.chd h3{font-family:var(--disp);font-size:17.5px;letter-spacing:-.005em;
  font-weight:700;font-stretch:92%}
.chs{display:block;color:var(--txt3);font-size:12.5px;margin-top:5px;max-width:74ch}

/* svg */
.cv{width:100%;height:auto;display:block;overflow:visible}
.gl{stroke:rgba(255,255,255,.055);stroke-width:1}
.ax{font-family:var(--mono);font-size:10.5px;fill:var(--txt3)}
.ar{text-anchor:end}.am{text-anchor:middle}
.ln.doux{stroke-width:2;filter:none}
.ln{fill:none;stroke-width:2.6;stroke-linecap:round;stroke-linejoin:round;
  stroke-dasharray:var(--dl);stroke-dashoffset:var(--dl);
  animation:trace 2.1s cubic-bezier(.3,.7,.2,1) forwards}
@keyframes trace{to{stroke-dashoffset:0}}
.lb{font-family:var(--mono);font-size:12px;font-weight:600}
.lbp{fill:var(--txt2);font-weight:400}
.lgd{display:flex;gap:var(--e4);flex-wrap:wrap;margin-top:var(--e4)}
.li{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--txt2)}
.li i{width:11px;height:11px;border-radius:3px;flex:none}

/* tables */
table.tb-cl{width:100%;border-collapse:collapse;font-size:13.5px}
.tb-cl th{text-align:left;font-family:var(--mono);font-size:10px;letter-spacing:.14em;
  color:var(--txt3);font-weight:500;padding:0 10px 10px 0;
  border-bottom:1px solid var(--bord)}
.tb-cl td{padding:11px 10px 11px 0;border-bottom:1px solid rgba(255,255,255,.04)}
.tb-cl tbody tr:hover{background:rgba(255,255,255,.028)}
.pos{font-family:var(--mono);color:var(--txt3);font-size:12px;width:34px}
.pil{font-weight:600;white-space:nowrap}
.tb{display:inline-block;width:3px;height:15px;border-radius:2px;
  margin-right:11px;vertical-align:-2px}
.ecn{color:var(--txt2);font-size:12.5px}
.num{font-family:var(--mono);text-align:right;width:62px}
.fort{color:var(--txt);font-weight:700}
td.bar{width:34%;padding-right:0}
td.bar i{display:block;height:5px;border-radius:3px;width:var(--w)}

/* duels */
.dlg{display:flex;align-items:center;gap:7px;font-family:var(--mono);font-size:10px;
  letter-spacing:.12em;color:var(--txt3);margin-bottom:16px}
.dlg span{width:10px;height:10px;border-radius:2px}
.dlg .k1{background:var(--cyan)}.dlg .k2{background:#2a3040;margin-left:12px}
.duel{display:grid;grid-template-columns:1fr 46% 44px;gap:13px;align-items:center;
  padding:9px 0}
.dnom{font-size:13.5px;font-weight:600;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}
.dn{display:block;font-family:var(--mono);font-size:10px;color:var(--txt3);
  font-weight:400;letter-spacing:.07em;margin-top:2px}
.dbar{display:flex;height:22px;border-radius:5px;overflow:hidden;background:#171b26}
.dbar i{display:flex;align-items:center;font-style:normal}
.dbar b{font-family:var(--mono);font-size:10.5px;padding:0 7px;font-weight:600}
.dg{width:var(--w)}
.dg.v{background:linear-gradient(90deg,#00a98f,var(--cyan))}
.dg.r{background:linear-gradient(90deg,#8e1b00,var(--rouge))}
.dg b{color:#04110e}
.dp{flex:1;background:#2a3040;justify-content:flex-end}
.dp b{color:var(--txt3)}
.dpc{font-family:var(--mono);font-size:13px;text-align:right;color:var(--txt2)}
.sep{font-family:var(--mono);font-size:10px;letter-spacing:.14em;color:var(--txt3);
  margin:22px 0 6px;padding-top:16px;border-top:1px solid var(--bord)}

/* barres */
.bl{display:grid;grid-template-columns:1fr 52% 58px;gap:13px;align-items:center;
  padding:8px 0}
.bn{font-size:13.5px;font-weight:600;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}
.bp{height:8px;background:#171b26;border-radius:4px;overflow:hidden}
.bp i{display:block;height:100%;width:var(--w);border-radius:4px}
.bv{font-family:var(--mono);font-size:13px;text-align:right;color:var(--txt2)}

/* frise */
.frise{margin-top:4px}
.fl{display:grid;grid-template-columns:168px 1fr;gap:14px;align-items:center;
  padding:5px 0}
.fn{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}
.fp{position:relative;height:24px;background:#141821;border-radius:5px}
.fp i{position:absolute;top:0;height:24px;border-radius:4px;display:flex;
  align-items:center;overflow:hidden;opacity:.92;font-style:normal}
.fp i:hover{opacity:1;z-index:3;box-shadow:0 0 0 1px rgba(255,255,255,.3)}
.fp s{font-family:var(--mono);font-size:9.5px;text-decoration:none;color:#070910;
  padding:0 6px;white-space:nowrap;font-weight:700;letter-spacing:.03em}
.fax{position:relative;height:18px;margin-left:182px;margin-top:8px}
.fax span{position:absolute;font-family:var(--mono);font-size:10px;color:var(--txt3);
  transform:translateX(-50%)}
@media(max-width:700px){.fl{grid-template-columns:100px 1fr}.fax{margin-left:114px}}

footer{margin-top:var(--e8);padding-top:var(--e5);border-top:1px solid var(--bord);
  color:var(--txt3);font-size:12.5px;display:flex;gap:var(--e5);flex-wrap:wrap}
footer code{font-family:var(--mono);color:var(--txt2);font-size:12px}
footer a{color:var(--txt2)}
@media(prefers-reduced-motion:reduce){
  *{animation:none!important;transition:none!important}
  .ln{stroke-dashoffset:0}
}
/* artwork */
.trk{position:absolute;top:40px;right:-40px;width:min(44vw,520px);height:auto;
  opacity:.5;pointer-events:none;z-index:0}
#lap{fill:none}
.trk-b{stroke:rgba(255,255,255,.07);stroke-width:22;stroke-linejoin:round}
.trk-f{stroke:var(--rouge);stroke-width:2;stroke-dasharray:1600;
  stroke-dashoffset:1600;animation:trace 3.4s ease-out .3s forwards}
.trk-c{fill:#fff}
header.hero>*{position:relative;z-index:1}
@media(max-width:860px){.trk{display:none}}
.ondes{display:block;width:100%;height:58px;margin:0 0 -8px;opacity:.5}
.tel{fill:none;stroke:var(--rouge);stroke-width:1.6;
  stroke-dasharray:2600;stroke-dashoffset:2600;animation:trace 2.4s ease-out forwards}

/* strength intervals */
.fo{display:grid;grid-template-columns:30px 230px 1fr 56px;gap:14px;
  align-items:center;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.035)}
.fo:last-of-type{border-bottom:0}
.fo-r{font-family:var(--mono);font-size:12px;color:var(--txt3)}
.fo-n{font-size:13.5px;font-weight:600;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}
.fo-n span{display:block;font-family:var(--mono);font-size:9.5px;color:var(--txt3);
  font-weight:400;letter-spacing:.05em;margin-top:3px}
.fo-p{position:relative;height:20px}
.fo-p::before{content:"";position:absolute;left:0;right:0;top:9px;height:2px;
  background:rgba(255,255,255,.05)}
.fo-i{position:absolute;top:6px;height:8px;border-radius:5px;opacity:.42;
  font-style:normal}
.fo-d{position:absolute;top:2px;width:16px;height:16px;border-radius:50%;
  margin-left:-8px;border:3px solid var(--carte)}
.fo-v{font-family:var(--mono);font-size:14px;font-weight:700;text-align:right}
@media(max-width:820px){
  .fo{grid-template-columns:26px 1fr 54px;row-gap:4px;padding:12px 0}
  .fo-v{grid-column:3;grid-row:1}
  .fo-p{grid-column:1/-1;grid-row:2}}
.avert{margin-top:var(--e4);padding-top:var(--e3);border-top:1px solid var(--bord);
  font-size:12.5px;color:var(--txt3);line-height:1.6}

/* residuals */
.rs{display:grid;grid-template-columns:270px 1fr 46px;gap:14px;align-items:center;
  padding:9px 0;border-bottom:1px solid rgba(255,255,255,.035)}
.rs:last-of-type{border-bottom:0}
.rs-n2{font-size:13.5px;font-weight:600;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}
.rs-n2 span{display:block;font-family:var(--mono);font-size:9.5px;color:var(--txt3);
  font-weight:400;letter-spacing:.04em;margin-top:3px}
.rs-t{position:relative;height:16px;background:#141821;border-radius:4px}
.rs-t u{position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;
  background:rgba(255,255,255,.22)}
.rs-t i{position:absolute;top:3px;height:10px;border-radius:3px;font-style:normal}
.rs-p{background:linear-gradient(90deg,var(--rouge),var(--rouge2))}
.rs-n{background:linear-gradient(90deg,#00a98f,var(--cyan))}
.rs-v{font-family:var(--mono);font-size:13px;text-align:right;color:var(--txt2)}
@media(max-width:820px){
  .rs{grid-template-columns:1fr 46px;row-gap:4px;padding:12px 0}
  .rs-v{grid-column:2;grid-row:1}
  .rs-t{grid-column:1/-1;grid-row:2}}

/* Keyboard focus. There was none at all, so a keyboard user could tab the
   nav and see nothing move. Ring rather than outline so it clears the sticky
   nav's bottom border, and :focus-visible so a mouse click does not draw it. */
:focus-visible{outline:2px solid var(--rouge2);outline-offset:3px;
  border-radius:4px}
nav a:focus-visible{outline-offset:-4px}

/* motion: feedback only */
.carte{transition:border-color .25s,transform .25s,box-shadow .25s}
.carte:hover{border-color:#2d3447;transform:translateY(-3px);
  box-shadow:0 18px 46px -24px rgba(0,0,0,.95)}
.tuile{transition:transform .25s,border-color .25s}
.tuile:hover{transform:translateY(-3px);border-color:#2d3447}
.puce{transition:border-color .2s,color .2s,transform .2s}
.puce:hover{color:var(--txt);border-color:#39415a;transform:translateY(-2px)}
.tb-cl tbody tr{transition:background .18s}

"""

JS = """
/* Deliberately small. An earlier version faded every card in on scroll and
   counted the headline figures up from zero. Both were decoration: they told
   the reader nothing that the page does not already say, and they delayed the
   numbers behind an animation on every visit. What is left is the chart line
   drawing along its own time axis, which is in the CSS and does carry meaning,
   plus hover and focus feedback.

   Reserved for behaviour that needs it later; no entrance animation belongs
   here. */
""" 
NAV = [("force","Driver strength"),("residus","Residuals"),
       ("bareme","Scoring systems"),
       ("voiture","Car or driver"),("saison","Season"),("duels","Team mates"),
       ("domination","Dominance"),("carrieres","Careers")]

def rendre(d):
    k = d["kpi"]
    n_res, n_crs, n_pil, n_ecu, n_scd, n_duel, s0, s1 = k
    an = s1
    cls = d["classement"]
    meneur = cls[0] if cls else None

    nav = "".join(f'<a href="#{i}">{e(t)}</a>' for i, t in NAV)
    puces = "".join(f'<span class="puce{" on" if o else ""}">{e(t)}</span>' for t, o in [
        ("dbt", True), ("DUCKDB", False), ("SQL", False),
        ("KIMBALL STAR SCHEMA", False), ("SCD TYPE 2", False),
        ("BRADLEY-TERRY", True), ("BOOTSTRAP CI", False),
        ("NUMPY", False), ("PYTHON MODELS IN dbt", False)])

    tuiles = (
      tuile(nb(n_res), "RACE RESULTS LOADED",
            f"Every classified and retired entry from {s0} to {s1}, pulled from a "
            f"public results API and rebuilt into a dimensional model.", grand=True)
      + tuile(nb(n_crs), "GRANDS PRIX")
      + tuile(nb(n_pil), "DRIVERS")
      + tuile(nb(n_ecu), "CONSTRUCTORS")
      + tuile(nb(n_duel), "TEAM MATE DUELS FITTED")
      + tuile(nb(n_scd), "SCD2 PERIODS")
      + tuile(f"{s1-s0+1}", "SEASONS OF HISTORY")
    )

    tete = (
      f'<header class="hero" id="top">{CIRCUIT}<div class="marque">{MARQUE}'
      f'<div class="wm">APEX<b>//</b>DATA<span>RACE ANALYTICS WAREHOUSE</span></div></div>'
      # "One model that holds together" said nothing: it would fit any data
      # project ever built. The line now states the actual contribution, which
      # is that the teammate graph puts drivers on one scale who never shared
      # a garage or an era.
      f'<h1>{nb(n_res)} results.<br>{s1-s0+1} seasons.<br><i>One scale for '
      f'drivers who never met.</i></h1>'
      f'<p class="sstitre">An analytics engineering project: a dimensional warehouse '
      f'built with dbt over the complete results history of world championship motor '
      f'racing, {s0} to {s1}. Every figure on this page is read from the warehouse at '
      f'build time.</p>'
      f'<div class="specs">'
      f'<div><b>Ingestion</b>A resumable Python loader against a public results API, '
      f'with rate-limit backoff and a progress table, so an interrupted run continues '
      f'where it stopped.</div>'
      f'<div><b>Modelling</b>Staging, intermediate and mart layers. A Kimball star '
      f'schema, plus a Type 2 dimension holding every driver and constructor pairing '
      f'with its own validity range.</div>'
      f'<div><b>Statistics</b>A Bradley-Terry fit over the teammate graph with a '
      f'bootstrap interval, a variance decomposition separating car from driver, and '
      f'every season rescored under every points system the sport has used.</div>'
      f'<div><b>Testing</b>Assertions on every build, including one that rescores '
      f'2010 to 2018 from nothing and requires the answer to equal the points those '
      f'drivers really took.</div></div>'
      f'<div class="puces">{puces}</div></header>' 
      f'<nav><div class="in">'
      f'<a class="nmk" href="#top">{MARQUE}<span>APEX<i>//</i>DATA</span></a>'
      f'{nav}</div></nav>'
      f'{ONDES}'
      f'<section class="bento">{tuiles}</section>'
    )

    corps = []
    corps.append('<span id="force"></span>'
                 + titre("01", "Who was actually quick")
                 + '<div class="grille">'
                 + classement_force(d["force"], d["force_stats"]) + '</div>')

    corps.append('<span id="residus"></span>'
                 + titre("02", "Where the model is wrong")
                 + '<div class="grille">'
                 + residus(d["residus"], d["residu_stats"]) + '</div>')

    corps.append('<span id="bareme"></span>'
                 + titre("03", "The rules as a variable")
                 + '<div class="grille">'
                 + bascules_tbl(d["bascules"], d["bascule_n"])
                 + barres("Most wins, all time", "drivers, every season in the "
                          "warehouse", d["vp"]) + '</div>')

    corps.append('<span id="voiture"></span>'
                 + titre("04", "Car or driver")
                 + '<div class="grille">' + courbe_voiture(d["voiture"]) + '</div>')

    corps.append('<span id="saison"></span>'
                 + titre("05", f"The {an} season")
                 + '<div class="grille">'
                 + chart_bataille(d["bataille"], an)
                 + table_classement(cls, an)
                 + barres("Most wins by constructor", "wins credited to the entrant",
                          d["ve"], cle_couleur=True)
                 + '</div>')

    corps.append('<span id="duels"></span>'
                 + titre("06", "Same car, different driver")
                 + '<div class="grille">' + duels(d["h2h"], d["h2h_bas"])
                 + partages(d["partages"]) + '</div>')

    corps.append('<span id="domination"></span>'
                 + titre("07", "Eras of dominance")
                 + '<div class="grille">' + aires(d["saisons"], d["series"]) + '</div>')

    corps.append('<span id="carrieres"></span>'
                 + titre("08", "Slowly changing history")
                 + '<div class="grille">' + frise(d["frise"], s0, s1) + '</div>')

    pied = (f'<footer><span>Source <code>api.jolpi.ca/ergast</code>, seasons {s0} to '
            f'{s1}</span><span><code>dbt</code> on <code>DuckDB</code></span>'
            f'<span>Models, tests and this page all rebuild from one command</span>'
            f'</footer>')

    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Apex Data, race analytics warehouse</title>'
            f'<link rel="preconnect" href="https://fonts.googleapis.com">'
            f'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wdth,wght@12..96,75..100,400..800&family=Chivo:ital,wght@0,300..900;1,400&family=Azeret+Mono:wght@400;500;700&display=swap">'
            f'<style>{CSS}</style></head><body><div class="wrap">'
            f'{tete}{"".join(corps)}{pied}</div><script>{JS}</script></body></html>')


def main():
    con = duckdb.connect(str(DB), read_only=True)
    try: d = collecter(con)
    finally: con.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(rendre(d), encoding="utf-8")
    print(f"wrote {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")

if __name__ == "__main__":
    main()
