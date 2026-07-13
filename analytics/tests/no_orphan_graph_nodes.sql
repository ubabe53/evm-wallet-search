with endpoints as (
  select source_node_id as node_id from {{ ref('graph_edges') }}
  union
  select target_node_id as node_id from {{ ref('graph_edges') }}
)

select nodes.node_id
from {{ ref('graph_nodes') }} as nodes
left join endpoints using (node_id)
where endpoints.node_id is null
