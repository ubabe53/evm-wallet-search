select graph_edges.edge_id
from {{ ref('graph_edges') }} as graph_edges
left join {{ ref('graph_nodes') }} as source_nodes
  on graph_edges.source_node_id = source_nodes.node_id
left join {{ ref('graph_nodes') }} as target_nodes
  on graph_edges.target_node_id = target_nodes.node_id
where source_nodes.node_id is null
  or target_nodes.node_id is null
