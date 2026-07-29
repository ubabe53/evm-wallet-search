{% if var('use_fixture', true) %}
with expected (
  chain_id,
  transaction_hash,
  log_index,
  transaction_sender_relation,
  transaction_target_relation,
  is_indirect
) as (
  values
    (1, '0xaaa', 0, 'transfer_sender', 'token_contract', false),
    (1, '0xbbb', 1, 'transfer_sender', 'token_contract', false),
    (1, '0xccc', 0, 'transfer_recipient', 'token_contract', true),
    (1, '0xddd', 2, 'other', 'other', true),
    (1, '0xeee', 0, 'unknown', 'unknown', null)
)
select expected.*
from expected
left join {{ ref('int_wallet_transfer_events') }} as actual
  using (chain_id, transaction_hash, log_index)
where actual.chain_id is null
  or actual.transaction_sender_relation != expected.transaction_sender_relation
  or actual.transaction_target_relation != expected.transaction_target_relation
  or actual.is_indirect is distinct from expected.is_indirect
{% else %}
select * from {{ ref('int_wallet_transfer_events') }} where false
{% endif %}
