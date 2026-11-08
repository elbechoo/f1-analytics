-- Grain: one driver, one season, under one scoring system.
--
-- Championships are decided by a points table, and the points table has been
-- rewritten eight times. So "who won the title" is partly a fact about the
-- driving and partly a fact about an administrative decision taken years
-- earlier. This model separates the two: every season is rescored under every
-- system the sport has used, and the seasons where the name at the top changes
-- are the seasons where the rulebook, not the racing, picked the champion.
--
-- One deliberate simplification, and it matters: from 1950 to 1990 only a
-- driver's best N results counted and the rest were dropped. That rule is NOT
-- applied here, because applying one era's drop rule to another era's calendar
-- is not a comparison of anything. What this model compares is the shape of the
-- scoring curve - how steeply reward falls away from first place - with all
-- results counting in every case. Under that definition the 1950s champions
-- shown here can differ from the ones in the record books, and that difference
-- is the dropped-scores rule rather than an error.
--
-- Fastest-lap bonus points are also excluded. They existed 1950-1959 and
-- 2019-2024, were worth one point, and the data does not reliably say who set
-- the fastest lap before 2004.

with resultats as (

    select
        saison,
        pilote_id,
        position_classement
    from {{ ref('fct_resultat') }}
    where est_classe

),

systemes as (

    -- `depuis` is only used to label the chart, not to filter: the point of
    -- the model is to apply every system to every season.
    select * from (values
        ('1950_1959', 1950, 'Top five score, 8-6-4-3-2'),
        ('1961_1990', 1961, 'Top six score, 9-6-4-3-2-1'),
        ('1991_2002', 1991, 'Top six score, 10 for a win'),
        ('2003_2009', 2003, 'Top eight score, flatter curve'),
        ('2010_now',  2010, 'Top ten score, 25 for a win')
    ) as t(systeme, depuis, libelle)

),

bareme as (

    select
        s.systeme,
        s.depuis,
        s.libelle,
        p.position_classement,
        p.points
    from systemes s
    join (values
        ('1950_1959', 1,  8.0), ('1950_1959', 2, 6.0), ('1950_1959', 3, 4.0),
        ('1950_1959', 4,  3.0), ('1950_1959', 5, 2.0),

        ('1961_1990', 1,  9.0), ('1961_1990', 2, 6.0), ('1961_1990', 3, 4.0),
        ('1961_1990', 4,  3.0), ('1961_1990', 5, 2.0), ('1961_1990', 6, 1.0),

        ('1991_2002', 1, 10.0), ('1991_2002', 2, 6.0), ('1991_2002', 3, 4.0),
        ('1991_2002', 4,  3.0), ('1991_2002', 5, 2.0), ('1991_2002', 6, 1.0),

        ('2003_2009', 1, 10.0), ('2003_2009', 2, 8.0), ('2003_2009', 3, 6.0),
        ('2003_2009', 4,  5.0), ('2003_2009', 5, 4.0), ('2003_2009', 6, 3.0),
        ('2003_2009', 7,  2.0), ('2003_2009', 8, 1.0),

        ('2010_now',  1, 25.0), ('2010_now',  2, 18.0), ('2010_now', 3, 15.0),
        ('2010_now',  4, 12.0), ('2010_now',  5, 10.0), ('2010_now', 6,  8.0),
        ('2010_now',  7,  6.0), ('2010_now',  8,  4.0), ('2010_now', 9,  2.0),
        ('2010_now', 10,  1.0)
    ) as p(systeme, position_classement, points)
      on p.systeme = s.systeme

),

marques as (

    select
        b.systeme,
        b.depuis,
        b.libelle,
        r.saison,
        r.pilote_id,
        sum(b.points)   as points,
        count(*)        as nb_courses_marquantes
    from resultats r
    join bareme b
      on b.position_classement = r.position_classement
    group by 1, 2, 3, 4, 5

)

select
    {{ dbt_utils.generate_surrogate_key(['systeme', 'saison', 'pilote_id']) }}
        as ligne_id,
    systeme,
    depuis            as systeme_depuis,
    libelle           as systeme_libelle,
    saison,
    pilote_id,
    points,
    nb_courses_marquantes,
    row_number() over (
        partition by systeme, saison order by points desc, pilote_id
    )                 as rang,
    -- Ties on points are broken in the real rules by countback on wins. Here
    -- the margin is reported instead so a one-point title is visible as one,
    -- rather than hidden behind a resolved rank.
    points - lead(points) over (
        partition by systeme, saison order by points desc, pilote_id
    )                 as avance_sur_suivant
from marques
