{% if var('use_fixture', true) %}
with expected (
  transfer_id,
  transaction_sender_relation,
  transaction_target_relation,
  is_indirect,
  token_status
) as (
  values
    ('1-0xaaa-0', 'transfer_sender', 'token_contract', false, 'trusted'),
    ('1-0xbbb-1', 'transfer_sender', 'token_contract', false, 'trusted'),
    ('1-0xccc-0', 'transfer_recipient', 'token_contract', true, 'trusted'),
    ('1-0xddd-2', 'other', 'other', true, 'trusted'),
    ('1-0xeee-0', 'unknown', 'unknown', null, 'unverified')
)
select expected.*
from expected
left join {{ ref('wallet_events') }} as actual using (transfer_id)
where actual.transfer_id is null
  or actual.transaction_sender_relation != expected.transaction_sender_relation
  or actual.transaction_target_relation != expected.transaction_target_relation
  or actual.is_indirect is distinct from expected.is_indirect
  or actual.token_status != expected.token_status
{% else %}
select * from {{ ref('wallet_events') }} where false
{% endif %}
