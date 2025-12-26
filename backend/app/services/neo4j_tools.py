"""
Neo4j Graph Search Tool Service
Encapsulates graph search, node reading, edge querying tools for Report Agent use

Core Search Tools (Optimized):
1. InsightForge (Deep Insight Search) - Most powerful hybrid search, automatically generates sub-queries and searches across multiple dimensions
2. PanoramaSearch (Broad Search) - Gets the full picture, including expired content
3. QuickSearch (Simple Search) - Quick search
"""

import time
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from .neo4j_service import Neo4jService

logger = get_logger('fishi.neo4j_tools')


@dataclass
class SearchResult:
    """Search Result"""
    facts: List[str]
    edges: List[Dict[str, Any]]
    nodes: List[Dict[str, Any]]
    query: str
    total_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "facts": self.facts,
            "edges": self.edges,
            "nodes": self.nodes,
            "query": self.query,
            "total_count": self.total_count
        }
    
    def to_text(self) -> str:
        """Convert to text format for LLM understanding"""
        text_parts = [f"Search Query: {self.query}", f"Found {self.total_count} related information"]
        
        if self.facts:
            text_parts.append("\n### Related Facts:")
            for i, fact in enumerate(self.facts, 1):
                text_parts.append(f"{i}. {fact}")
        
        return "\n".join(text_parts)


@dataclass
class NodeInfo:
    """Node Information"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes
        }
    
    def to_text(self) -> str:
        """Convert to text format"""
        entity_type = next((l for l in self.labels if l not in ["Entity", "Node", "GraphNode"]), "Unknown Type")
        return f"Entity: {self.name} (Type: {entity_type})\nSummary: {self.summary}"


@dataclass
class EdgeInfo:
    """Edge Information"""
    uuid: str
    name: str
    fact: str
    source_node_uuid: str
    target_node_uuid: str
    source_node_name: Optional[str] = None
    target_node_name: Optional[str] = None
    # Temporal information
    created_at: Optional[str] = None
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    expired_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "fact": self.fact,
            "source_node_uuid": self.source_node_uuid,
            "target_node_uuid": self.target_node_uuid,
            "source_node_name": self.source_node_name,
            "target_node_name": self.target_node_name,
            "created_at": self.created_at,
            "valid_at": self.valid_at,
            "invalid_at": self.invalid_at,
            "expired_at": self.expired_at
        }
    
    def to_text(self, include_temporal: bool = False) -> str:
        """Convert to text format"""
        source = self.source_node_name or self.source_node_uuid[:8]
        target = self.target_node_name or self.target_node_uuid[:8]
        base_text = f"Relationship: {source} --[{self.name}]--> {target}\nFacts: {self.fact}"
        
        if include_temporal:
            valid_at = self.valid_at or "Unknown"
            invalid_at = self.invalid_at or "Present"
            base_text += f"\nValidity: {valid_at} - {invalid_at}"
            if self.expired_at:
                base_text += f" (Already Expired: {self.expired_at})"
        
        return base_text
    
    @property
    def is_expired(self) -> bool:
        """Whether already expired"""
        return self.expired_at is not None
    
    @property
    def is_invalid(self) -> bool:
        """Whether already invalid"""
        return self.invalid_at is not None


@dataclass
class InsightForgeResult:
    """
    Deep Insight Search Result (InsightForge)
    Contains search results for multiple sub-queries and comprehensive analysis
    """
    query: str
    simulation_requirement: str
    sub_queries: List[str]
    
    # Results for each dimension
    semantic_facts: List[str] = field(default_factory=list)
    entity_insights: List[Dict[str, Any]] = field(default_factory=list)
    relationship_chains: List[str] = field(default_factory=list)
    
    # Statistical information
    total_facts: int = 0
    total_entities: int = 0
    total_relationships: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "simulation_requirement": self.simulation_requirement,
            "sub_queries": self.sub_queries,
            "semantic_facts": self.semantic_facts,
            "entity_insights": self.entity_insights,
            "relationship_chains": self.relationship_chains,
            "total_facts": self.total_facts,
            "total_entities": self.total_entities,
            "total_relationships": self.total_relationships
        }
    
    def to_text(self) -> str:
        """Convert to detailed text format for LLM understanding"""
        text_parts = [
            f"## Future Prediction Deep Analysis",
            f"Analysis Question: {self.query}",
            f"Prediction Scenario: {self.simulation_requirement}",
            f"\n### Prediction Data Statistics",
            f"- Related Predicted Facts: {self.total_facts}",
            f"- Involved Entities: {self.total_entities}",
            f"- Relationship Chains: {self.total_relationships}"
        ]
        
        if self.sub_queries:
            text_parts.append(f"\n### Analysis Sub-questions")
            for i, sq in enumerate(self.sub_queries, 1):
                text_parts.append(f"{i}. {sq}")
        
        if self.semantic_facts:
            text_parts.append(f"\n### [Key Facts] (Please cite these in report)")
            for i, fact in enumerate(self.semantic_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        if self.entity_insights:
            text_parts.append(f"\n### [Core Entities]")
            for entity in self.entity_insights:
                text_parts.append(f"- **{entity.get('name', 'Unknown')}** ({entity.get('type', 'Entity')})")
                if entity.get('summary'):
                    text_parts.append(f"  Summary: \"{entity.get('summary')}\"")
        
        if self.relationship_chains:
            text_parts.append(f"\n### [Relationship Chains]")
            for chain in self.relationship_chains:
                text_parts.append(f"- {chain}")
        
        return "\n".join(text_parts)


@dataclass
class PanoramaResult:
    """
    Breadth Search Result (Panorama)
    Contains all related information, including expired content
    """
    query: str
    
    all_nodes: List[NodeInfo] = field(default_factory=list)
    all_edges: List[EdgeInfo] = field(default_factory=list)
    active_facts: List[str] = field(default_factory=list)
    historical_facts: List[str] = field(default_factory=list)
    
    total_nodes: int = 0
    total_edges: int = 0
    active_count: int = 0
    historical_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "all_nodes": [n.to_dict() for n in self.all_nodes],
            "all_edges": [e.to_dict() for e in self.all_edges],
            "active_facts": self.active_facts,
            "historical_facts": self.historical_facts,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "active_count": self.active_count,
            "historical_count": self.historical_count
        }
    
    def to_text(self) -> str:
        """Convert to text format"""
        text_parts = [
            f"## Breadth Search Result (Panorama View)",
            f"Query: {self.query}",
            f"\n### Statistics",
            f"- Total Nodes: {self.total_nodes}",
            f"- Total Edges: {self.total_edges}",
            f"- Active Facts: {self.active_count}",
            f"- Historical Facts: {self.historical_count}"
        ]
        
        if self.active_facts:
            text_parts.append(f"\n### [Active Facts] (Current Simulation State)")
            for i, fact in enumerate(self.active_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        if self.historical_facts:
            text_parts.append(f"\n### [Historical Facts] (Evolution Record)")
            for i, fact in enumerate(self.historical_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        if self.all_nodes:
            text_parts.append(f"\n### [Entities]")
            for node in self.all_nodes:
                entity_type = next((l for l in node.labels if l not in ["Entity", "Node", "GraphNode"]), "Entity")
                text_parts.append(f"- **{node.name}** ({entity_type})")
        
        return "\n".join(text_parts)


@dataclass
class AgentInterview:
    """Single Agent Interview Result"""
    agent_name: str
    agent_role: str
    agent_bio: str
    question: str
    response: str
    key_quotes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "agent_bio": self.agent_bio,
            "question": self.question,
            "response": self.response,
            "key_quotes": self.key_quotes
        }
    
    def to_text(self) -> str:
        text = f"**{self.agent_name}** ({self.agent_role})\n"
        text += f"_Bio: {self.agent_bio}_\n\n"
        text += f"**Q:** {self.question}\n\n"
        text += f"**A:** {self.response}\n"
        if self.key_quotes:
            text += "\n**Key Quotes:**\n"
            for quote in self.key_quotes:
                text += f"> \"{quote}\"\n"
        return text


@dataclass
class InterviewResult:
    """Interview Result containing multiple Agent interviews"""
    interview_topic: str
    interview_questions: List[str]
    
    selected_agents: List[Dict[str, Any]] = field(default_factory=list)
    interviews: List[AgentInterview] = field(default_factory=list)
    
    selection_reasoning: str = ""
    summary: str = ""
    
    total_agents: int = 0
    interviewed_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "interview_topic": self.interview_topic,
            "interview_questions": self.interview_questions,
            "selected_agents": self.selected_agents,
            "interviews": [i.to_dict() for i in self.interviews],
            "selection_reasoning": self.selection_reasoning,
            "summary": self.summary,
            "total_agents": self.total_agents,
            "interviewed_count": self.interviewed_count
        }
    
    def to_text(self) -> str:
        """Convert to detailed text format"""
        text_parts = [
            f"## 🎤 Deep Interview Report",
            f"**Interview Topic:** {self.interview_topic}",
            f"**Interviewee Count:** {self.interviewed_count} / {self.total_agents} Agents",
            f"\n### Selection Reasoning",
            f"{self.selection_reasoning}",
            f"\n---"
        ]
        
        if self.interviews:
            text_parts.append(f"\n### Interview Transcript")
            for i, interview in enumerate(self.interviews, 1):
                text_parts.append(f"\n#### Interview #{i}: {interview.agent_name}")
                text_parts.append(interview.to_text())
                text_parts.append("\n---")
        
        if self.summary:
            text_parts.append(f"\n### Summary")
            text_parts.append(self.summary)
        
        return "\n".join(text_parts)


class Neo4jToolsService:
    """
    Neo4j Graph Search Tool Service
    
    [Core Search Tools]
    1. insight_forge - Deep Insight Search (Most powerful, auto-generates sub-queries)
    2. panorama_search - Breadth Search (Full picture including expired content)
    3. quick_search - Simple Search (Quick search)
    4. interview_agents - Deep Interview (Interview simulation Agents)
    
    [Basic Tools]
    - search_graph - Graph keyword search
    - get_all_nodes - Get all nodes in graph
    - get_all_edges - Get all edges in graph
    - get_node_detail - Get node detailed info
    - get_node_edges - Get edges related to node
    - get_entities_by_type - Get entities by type
    - get_entity_summary - Get summary of entity relationships
    """
    
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        """Initialize Neo4j Tools Service"""
        self.neo4j = Neo4jService()
        self._llm_client = llm_client
        logger.info("Neo4jToolsService initialization completed")
    
    @property
    def llm(self) -> LLMClient:
        """Lazy initialization of LLM client"""
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client
    
    def _call_with_retry(self, func, operation_name: str, max_retries: int = None):
        """Execute with retry mechanism"""
        max_retries = max_retries or self.MAX_RETRIES
        last_exception = None
        delay = self.RETRY_DELAY
        
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Neo4j {operation_name} attempt {attempt + 1} failed: {str(e)[:100]}, "
                        f"retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay *= 2
                else:
                    logger.error(f"Neo4j {operation_name} failed after {max_retries} attempts: {str(e)}")
        
        raise last_exception
    
    def search_graph(
        self, 
        graph_id: str, 
        query: str, 
        limit: int = 10,
        scope: str = "edges"
    ) -> SearchResult:
        """
        Graph keyword search using Neo4j full-text or CONTAINS matching
        
        Args:
            graph_id: Graph ID (used as label filter in Neo4j)
            query: Search query
            limit: Return result quantity
            scope: Search scope, "edges" or "nodes"
            
        Returns:
            SearchResult: Search result
        """
        logger.info(f"Graph search: graph_id={graph_id}, query={query[:50]}...")
        
        facts = []
        edges = []
        nodes = []
        
        # Extract keywords for matching
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(',', ' ').replace('，', ' ').split() if len(w.strip()) > 1]
        
        try:
            if scope in ["edges", "both"]:
                # Search edges using CONTAINS on fact property
                edge_query = """
                MATCH (source:GraphNode)-[r]->(target:GraphNode)
                WHERE r.graph_id = $graph_id
                  AND (toLower(r.fact) CONTAINS $query_lower OR toLower(r.name) CONTAINS $query_lower)
                RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact,
                       source.uuid AS source_uuid, target.uuid AS target_uuid,
                       source.name AS source_name, target.name AS target_name,
                       r.created_at AS created_at, r.valid_at AS valid_at,
                       r.invalid_at AS invalid_at, r.expired_at AS expired_at
                LIMIT $limit
                """
                
                results = self._call_with_retry(
                    func=lambda: self.neo4j.execute_query(edge_query, {
                        "graph_id": graph_id,
                        "query_lower": query_lower,
                        "limit": limit
                    }),
                    operation_name=f"edge search(graph={graph_id})"
                )
                
                for record in results:
                    if record.get("fact"):
                        facts.append(record["fact"])
                    edges.append({
                        "uuid": record.get("uuid", ""),
                        "name": record.get("name", ""),
                        "fact": record.get("fact", ""),
                        "source_node_uuid": record.get("source_uuid", ""),
                        "target_node_uuid": record.get("target_uuid", ""),
                        "source_node_name": record.get("source_name", ""),
                        "target_node_name": record.get("target_name", ""),
                    })
            
            if scope in ["nodes", "both"]:
                # Search nodes
                node_query = """
                MATCH (n:GraphNode)
                WHERE n.graph_id = $graph_id
                  AND (toLower(n.name) CONTAINS $query_lower OR toLower(n.summary) CONTAINS $query_lower)
                RETURN n.uuid AS uuid, n.name AS name, labels(n) AS labels, 
                       n.summary AS summary, properties(n) AS attributes
                LIMIT $limit
                """
                
                results = self._call_with_retry(
                    func=lambda: self.neo4j.execute_query(node_query, {
                        "graph_id": graph_id,
                        "query_lower": query_lower,
                        "limit": limit
                    }),
                    operation_name=f"node search(graph={graph_id})"
                )
                
                for record in results:
                    nodes.append({
                        "uuid": record.get("uuid", ""),
                        "name": record.get("name", ""),
                        "labels": record.get("labels", []),
                        "summary": record.get("summary", ""),
                    })
                    if record.get("summary"):
                        facts.append(f"[{record['name']}]: {record['summary']}")
            
            logger.info(f"Search completed: found {len(facts)} related facts")
            
        except Exception as e:
            logger.error(f"Graph search failed: {str(e)}")
        
        return SearchResult(
            facts=facts,
            edges=edges,
            nodes=nodes,
            query=query,
            total_count=len(facts)
        )
    
    def get_all_nodes(self, graph_id: str) -> List[NodeInfo]:
        """Get all nodes of the graph"""
        logger.info(f"Getting all nodes for graph {graph_id}...")
        
        query = """
        MATCH (n:GraphNode)
        WHERE n.graph_id = $graph_id
        RETURN n.uuid AS uuid, n.name AS name, labels(n) AS labels,
               n.summary AS summary, properties(n) AS attributes
        """
        
        results = self._call_with_retry(
            func=lambda: self.neo4j.execute_query(query, {"graph_id": graph_id}),
            operation_name=f"get nodes(graph={graph_id})"
        )
        
        node_list = []
        for record in results:
            node_list.append(NodeInfo(
                uuid=record.get("uuid", ""),
                name=record.get("name", ""),
                labels=record.get("labels", []),
                summary=record.get("summary", ""),
                attributes=record.get("attributes", {})
            ))
        
        logger.info(f"Got {len(node_list)} nodes")
        return node_list
    
    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> List[EdgeInfo]:
        """Get all edges of the graph (including time information)"""
        logger.info(f"Getting all edges for graph {graph_id}...")
        
        query = """
        MATCH (source:GraphNode)-[r]->(target:GraphNode)
        WHERE r.graph_id = $graph_id OR source.graph_id = $graph_id
        RETURN r.uuid AS uuid, type(r) AS name, r.fact AS fact,
               source.uuid AS source_uuid, target.uuid AS target_uuid,
               source.name AS source_name, target.name AS target_name,
               r.created_at AS created_at, r.valid_at AS valid_at,
               r.invalid_at AS invalid_at, r.expired_at AS expired_at
        """
        
        results = self._call_with_retry(
            func=lambda: self.neo4j.execute_query(query, {"graph_id": graph_id}),
            operation_name=f"get edges(graph={graph_id})"
        )
        
        edge_list = []
        for record in results:
            edge_info = EdgeInfo(
                uuid=record.get("uuid", ""),
                name=record.get("name", ""),
                fact=record.get("fact", ""),
                source_node_uuid=record.get("source_uuid", ""),
                target_node_uuid=record.get("target_uuid", ""),
                source_node_name=record.get("source_name", ""),
                target_node_name=record.get("target_name", "")
            )
            
            if include_temporal:
                edge_info.created_at = record.get("created_at")
                edge_info.valid_at = record.get("valid_at")
                edge_info.invalid_at = record.get("invalid_at")
                edge_info.expired_at = record.get("expired_at")
            
            edge_list.append(edge_info)
        
        logger.info(f"Got {len(edge_list)} edges")
        return edge_list
    
    def get_node_detail(self, node_uuid: str) -> Optional[NodeInfo]:
        """Get detailed information of a single node"""
        logger.info(f"Getting node detail: {node_uuid[:8]}...")
        
        query = """
        MATCH (n:GraphNode)
        WHERE n.uuid = $node_uuid
        RETURN n.uuid AS uuid, n.name AS name, labels(n) AS labels,
               n.summary AS summary, properties(n) AS attributes
        """
        
        try:
            results = self._call_with_retry(
                func=lambda: self.neo4j.execute_query(query, {"node_uuid": node_uuid}),
                operation_name=f"get node detail(uuid={node_uuid[:8]}...)"
            )
            
            if not results:
                return None
            
            record = results[0]
            return NodeInfo(
                uuid=record.get("uuid", ""),
                name=record.get("name", ""),
                labels=record.get("labels", []),
                summary=record.get("summary", ""),
                attributes=record.get("attributes", {})
            )
        except Exception as e:
            logger.error(f"Get node detail failed: {str(e)}")
            return None
    
    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[EdgeInfo]:
        """Get all edges related to the node"""
        logger.info(f"Getting related edges for node {node_uuid[:8]}...")
        
        query = """
        MATCH (n:GraphNode)-[r]-(other:GraphNode)
        WHERE n.uuid = $node_uuid
        RETURN r.uuid AS uuid, type(r) AS name, r.fact AS fact,
               startNode(r).uuid AS source_uuid, endNode(r).uuid AS target_uuid,
               startNode(r).name AS source_name, endNode(r).name AS target_name,
               r.created_at AS created_at, r.valid_at AS valid_at,
               r.invalid_at AS invalid_at, r.expired_at AS expired_at
        """
        
        try:
            results = self._call_with_retry(
                func=lambda: self.neo4j.execute_query(query, {"node_uuid": node_uuid}),
                operation_name=f"get node edges(uuid={node_uuid[:8]}...)"
            )
            
            edge_list = []
            for record in results:
                edge_list.append(EdgeInfo(
                    uuid=record.get("uuid", ""),
                    name=record.get("name", ""),
                    fact=record.get("fact", ""),
                    source_node_uuid=record.get("source_uuid", ""),
                    target_node_uuid=record.get("target_uuid", ""),
                    source_node_name=record.get("source_name", ""),
                    target_node_name=record.get("target_name", ""),
                    created_at=record.get("created_at"),
                    valid_at=record.get("valid_at"),
                    invalid_at=record.get("invalid_at"),
                    expired_at=record.get("expired_at")
                ))
            
            logger.info(f"Found {len(edge_list)} edges related to node")
            return edge_list
            
        except Exception as e:
            logger.warning(f"Get node edges failed: {str(e)}")
            return []
    
    def get_entities_by_type(self, graph_id: str, entity_type: str) -> List[NodeInfo]:
        """Get entities by type"""
        logger.info(f"Getting entities of type {entity_type}...")
        
        query = """
        MATCH (n:GraphNode)
        WHERE n.graph_id = $graph_id AND $entity_type IN labels(n)
        RETURN n.uuid AS uuid, n.name AS name, labels(n) AS labels,
               n.summary AS summary, properties(n) AS attributes
        """
        
        results = self._call_with_retry(
            func=lambda: self.neo4j.execute_query(query, {
                "graph_id": graph_id,
                "entity_type": entity_type
            }),
            operation_name=f"get entities by type({entity_type})"
        )
        
        node_list = []
        for record in results:
            node_list.append(NodeInfo(
                uuid=record.get("uuid", ""),
                name=record.get("name", ""),
                labels=record.get("labels", []),
                summary=record.get("summary", ""),
                attributes=record.get("attributes", {})
            ))
        
        logger.info(f"Found {len(node_list)} entities of type {entity_type}")
        return node_list
    
    def get_entity_summary(self, graph_id: str, entity_name: str) -> Dict[str, Any]:
        """Get relationship summary of specified entity"""
        logger.info(f"Getting relationship summary for entity {entity_name}...")
        
        search_result = self.search_graph(
            graph_id=graph_id,
            query=entity_name,
            limit=20
        )
        
        # Find entity node
        query = """
        MATCH (n:GraphNode)
        WHERE n.graph_id = $graph_id AND toLower(n.name) = toLower($entity_name)
        RETURN n.uuid AS uuid, n.name AS name, labels(n) AS labels,
               n.summary AS summary, properties(n) AS attributes
        """
        
        results = self.neo4j.execute_query(query, {
            "graph_id": graph_id,
            "entity_name": entity_name
        })
        
        entity_node = None
        related_edges = []
        
        if results:
            record = results[0]
            entity_node = NodeInfo(
                uuid=record.get("uuid", ""),
                name=record.get("name", ""),
                labels=record.get("labels", []),
                summary=record.get("summary", ""),
                attributes=record.get("attributes", {})
            )
            related_edges = self.get_node_edges(graph_id, entity_node.uuid)
        
        return {
            "entity_name": entity_name,
            "entity_information": entity_node.to_dict() if entity_node else None,
            "related_facts": search_result.facts,
            "related_edges": [e.to_dict() for e in related_edges],
            "total_relations": len(related_edges)
        }
    
    def get_graph_statistics(self, graph_id: str) -> Dict[str, Any]:
        """Get graph statistical information"""
        logger.info(f"Getting statistics for graph {graph_id}...")
        
        nodes = self.get_all_nodes(graph_id)
        edges = self.get_all_edges(graph_id)
        
        entity_types = {}
        for node in nodes:
            for label in node.labels:
                if label not in ["Entity", "Node", "GraphNode"]:
                    entity_types[label] = entity_types.get(label, 0) + 1
        
        relation_types = {}
        for edge in edges:
            relation_types[edge.name] = relation_types.get(edge.name, 0) + 1
        
        return {
            "graph_id": graph_id,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "entity_types": entity_types,
            "relation_types": relation_types
        }
    
    def get_simulation_context(
        self, 
        graph_id: str,
        simulation_requirement: str,
        limit: int = 30
    ) -> Dict[str, Any]:
        """Get simulation related context information"""
        logger.info(f"Getting simulation context: {simulation_requirement[:50]}...")
        
        search_result = self.search_graph(
            graph_id=graph_id,
            query=simulation_requirement,
            limit=limit
        )
        
        stats = self.get_graph_statistics(graph_id)
        all_nodes = self.get_all_nodes(graph_id)
        
        entities = []
        for node in all_nodes:
            custom_labels = [l for l in node.labels if l not in ["Entity", "Node", "GraphNode"]]
            if custom_labels:
                entities.append({
                    "name": node.name,
                    "type": custom_labels[0],
                    "summary": node.summary
                })
        
        return {
            "simulation_requirement": simulation_requirement,
            "related_facts": search_result.facts,
            "graph_statistics": stats,
            "entities": entities[:limit],
            "total_entities": len(entities)
        }
    
    # ========== Core Search Tools (Optimized) ==========
    
    def insight_forge(
        self,
        graph_id: str,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_sub_queries: int = 5
    ) -> InsightForgeResult:
        """
        [InsightForge - Deep Insight Search]
        
        Most powerful search function, auto-decomposes question and searches across multiple dimensions
        """
        logger.info(f"InsightForge Deep Insight Retrieval: {query[:50]}...")
        
        result = InsightForgeResult(
            query=query,
            simulation_requirement=simulation_requirement,
            sub_queries=[]
        )
        
        # Generate sub-queries using LLM
        sub_queries = self._generate_sub_queries(
            query=query,
            simulation_requirement=simulation_requirement,
            report_context=report_context,
            max_queries=max_sub_queries
        )
        result.sub_queries = sub_queries
        logger.info(f"Generated {len(sub_queries)} sub-queries")
        
        # Search for each sub-query
        all_facts = []
        all_edges = []
        seen_facts = set()
        
        for sub_query in sub_queries:
            search_result = self.search_graph(
                graph_id=graph_id,
                query=sub_query,
                limit=15,
                scope="edges"
            )
            
            for fact in search_result.facts:
                if fact not in seen_facts:
                    all_facts.append(fact)
                    seen_facts.add(fact)
            
            all_edges.extend(search_result.edges)
        
        # Also search original query
        main_search = self.search_graph(
            graph_id=graph_id,
            query=query,
            limit=20,
            scope="edges"
        )
        for fact in main_search.facts:
            if fact not in seen_facts:
                all_facts.append(fact)
                seen_facts.add(fact)
        
        result.semantic_facts = all_facts
        result.total_facts = len(all_facts)
        
        # Extract entity UUIDs from edges
        entity_uuids = set()
        for edge_data in all_edges:
            if isinstance(edge_data, dict):
                if edge_data.get('source_node_uuid'):
                    entity_uuids.add(edge_data['source_node_uuid'])
                if edge_data.get('target_node_uuid'):
                    entity_uuids.add(edge_data['target_node_uuid'])
        
        # Get entity details
        entity_insights = []
        node_map = {}
        
        for uuid in list(entity_uuids):
            if not uuid:
                continue
            try:
                node = self.get_node_detail(uuid)
                if node:
                    node_map[uuid] = node
                    entity_type = next((l for l in node.labels if l not in ["Entity", "Node", "GraphNode"]), "Entity")
                    
                    related_facts = [
                        f for f in all_facts 
                        if node.name.lower() in f.lower()
                    ]
                    
                    entity_insights.append({
                        "uuid": node.uuid,
                        "name": node.name,
                        "type": entity_type,
                        "summary": node.summary,
                        "related_facts": related_facts
                    })
            except Exception as e:
                logger.debug(f"Get node {uuid} failed: {e}")
                continue
        
        result.entity_insights = entity_insights
        result.total_entities = len(entity_insights)
        
        # Build relationship chains
        relationship_chains = []
        for edge_data in all_edges:
            if isinstance(edge_data, dict):
                source_uuid = edge_data.get('source_node_uuid', '')
                target_uuid = edge_data.get('target_node_uuid', '')
                relation_name = edge_data.get('name', '')
                
                source_name = edge_data.get('source_node_name') or (node_map.get(source_uuid, NodeInfo('', '', [], '', {})).name or source_uuid[:8])
                target_name = edge_data.get('target_node_name') or (node_map.get(target_uuid, NodeInfo('', '', [], '', {})).name or target_uuid[:8])
                
                chain = f"{source_name} --[{relation_name}]--> {target_name}"
                if chain not in relationship_chains:
                    relationship_chains.append(chain)
        
        result.relationship_chains = relationship_chains
        result.total_relationships = len(relationship_chains)
        
        logger.info(f"InsightForge completed: {result.total_facts} facts, {result.total_entities} entities, {result.total_relationships} relationships")
        return result
    
    def _generate_sub_queries(
        self,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_queries: int = 5
    ) -> List[str]:
        """Use LLM to generate simple keyword-focused search terms"""
        system_prompt = """You are a keyword extraction expert. Extract simple search keywords from a complex question.

CRITICAL RULES:
1. Return SHORT keyword phrases (1-3 words each)
2. Include entity names (people, companies, products)
3. Include action verbs (competes, mentions, discusses)
4. Include topic keywords (market, technology, innovation)
5. NO full sentences or questions - ONLY keywords
6. Return JSON format: {"sub_queries": ["keyword1", "keyword2", ...]}

EXAMPLE:
Query: "How are tech companies responding to market saturation?"
Good: {"sub_queries": ["tech companies", "market saturation", "responds", "Apple", "competition"]}
Bad: {"sub_queries": ["How are tech companies responding to market saturation in the simulation?"]}"""

        user_prompt = f"""Extract {max_queries} simple keyword phrases from this query:

Query: {query}

Context: {simulation_requirement[:200]}

Return SHORT keywords only, not full sentences. Include any entity names mentioned."""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            sub_queries = response.get("sub_queries", [])
            # Filter out any long queries (fallback safety)
            short_queries = [str(sq)[:50] for sq in sub_queries if len(str(sq)) < 100]
            return short_queries[:max_queries] if short_queries else self._extract_keywords_fallback(query)
            
        except Exception as e:
            logger.warning(f"Generating sub-queries failed: {str(e)}, using keyword extraction")
            return self._extract_keywords_fallback(query)
    
    def _extract_keywords_fallback(self, query: str) -> List[str]:
        """Simple keyword extraction fallback"""
        # Extract words longer than 3 characters, excluding common words
        stopwords = {'what', 'how', 'when', 'where', 'which', 'that', 'this', 'with', 'from', 'about', 'into', 'does', 'will', 'would', 'could', 'should', 'have', 'been', 'being', 'their', 'they', 'them', 'there', 'these', 'those', 'some', 'more', 'most', 'other'}
        words = query.lower().replace('?', '').replace(',', '').split()
        keywords = [w for w in words if len(w) > 3 and w not in stopwords]
        return keywords[:5] if keywords else [query[:30]]
    
    def panorama_search(
        self,
        graph_id: str,
        query: str,
        include_expired: bool = True,
        limit: int = 50
    ) -> PanoramaResult:
        """
        [PanoramaSearch - Breadth Search]
        
        Gets full view including all related content and historical/expired information
        """
        logger.info(f"PanoramaSearch Breadth Search: {query[:50]}...")
        
        result = PanoramaResult(query=query)
        
        all_nodes = self.get_all_nodes(graph_id)
        node_map = {n.uuid: n for n in all_nodes}
        result.all_nodes = all_nodes
        result.total_nodes = len(all_nodes)
        
        all_edges = self.get_all_edges(graph_id, include_temporal=True)
        result.all_edges = all_edges
        result.total_edges = len(all_edges)
        
        active_facts = []
        historical_facts = []
        
        for edge in all_edges:
            if not edge.fact:
                continue
            
            is_historical = edge.is_expired or edge.is_invalid
            
            if is_historical:
                valid_at = edge.valid_at or "Unknown"
                invalid_at = edge.invalid_at or edge.expired_at or "Unknown"
                fact_with_time = f"[{valid_at} - {invalid_at}] {edge.fact}"
                historical_facts.append(fact_with_time)
            else:
                active_facts.append(edge.fact)
        
        # Sort by relevance
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(',', ' ').split() if len(w.strip()) > 1]
        
        def relevance_score(fact: str) -> int:
            fact_lower = fact.lower()
            score = 0
            if query_lower in fact_lower:
                score += 100
            for kw in keywords:
                if kw in fact_lower:
                    score += 10
            return score
        
        active_facts.sort(key=relevance_score, reverse=True)
        historical_facts.sort(key=relevance_score, reverse=True)
        
        result.active_facts = active_facts[:limit]
        result.historical_facts = historical_facts[:limit] if include_expired else []
        result.active_count = len(active_facts)
        result.historical_count = len(historical_facts)
        
        logger.info(f"PanoramaSearch completed: {result.active_count} valid, {result.historical_count} historical")
        return result
    
    def quick_search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10
    ) -> SearchResult:
        """
        [QuickSearch - Simple Search]
        
        Quick, lightweight search tool
        """
        logger.info(f"QuickSearch Simple Search: {query[:50]}...")
        
        result = self.search_graph(
            graph_id=graph_id,
            query=query,
            limit=limit,
            scope="edges"
        )
        
        logger.info(f"QuickSearch completed: {result.total_count} results")
        return result
    
    def interview_agents(
        self,
        simulation_id: str,
        interview_requirement: str,
        simulation_requirement: str = "",
        max_agents: int = 5,
        custom_questions: List[str] = None
    ) -> InterviewResult:
        """
        [InterviewAgents - Deep Interview]
        
        Interview simulation Agents using the OASIS interview API
        """
        from .simulation_runner import SimulationRunner
        
        logger.info(f"InterviewAgents Deep Interview: {interview_requirement[:50]}...")
        
        result = InterviewResult(
            interview_topic=interview_requirement,
            interview_questions=custom_questions or []
        )
        
        # Load agent profiles
        profiles = self._load_agent_profiles(simulation_id)
        
        if not profiles:
            logger.warning(f"Persona files not found for simulation {simulation_id}")
            result.summary = "No interviewable Agent personas found"
            return result
        
        result.total_agents = len(profiles)
        logger.info(f"Loaded {len(profiles)} Agent personas")
        
        # Select agents for interview
        selected_agents, selected_indices, selection_reasoning = self._select_agents_for_interview(
            profiles=profiles,
            interview_requirement=interview_requirement,
            simulation_requirement=simulation_requirement,
            max_agents=max_agents
        )
        
        result.selected_agents = selected_agents
        result.selection_reasoning = selection_reasoning
        logger.info(f"Selected {len(selected_agents)} Agents for interview: {selected_indices}")
        
        # Generate interview questions
        if not result.interview_questions:
            result.interview_questions = self._generate_interview_questions(
                interview_requirement=interview_requirement,
                simulation_requirement=simulation_requirement,
                selected_agents=selected_agents
            )
            logger.info(f"Generated {len(result.interview_questions)} interview questions")
        
        combined_prompt = "\n".join([f"{i+1}. {q}" for i, q in enumerate(result.interview_questions)])
        INTERVIEW_PROMPT_PREFIX = "Based on your persona, memories and actions, please reply directly: "
        optimized_prompt = f"{INTERVIEW_PROMPT_PREFIX}{combined_prompt}"
        
        # Call interview API
        try:
            interviews_request = []
            for agent_idx in selected_indices:
                interviews_request.append({
                    "agent_id": agent_idx,
                    "prompt": optimized_prompt
                })
            
            logger.info(f"Calling batch interview API: {len(interviews_request)} Agents")
            
            api_result = SimulationRunner.interview_agents_batch(
                simulation_id=simulation_id,
                interviews=interviews_request,
                platform=None,
                timeout=180.0
            )
            
            logger.info(f"Interview API returned: {api_result.get('interviews_count', 0)} results")
            
            if not api_result.get("success", False):
                error_msg = api_result.get("error", "Unknown error")
                logger.warning(f"Interview API failed: {error_msg}")
                result.summary = f"Interview API call failed: {error_msg}"
                return result
            
            # Parse results
            api_data = api_result.get("result", {})
            results_dict = api_data.get("results", {}) if isinstance(api_data, dict) else {}
            
            for i, agent_idx in enumerate(selected_indices):
                agent = selected_agents[i]
                agent_name = agent.get("realname", agent.get("username", f"Agent_{agent_idx}"))
                agent_role = agent.get("profession", "Unknown")
                agent_bio = agent.get("bio", "")
                
                twitter_result = results_dict.get(f"twitter_{agent_idx}", {})
                reddit_result = results_dict.get(f"reddit_{agent_idx}", {})
                
                twitter_response = twitter_result.get("response", "")
                reddit_response = reddit_result.get("response", "")
                
                response_parts = []
                if twitter_response:
                    response_parts.append(f"[Twitter]\n{twitter_response}")
                if reddit_response:
                    response_parts.append(f"[Reddit]\n{reddit_response}")
                
                response_text = "\n\n".join(response_parts) if response_parts else "[No Response]"
                
                import re
                combined_responses = f"{twitter_response} {reddit_response}"
                key_quotes = re.findall(r'[""''"'']([^""''"'']{10,100})[""''"'']', combined_responses)
                if not key_quotes:
                    sentences = combined_responses.split('.')
                    key_quotes = [s.strip() + '.' for s in sentences if len(s.strip()) > 20][:3]
                
                interview = AgentInterview(
                    agent_name=agent_name,
                    agent_role=agent_role,
                    agent_bio=agent_bio[:1000],
                    question=combined_prompt,
                    response=response_text,
                    key_quotes=key_quotes[:5]
                )
                result.interviews.append(interview)
            
            result.interviewed_count = len(result.interviews)
            
        except ValueError as e:
            logger.warning(f"Interview failed (environment not running?): {e}")
            result.summary = f"Interview failed: {str(e)}. Simulation might be closed."
            return result
        except Exception as e:
            logger.error(f"Interview API exception: {e}")
            import traceback
            logger.error(traceback.format_exc())
            result.summary = f"Error during interview: {str(e)}"
            return result
        
        # Generate summary
        if result.interviews:
            result.summary = self._generate_interview_summary(
                interviews=result.interviews,
                interview_requirement=interview_requirement
            )
        
        logger.info(f"InterviewAgents completed: Interviewed {result.interviewed_count} Agents")
        return result
    
    def _load_agent_profiles(self, simulation_id: str) -> List[Dict[str, Any]]:
        """Load simulation Agent persona files"""
        import os
        import csv
        
        sim_dir = os.path.join(
            os.path.dirname(__file__), 
            f'../../uploads/simulations/{simulation_id}'
        )
        
        profiles = []
        
        reddit_profile_path = os.path.join(sim_dir, "reddit_profiles.json")
        if os.path.exists(reddit_profile_path):
            try:
                with open(reddit_profile_path, 'r', encoding='utf-8') as f:
                    profiles = json.load(f)
                logger.info(f"Loaded {len(profiles)} personas from reddit_profiles.json")
                return profiles
            except Exception as e:
                logger.warning(f"Read reddit_profiles.json failed: {e}")
        
        twitter_profile_path = os.path.join(sim_dir, "twitter_profiles.csv")
        if os.path.exists(twitter_profile_path):
            try:
                with open(twitter_profile_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        profiles.append({
                            "realname": row.get("name", ""),
                            "username": row.get("username", ""),
                            "bio": row.get("description", ""),
                            "persona": row.get("user_char", ""),
                            "profession": "Unknown"
                        })
                logger.info(f"Loaded {len(profiles)} personas from twitter_profiles.csv")
                return profiles
            except Exception as e:
                logger.warning(f"Read twitter_profiles.csv failed: {e}")
        
        return profiles
    
    def _select_agents_for_interview(
        self,
        profiles: List[Dict[str, Any]],
        interview_requirement: str,
        simulation_requirement: str,
        max_agents: int
    ) -> tuple:
        """Use LLM to select Agents to interview"""
        
        agent_summaries = []
        for i, profile in enumerate(profiles):
            summary = {
                "index": i,
                "name": profile.get("realname", profile.get("username", f"Agent_{i}")),
                "profession": profile.get("profession", "Unknown"),
                "bio": profile.get("bio", "")[:200],
            }
            agent_summaries.append(summary)
        
        system_prompt = """Select the most suitable interview candidates from the simulation Agent list.

Selection Criteria:
1. Agent's identity relates to interview topic
2. Agent likely holds unique views
3. Select diverse perspectives
4. Prioritize actors directly involved

Return JSON: {"selected_indices": [list of indices], "reasoning": "explanation"}"""

        user_prompt = f"""Interview Requirement: {interview_requirement}

Simulation Background: {simulation_requirement if simulation_requirement else "Not provided"}

Selectable Agents ({len(agent_summaries)} total):
{json.dumps(agent_summaries, ensure_ascii=False, indent=2)}

Select at most {max_agents} suitable Agents."""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            selected_indices = response.get("selected_indices", [])[:max_agents]
            reasoning = response.get("reasoning", "Auto-selected based on relevance")
            
            selected_agents = []
            valid_indices = []
            for idx in selected_indices:
                if 0 <= idx < len(profiles):
                    selected_agents.append(profiles[idx])
                    valid_indices.append(idx)
            
            return selected_agents, valid_indices, reasoning
            
        except Exception as e:
            logger.warning(f"LLM Agent selection failed: {e}")
            selected = profiles[:max_agents]
            indices = list(range(min(max_agents, len(profiles))))
            return selected, indices, "Using default selection"
    
    def _generate_interview_questions(
        self,
        interview_requirement: str,
        simulation_requirement: str,
        selected_agents: List[Dict[str, Any]]
    ) -> List[str]:
        """Use LLM to generate interview questions"""
        
        agent_roles = [a.get("profession", "Unknown") for a in selected_agents]
        
        system_prompt = """Generate 3-5 deep interview questions.

Requirements:
1. Open-ended questions
2. May yield different answers for different roles
3. Cover facts, opinions, and feelings
4. Natural language

Return JSON: {"questions": ["Question 1", ...]}"""

        user_prompt = f"""Interview Requirement: {interview_requirement}
Simulation Background: {simulation_requirement if simulation_requirement else "Not provided"}
Interviewee Roles: {', '.join(agent_roles)}

Generate 3-5 interview questions."""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.5
            )
            
            return response.get("questions", [f"What are your thoughts on {interview_requirement}?"])
            
        except Exception as e:
            logger.warning(f"Generating questions failed: {e}")
            return [
                f"What is your view on {interview_requirement}?",
                "How does this affect you or your group?",
                "How should this issue be resolved?"
            ]
    
    def _generate_interview_summary(
        self,
        interviews: List[AgentInterview],
        interview_requirement: str
    ) -> str:
        """Generate interview summary"""
        
        if not interviews:
            return "No interviews completed"
        
        interview_texts = []
        for interview in interviews:
            interview_texts.append(f"[{interview.agent_name} ({interview.agent_role})]\n{interview.response[:500]}")
        
        system_prompt = """Generate an interview summary.

Requirements:
1. Distill key points from all parties
2. Point out consensus and divergence
3. Highlight valuable quotes
4. Objective and neutral
5. Keep within 1000 characters"""

        user_prompt = f"""Interview Topic: {interview_requirement}

Interview Content:
{"".join(interview_texts)}

Generate the summary."""

        try:
            summary = self.llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            return summary
            
        except Exception as e:
            logger.warning(f"Generating summary failed: {e}")
            return f"Interviewed {len(interviews)} people: " + ", ".join([i.agent_name for i in interviews])


# Backward compatibility alias
ZepToolsService = Neo4jToolsService
