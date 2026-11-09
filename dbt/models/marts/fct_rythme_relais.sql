-- Grain: one driver's stint in one race.
--
-- A stint is the run between pit stops. Splitting a race into stints and
-- fitting a line through the lap times is the closest this data gets to
-- answering "how quick was the car actually going", as opposed to where it
-- finished, which is also a story about strategy, traffic and reliability.
--
-- What the slope is, and what it is not
-- -------------------------------------
-- `pente_ms_par_tour` is the gradient of lap time against lap number inside
-- the stint. It is deliberately NOT called degradation, because two opposite
-- forces are inside it and this data cannot separate them:
--
--   * tyres wear, which makes each lap slower
--   * fuel burns off at roughly 1.5 to 2 kg a lap, which makes each lap
--     faster by something like 0.03 to 0.06 seconds
--
-- So the number is the NET of the two. A stint at zero is not a stint with no
-- wear: it is a stint where wear and fuel burn cancelled. Correcting for fuel
-- needs the starting load, which this API does not publish, and inventing a
-- constant would dress a guess as a measurement.
--
-- There is also no tyre compound in this source, so a soft stint and a hard
-- stint are indistinguishable here. Any comparison between stints is
-- therefore between unknown compounds, which is the single biggest limit on
-- what this model can be used for.
--
-- What is excluded, and why
-- --------------------------
--   * the in-lap and the out-lap: both contain pit lane time and say nothing
--     about pace
--   * laps more than 25% slower than the stint median: safety cars, virtual
--     safety cars, red flags and spins. A single safety-car lap can be 40
--     seconds long and would dominate a least-squares fit through fifteen
--     otherwise clean laps
--   * stints with fewer than six clean laps, where a slope is noise
--
-- The outlier rule is a blunt instrument and it will occasionally remove a
-- genuine slow lap in heavy traffic. That is the trade accepted here: the
-- alternative is leaving in a neutralised lap, which is not a lap of racing
-- at all.

with decoupage as (

    -- The stint labelling lives in int_tour_relais so it can be tested on
    -- its own, before anything here throws laps away.
    select * from {{ ref('int_tour_relais') }}
    where temps_ms is not null

),

bornes as (

    select
        saison, manche, course_id, pilote_id, no_relais,
        min(numero_tour) as tour_debut,
        max(numero_tour) as tour_fin,
        count(*)         as nb_tours_bruts,
        median(temps_ms) as mediane_brute
    from decoupage
    group by 1, 2, 3, 4, 5

),

propres as (

    select d.*
    from decoupage d
    join bornes b
      on  b.saison    = d.saison
      and b.manche    = d.manche
      and b.pilote_id = d.pilote_id
      and b.no_relais = d.no_relais
    -- In-lap and out-lap. The first stint has no out-lap and the last has no
    -- in-lap, which the comparison handles on its own.
    where d.numero_tour > b.tour_debut
      and d.numero_tour < b.tour_fin
      and d.temps_ms <= b.mediane_brute * 1.25

)

select
    {{ dbt_utils.generate_surrogate_key([
        'saison', 'manche', 'pilote_id', 'no_relais'
    ]) }}                                               as relais_id,
    saison,
    manche,
    course_id,
    pilote_id,
    no_relais,
    min(numero_tour)                                    as tour_debut,
    max(numero_tour)                                    as tour_fin,
    count(*)                                            as nb_tours_propres,
    median(temps_ms)::bigint                            as mediane_ms,
    min(temps_ms)                                       as meilleur_ms,

    -- Least squares through the clean laps. Null below six laps rather than
    -- a number nobody should trust.
    case
        when count(*) >= 6
        then round(regr_slope(temps_ms, numero_tour), 1)
    end                                                 as pente_ms_par_tour,

    -- How much of the lap-to-lap variation the straight line explains. A
    -- slope with r2 near zero is a line drawn through noise, and reporting
    -- it next to the slope is the difference between a model and a number.
    case
        when count(*) >= 6
        then round(regr_r2(temps_ms, numero_tour), 3)
    end                                                 as r2

from propres
group by 1, 2, 3, 4, 5, 6
having count(*) >= 6
