select
  lower(address) as address,
  address_type,
  try_cast(code_size_bytes as bigint) as code_size_bytes,
  cast(rpc_block_number as bigint) as rpc_block_number,
  cast(fetched_at as varchar) as fetched_at,
  fetch_status,
  nullif(trim(error_code), '') as error_code
{% if var('use_fixture', true) %}
from {{ ref('counterparty_code_metadata_fixture') }}
{% else %}
from {{ ref('counterparty_code_metadata') }}
{% endif %}
