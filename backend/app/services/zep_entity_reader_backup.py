"""
Zepentitiesreadwithfilterservice
fromZep图谱 readnodes，筛选出符合预定义entitiestypeofnodes
"""

import time
from typing import Dict, Any, List, Optional, Set, Callable, TypeVar
from dataclasses import dataclass, field

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('fishi.zep_entity_reader')

# use于泛型returntype
T = TypeVar('T')


@dataclass
class EntityNode:
    """entitynodecount据structure"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    # relatedofedgeinformation
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    # relatedof其henodeinformation
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
        """getentity types（排除默认ofEntitylabel）"""
        for label in self.labels:
            if label not in ["Entity", "Node"]:
                return label
        return None


@dataclass
class FilteredEntities:
    """filter后ofentityset"""
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


class ZepEntityReader:
    """
    Zepentitiesreadwithfilterservice
    
    主wantFeatures:
    1. fromZep图谱read所havenodes
    2. 筛选出符合预定义entitiestypeofnodes（Labelsnot只isEntityofnodes）
    3. get每entitiesofrelatededgesand关联nodesinformation
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY not configured")
        
        self.client = Zep(api_key=self.api_key)
    
    def _call_with_retry(
        self, 
        func: Callable[[], T], 
        operation_name: str,
        max_retries: int = 3,
        initial_delay: float = 2.0
    ) -> T:
        """
        带retry机制ofZep APIcall
        
        Args:
            func: wantexecuteoffunction（无parametersoflambda or callable）
            operation_name: 操作名称，use于log
            max_retries: maximumretrytimescount（默认3times，即最多尝试3times）
            initial_delay: 初始延迟秒count
            
        Returns:
            APIcallresult
        """
        last_exception = None
        delay = initial_delay
        
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Zep {operation_name} 第 {attempt + 1} attemptsfailed: {str(e)[:100]}, "
                        f"{delay:.1f}秒后retry..."
                    )
                    time.sleep(delay)
                    delay *= 2  # 指count退避
                else:
                    logger.error(f"Zep {operation_name} in {max_retries} attempts后仍failed: {str(e)}")
        
        raise last_exception
    
    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        get图谱of所havenodes（带retry机制）
        
        Args:
            graph_id: 图谱ID
            
        Returns:
            nodeslist
        """
        logger.info(f"getgraph {graph_id} of所havenode...")
        
        # useretry机制callZep API
        nodes = self._call_with_retry(
            func=lambda: self.client.graph.node.get_by_graph_id(graph_id=graph_id),
            operation_name=f"getnode(graph={graph_id})"
        )
        
        nodes_data = []
        for node in nodes:
            nodes_data.append({
                "uuid": getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                "name": node.name or "",
                "labels": node.labels or [],
                "summary": node.summary or "",
                "attributes": node.attributes or {},
            })
        
        logger.info(f"totalget {len(nodes_data)} node")
        return nodes_data
    
    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        get图谱of所haveedges（带retry机制）
        
        Args:
            graph_id: 图谱ID
            
        Returns:
            edgeslist
        """
        logger.info(f"getgraph {graph_id} of所haveedge...")
        
        # useretry机制callZep API
        edges = self._call_with_retry(
            func=lambda: self.client.graph.edge.get_by_graph_id(graph_id=graph_id),
            operation_name=f"getedge(graph={graph_id})"
        )
        
        edges_data = []
        for edge in edges:
            edges_data.append({
                "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                "name": edge.name or "",
                "fact": edge.fact or "",
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "attributes": edge.attributes or {},
            })
        
        logger.info(f"totalget {len(edges_data)} edge")
        return edges_data
    
    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        """
        get指定nodesof所haverelatededges（带retry机制）
        
        Args:
            node_uuid: nodesUUID
            
        Returns:
            edgeslist
        """
        try:
            # useretry机制callZep API
            edges = self._call_with_retry(
                func=lambda: self.client.graph.node.get_entity_edges(node_uuid=node_uuid),
                operation_name=f"getnodeedge(node={node_uuid[:8]}...)"
            )
            
            edges_data = []
            for edge in edges:
                edges_data.append({
                    "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                    "name": edge.name or "",
                    "fact": edge.fact or "",
                    "source_node_uuid": edge.source_node_uuid,
                    "target_node_uuid": edge.target_node_uuid,
                    "attributes": edge.attributes or {},
                })
            
            return edges_data
        except Exception as e:
            logger.warning(f"getnode {node_uuid} ofedgefailed: {str(e)}")
            return []
    
    def filter_defined_entities(
        self, 
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True
    ) -> FilteredEntities:
        """
        筛选出符合预定义entitiestypeofnodes
        
        筛选逻辑：
        - ifnodesofLabels只have一"Entity"，say明thisentitiesnot符合I们预定义oftype，跳过
        - ifnodesofLabelscontains除"Entity"and"Node"之外oflabel，say明符合预定义type，保留
        
        Args:
            graph_id: 图谱ID
            defined_entity_types: 预定义ofentitiestypelist（ can 选，if提供则只保留this些type）
            enrich_with_edges: whether toget每entitiesofrelatededge informationrmation
            
        Returns:
            FilteredEntities: filter后ofentitiesset
        """
        logger.info(f"start筛选graph {graph_id} ofentity...")
        
        # get所havenode
        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)
        
        # get所haveedge（use于后续关联查找）
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []
        
        # 构建nodeUUID到nodescount据of映射
        node_map = {n["uuid"]: n for n in all_nodes}
        
        # 筛选符合件ofentity
        filtered_entities = []
        entity_types_found = set()
        
        for node in all_nodes:
            labels = node.get("labels", [])
            
            # 筛选逻辑：Labelsmustcontains除"Entity"and"Node"之外oflabel
            custom_labels = [l for l in labels if l not in ["Entity", "Node"]]
            
            if not custom_labels:
                # 只have默认label，跳过
                continue
            
            # if指定预定义type，checkwhether to匹配
            if defined_entity_types:
                matching_labels = [l for l in custom_labels if l in defined_entity_types]
                if not matching_labels:
                    continue
                entity_type = matching_labels[0]
            else:
                entity_type = custom_labels[0]
            
            entity_types_found.add(entity_type)
            
            # createentitynodeobject
            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )
            
            # getrelatededgeandnode
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
                
                # get关联nodeof基本information
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
        
        logger.info(f"筛选completed: Totalnode {total_count}, 符合件 {len(filtered_entities)}, "
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
        get单entitiesand其complete上下文（edgesand关联nodes，带retry机制）
        
        Args:
            graph_id: 图谱ID
            entity_uuid: entitiesUUID
            
        Returns:
            EntityNode or None
        """
        try:
            # useretry机制getnode
            node = self._call_with_retry(
                func=lambda: self.client.graph.node.get(uuid_=entity_uuid),
                operation_name=f"getnode详情(uuid={entity_uuid[:8]}...)"
            )
            
            if not node:
                return None
            
            # getnodeofedge
            edges = self.get_node_edges(entity_uuid)
            
            # get所havenodeuse于关联查找
            all_nodes = self.get_all_nodes(graph_id)
            node_map = {n["uuid"]: n for n in all_nodes}
            
            # processingrelatededgeandnode
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
            
            # get关联nodeinformation
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
                uuid=getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {},
                related_edges=related_edges,
                related_nodes=related_nodes,
            )
            
        except Exception as e:
            logger.error(f"getentity {entity_uuid} failed: {str(e)}")
            return None
    
    def get_entities_by_type(
        self, 
        graph_id: str, 
        entity_type: str,
        enrich_with_edges: bool = True
    ) -> List[EntityNode]:
        """
        get指定typeof所haveentities
        
        Args:
            graph_id: 图谱ID
            entity_type: entitiestype（如 "Student", "PublicFigure" etc）
            enrich_with_edges: whether toget relatededge informationrmation
            
        Returns:
            entitieslist
        """
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges
        )
        return result.entities


