"""
Neo4j entities read with filter service
from Neo4j graph read nodes, filter出符合预定义entities type of

nodes
"""

import time
from typing import Dict, Any, List, Optional, Set, Callable, TypeVar
from dataclasses import dataclass, field

from ..config import Config
from ..utils.logger import get_logger
from .neo4j_service import Neo4jService

logger = get_logger('mirofish.neo4j_entity_reader')

# use于泛型return type
T = TypeVar('T')


@dataclass
class EntityNode:
    """entity node count据structure"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    # related of edge information
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    # related of其he node information
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
        """get entity types（排除默认of GraphNode label）"""
        for label in self.labels:
            if label not in ["Entity", "Node", "GraphNode"]:
                return label
        return None


@dataclass
class FilteredEntities:
    """filter后 of entities set"""
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
    Neo4j entities read with filter service
    
    主want Features:
    1. from Neo4j graph read所have nodes
    2. filter出符合预定义entities type of nodes（Labels not只is GraphNode of nodes）
    3. get每entities of related edges and 关联nodes information
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
        带retry机制 of Neo4j call
        
        Args:
            func: want execute of function（无parameters of lambda or callable）
            operation_name: 操作名称，use于log
            max_retries: maximum retry times count（默认3times，即最多尝试3times）
            initial_delay: 初始延迟秒count
            
        Returns:
            Call result
        """
        return self.neo4j.execute_with_retry(func, operation_name, max_retries, initial_delay)
    
    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        get graph of所have nodes（带retry机制）
        
        Args:
            graph_id: graph ID
            
        Returns:
            nodes list
        """
        logger.info(f"get graph {graph_id} of所have node...")
        
        # use retry机制call Neo4j
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
            operation_name=f"get node(graph={graph_id})"
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
        
        logger.info(f"total get {len(nodes_data)} node")
        return nodes_data
    
    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        get graph of所have edges（带retry机制）
        
        Args:
            graph_id: graph ID
            
        Returns:
            edges list
        """
        logger.info(f"get graph {graph_id} of所have edge...")
        
        # use retry机制call Neo4j
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
            operation_name=f"get edge(graph={graph_id})"
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
        
        logger.info(f"total get {len(edges_data)} edge")
        return edges_data
    
    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        """
        get指定nodes of所have related edges（带retry机制）
        
        Args:
            node_uuid: nodes UUID
            
        Returns:
            edges list
        """
        try:
            # use retry机制call Neo4j
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
                operation_name=f"get node edge(node={node_uuid[:8]}...)"
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
            logger.warning(f"get node {node_uuid} of edge failed: {str(e)}")
            return []
    
    def filter_defined_entities(
        self, 
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True
    ) -> FilteredEntities:
        """
        filter出符合预定义entities type of nodes
        
        filter逻辑：
        - if nodes of Labels只have一个"GraphNode"，say明this entities not符合I们预定义 of type，跳过
        - if nodes of Labels contains除"GraphNode"之外 of label，say明符合预定义type，保留
        
        Args:
            graph_id: graph ID
            defined_entity_types: 预定义 of entities type list（可选，if提供则只保留this些type）
            enrich_with_edges: whether to get每entities of related edge informationrmation
            
        Returns:
            FilteredEntities: filter后 of entities set
        """
        logger.info(f"start filter graph {graph_id} of entity...")
        
        # get所have node
        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)
        
        # get所have edge（use于后续关联查找）
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []
        
        # 构建node UUID到nodes count据 of映射
        node_map = {n["uuid"]: n for n in all_nodes}
        
        # filter符合件 of entity
        filtered_entities = []
        entity_types_found = set()
        
        for node in all_nodes:
            labels = node.get("labels", [])
            
            # filter逻辑：Labels must contains除"GraphNode"之外 of label
            custom_labels = [l for l in labels if l not in ["Entity", "Node", "GraphNode"]]
            
            if not custom_labels:
                # 只have默认label，跳过
                continue
            
            # if指定预定义type，check whether to匹配
            if defined_entity_types:
                matching_labels = [l for l in custom_labels if l in defined_entity_types]
                if not matching_labels:
                    continue
                entity_type = matching_labels[0]
            else:
                entity_type = custom_labels[0]
            
            entity_types_found.add(entity_type)
            
            # create entity node object
            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )
            
            # get related edge and node
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
                
                # get关联node of基本information
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
        
        logger.info(f"filter completed: Total node {total_count}, 符合件 {len(filtered_entities)}, "
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
        get单entities and其complete上下文（edges and关联nodes，带retry机制）
        
        Args:
            graph_id: graph ID
            entity_uuid: entities UUID
            
        Returns:
            EntityNode or None
        """
        try:
            # use retry机制get node
            def query_node():
                return self.neo4j.get_node_by_uuid(entity_uuid)
            
            node = self._call_with_retry(
                func=query_node,
                operation_name=f"get node详情(uuid={entity_uuid[:8]}...)"
            )
            
            if not node:
                return None
            
            # get node of edge
            edges = self.get_node_edges(entity_uuid)
            
            # get所have node use于关联查找
            all_nodes = self.get_all_nodes(graph_id)
            node_map = {n["uuid"]: n for n in all_nodes}
            
            # processing related edge and node
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
            
            # get关联node information
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
            logger.error(f"get entity {entity_uuid} failed: {str(e)}")
            return None
    
    def get_entities_by_type(
        self, 
        graph_id: str, 
        entity_type: str,
        enrich_with_edges: bool = True
    ) -> List[EntityNode]:
        """
        get指定type of所have entities
        
        Args:
            graph_id: graph ID
            entity_type: entities type（如 "Student", "PublicFigure" etc）
            enrich_with_edges: whether to get related edge informationrmation
            
        Returns:
            entities list
        """
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges
        )
        return result.entities
