{% macro drop_retired_analytics_relations() %}
  {% set retired_relations = [
    'counterparty_code_metadata',
    'counterparty_code_metadata_fixture',
    'graph_edges',
    'graph_nodes',
    'int_classified_wallet_transfer_events',
    'int_token_reputation',
    'int_wallet_token_interactions',
    'raw_erc20_transfers_fixture',
    'stg_counterparty_metadata',
    'stg_erc20_transfers',
    'stg_token_metadata'
  ] %}
  {% for identifier in retired_relations %}
    {% do drop_relation_if_present(identifier) %}
  {% endfor %}
  {{ return('select 1') }}
{% endmacro %}
