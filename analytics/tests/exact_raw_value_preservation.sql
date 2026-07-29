{% set max_uint256 = '115792089237316195423570985008687907853269984665640564039457584007913129639935' %}

with expected as (
  select
    1 as chain_id,
    '0xeee' as transaction_hash,
    0 as log_index,
    '0x9999999999999999999999999999999999999999' as token_address,
    '{{ max_uint256 }}' as value_raw
),

violations as (
  select 'staging' as relation_name
  from expected
  left join {{ ref('stg_transfer_events') }} as staged
    using (chain_id, transaction_hash, log_index)
  where staged.value_raw is distinct from expected.value_raw

  union all

  select 'events' as relation_name
  from expected
  left join {{ ref('int_wallet_transfer_events') }} as events
    using (chain_id, transaction_hash, log_index)
  where events.value_raw is distinct from expected.value_raw

  union all

  select 'token_summary' as relation_name
  from expected
  left join {{ ref('token_summary') }} as summaries using (token_address)
  group by expected.value_raw
  having cast(sum(summaries.value_raw_sum) as varchar) is distinct from expected.value_raw
)

select * from violations
