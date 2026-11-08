{# Headline numbers straight from the warehouse, printed in CI so the README
   cannot drift away from what the data says. #}

{% macro resume_f1() %}

  {% set requete %}
    select
      (select count(*)              from {{ ref('fct_resultat') }})          as resultats,
      (select count(*)              from {{ ref('dim_course') }})            as courses,
      (select count(*)              from {{ ref('dim_pilote') }})            as pilotes,
      (select count(*)              from {{ ref('dim_ecurie') }})            as ecuries,
      (select count(*)              from {{ ref('dim_circuit') }})           as circuits,
      (select count(*)              from {{ ref('dim_pilote_ecurie_scd2') }}) as periodes_pilote_ecurie,
      (select count(*)              from {{ ref('fct_duel_coequipiers') }})  as duels,
      (select min(saison)           from {{ ref('dim_course') }})            as saison_min,
      (select max(saison)           from {{ ref('dim_course') }})            as saison_max
  {% endset %}

  {% if execute %}
    {% set r = run_query(requete) %}
    {% do log("", info=true) %}
    {% do log("=== Chiffres du warehouse F1 ===", info=true) %}
    {% for c in r.column_names %}
      {% do log("  " ~ c ~ " = " ~ r.columns[c].values()[0], info=true) %}
    {% endfor %}
    {% do log("", info=true) %}
  {% endif %}

{% endmacro %}
