"""
Neo4j Entity Reader with Filter Service
Reads nodes from Neo4j graph and filters out entities matching predefined types
"""

import time
from typing import Dict, Any, List, Optional, Set, Callable, TypeVar
from dataclasses import dataclass, field

from ..config import Config
from ..utils.logger import get_logger
from .neo4j_service import Neo4jService

logger = get_logger('fishi.neo4j_entity_reader')

# For generic return type
T = TypeVar('T')


@dataclass
class EntityNode:
    """Entity node data structure"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    # Related edge information
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    # Related node information
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }
    
    def get_entity_type(self) -> Optional[str]:
        """Get entity type (excluding default GraphNode label)"""
        for label in self.labels:
            if label not in ["Entity", "Node", "GraphNode"]:
                return label
        return None


@dataclass
class FilteredEntities:
    """Filtered entity set"""
    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class Neo4jEntityReader:
    """
    Neo4j Entity Reader with Filter Service
    
    Main features:
    1. Read all nodes from Neo4j graph
    2. Filter out nodes matching predefined entity types (nodes with labels other than just GraphNode)
    3. Get related edges and associated node information for each entity
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize entity reader
        
        Args:
            api_key: Not used (kept for API compatibility)
        """
        self.neo4j = Neo4jService()
        logger.info("Neo4jEntityReader initialized")
    
    def _call_with_retry(
        self, 
        func: Callable[[], T], 
        operation_name: str,
        max_retries: int = 3,
        initial_delay: float = 2.0
    ) -> T:
        """
        Neo4j call with retry mechanism
        
        Args:
            func: Function to execute (parameterless lambda or callable)
            operation_name: Operation name for logging
            max_retries: Maximum retry attempts (default 3)
            initial_delay: Initial delay in seconds
            
        Returns:
            Call result
        """
        return self.neo4j.execute_with_retry(func, operation_name, max_retries, initial_delay)
    
    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        Get all nodes from graph (with retry mechanism)
        
        Args:
            graph_id: Graph ID
            
        Returns:
            List of nodes
        """
        logger.info(f"Getting all nodes from graph {graph_id}...")
        
        # Use retry mechanism to call Neo4j
        def query_nodes():
            return self.neo4j.execute_query(
                """
                MATCH (n:GraphNode {graph_id: $graph_id})
                RETURN n, labels(n) as labels
                """,
                {"graph_id": graph_id}
            )
        
        results = self._call_with_retry(
            func=query_nodes,
            operation_name=f"get nodes(graph={graph_id})"
        )
        
        nodes_data = []
        for record in results:
            node = dict(record["n"])
            labels = [l for l in record["labels"] if l != "GraphNode"]
            
            nodes_data.append({
                "uuid": node.get("uuid", ""),
                "name": node.get("name", ""),
                "labels": labels,
                "summary": node.get("summary", ""),
                "attributes": {k: v for k, v in node.items() 
                             if k not in ["uuid", "name", "graph_id", "created_at", "summary"]},
            })
        
        logger.info(f"Total retrieved {len(nodes_data)} nodes")
        return nodes_data
    
    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        Get all edges from graph (with retry mechanism)
        
        Args:
            graph_id: Graph ID
            
        Returns:
            List of edges
        """
        logger.info(f"Getting all edges from graph {graph_id}...")
        
        # Use retry mechanism to call Neo4j
        def query_edges():
            return self.neo4j.execute_query(
                """
                MATCH (a:GraphNode {graph_id: $graph_id})-[r]->(b:GraphNode {graph_id: $graph_id})
                RETURN a.uuid as source_uuid, b.uuid as target_uuid,
                       type(r) as rel_type, properties(r) as props
                """,
                {"graph_id": graph_id}
            )
        
        results = self._call_with_retry(
            func=query_edges,
            operation_name=f"get edges(graph={graph_id})"
        )
        
        edges_data = []
        for record in results:
            props = record["props"]
            
            edges_data.append({
                "uuid": props.get("uuid", ""),
                "name": record["rel_type"],
                "fact": props.get("fact", ""),
                "source_node_uuid": record["source_uuid"],
                "target_node_uuid": record["target_uuid"],
                "attributes": {k: v for k, v in props.items() 
                             if k not in ["uuid", "graph_id", "created_at"]},
            })
        
        logger.info(f"Total retrieved {len(edges_data)} edges")
        return edges_data
    
    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        """
        Get all related edges for a specific node (with retry mechanism)
        
        Args:
            node_uuid: Node UUID
            
        Returns:
            List of edges
        """
        try:
            # Use retry mechanism to call Neo4j
            def query_edges():
                return self.neo4j.execute_query(
                    """
                    MATCH (n {uuid: $uuid})-[r]-(m)
                    RETURN r, type(r) as rel_type, properties(r) as props,
                           startNode(r).uuid as start_uuid, endNode(r).uuid as end_uuid
                    """,
                    {"uuid": node_uuid}
                )
            
            results = self._call_with_retry(
                func=query_edges,
                operation_name=f"get node edges(node={node_uuid[:8]}...)"
            )
            
            edges_data = []
            for record in results:
                props = record["props"]
                
                edges_data.append({
                    "uuid": props.get("uuid", ""),
                    "name": record["rel_type"],
                    "fact": props.get("fact", ""),
                    "source_node_uuid": record["start_uuid"],
                    "target_node_uuid": record["end_uuid"],
                    "attributes": props,
                })
            
            return edges_data
        except Exception as e:
            logger.warning(f"Failed to get edges for node {node_uuid}: {str(e)}")
            return []
    
    def filter_defined_entities(
        self, 
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True
    ) -> FilteredEntities:
        """
        Filter out nodes matching predefined entity types
        
        Filter logic:
        - If node labels only contain "GraphNode", it doesn't match our predefined types, skip
        - If node labels contain labels other than "GraphNode", it matches predefined type, keep
        
        Args:
            graph_id: Graph ID
            defined_entity_types: List of predefined entity types (optional, if provided only keep these types)
            enrich_with_edges: Whether to get related edge information for each entity
            
        Returns:
            FilteredEntities: Filtered entity set
        """
        logger.info(f"Starting to filter entities from graph {graph_id}...")
        
        # Get all nodes
        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)
        
        # Get all edges (for later association lookup)
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []
        
        # Build node UUID to node data mapping
        node_map = {n["uuid"]: n for n in all_nodes}
        
        # Filter entities matching conditions
        filtered_entities = []
        entity_types_found = set()
        
        for node in all_nodes:
            labels = node.get("labels", [])
            
            # Filter logic: Labels must contain labels other than "GraphNode"
            custom_labels = [l for l in labels if l not in ["Entity", "Node", "GraphNode"]]
            
            if not custom_labels:
                # Only has default label, skip
                continue
            
            # If predefined types specified, check for match
            if defined_entity_types:
                matching_labels = [l for l in custom_labels if l in defined_entity_types]
                if not matching_labels:
                    continue
                entity_type = matching_labels[0]
            else:
                entity_type = custom_labels[0]
            
            entity_types_found.add(entity_type)
            
            # Create entity node object
            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )
            
            # Get related edges and nodes
            if enrich_with_edges:
                related_edges = []
                related_node_uuids = set()
                
                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        })
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        })
                        related_node_uuids.add(edge["source_node_uuid"])
                
                entity.related_edges = related_edges
                
                # Get basic info for related nodes
                related_nodes = []
                for related_uuid in related_node_uuids:
                    if related_uuid in node_map:
                        related_node = node_map[related_uuid]
                        related_nodes.append({
                            "uuid": related_node["uuid"],
                            "name": related_node["name"],
                            "labels": related_node["labels"],
                            "summary": related_node.get("summary", ""),
                        })
                
                entity.related_nodes = related_nodes
            
            filtered_entities.append(entity)
        
        logger.info(f"Filter completed: Total nodes {total_count}, matching {len(filtered_entities)}, "
                   f"entity types: {entity_types_found}")
        
        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )
    
    def get_entity_with_context(
        self, 
        graph_id: str, 
        entity_uuid: str
    ) -> Optional[EntityNode]:
        """
        Get single entity with complete context (edges and related nodes, with retry mechanism)
        
        Args:
            graph_id: Graph ID
            entity_uuid: Entity UUID
            
        Returns:
            EntityNode or None
        """
        try:
            # Use retry mechanism to get node
            def query_node():
                return self.neo4j.get_node_by_uuid(entity_uuid)
            
            node = self._call_with_retry(
                func=query_node,
                operation_name=f"get node details(uuid={entity_uuid[:8]}...)"
            )
            
            if not node:
                return None
            
            # Get node edges
            edges = self.get_node_edges(entity_uuid)
            
            # Get all nodes for association lookup
            all_nodes = self.get_all_nodes(graph_id)
            node_map = {n["uuid"]: n for n in all_nodes}
            
            # Process related edges and nodes
            related_edges = []
            related_node_uuids = set()
            
            for edge in edges:
                if edge["source_node_uuid"] == entity_uuid:
                    related_edges.append({
                        "direction": "outgoing",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "target_node_uuid": edge["target_node_uuid"],
                    })
                    related_node_uuids.add(edge["target_node_uuid"])
                else:
                    related_edges.append({
                        "direction": "incoming",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "source_node_uuid": edge["source_node_uuid"],
                    })
                    related_node_uuids.add(edge["source_node_uuid"])
            
            # Get related node information
            related_nodes = []
            for related_uuid in related_node_uuids:
                if related_uuid in node_map:
                    related_node = node_map[related_uuid]
                    related_nodes.append({
                        "uuid": related_node["uuid"],
                        "name": related_node["name"],
                        "labels": related_node["labels"],
                        "summary": related_node.get("summary", ""),
                    })
            
            return EntityNode(
                uuid=node.get("uuid", ""),
                name=node.get("name", ""),
                labels=node.get("labels", []),
                summary=node.get("summary", ""),
                attributes={k: v for k, v in node.items() 
                          if k not in ["uuid", "name", "labels", "summary", "graph_id", "created_at"]},
                related_edges=related_edges,
                related_nodes=related_nodes,
            )
            
        except Exception as e:
            logger.error(f"Failed to get entity {entity_uuid}: {str(e)}")
            return None
    
    def get_entities_by_type(
        self, 
        graph_id: str, 
        entity_type: str,
        enrich_with_edges: bool = True
    ) -> List[EntityNode]:
        """
        Get all entities of specified type
        
        Args:
            graph_id: Graph ID
            entity_type: Entity type (e.g. "Student", "PublicFigure", etc.)
            enrich_with_edges: Whether to get related edge information
            
        Returns:
            List of entities
        """
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges
        )
        return result.entities
