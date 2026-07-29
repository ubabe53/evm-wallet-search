{% macro drop_relation_if_present(identifier) %}
  {% if execute %}
    {% set relation = adapter.get_relation(
      database=target.database,
      schema=target.schema,
      identifier=identifier
    ) %}
    {% if relation is not none %}
      {% do adapter.drop_relation(relation) %}
    {% endif %}
  {% endif %}
  {{ return('select 1') }}
{% endmacro %}
