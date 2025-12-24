"""
Zepsearchtoolservice
封装图谱search、nodesread、edgesqueryetctool，供Report Agentuse

核心searchtool（优化后）：
1. InsightForge（Deepinsightsearch）- 最强大ofhybridsearch，自动generate子问题并多维度search
2. PanoramaSearch（广度search）- get全貌，package括expiredcontent
3. QuickSearch（简单search）- quicksearch
"""

import time
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient

logger = get_logger('mirofish.zep_tools')


@dataclass
class SearchResult:
    """searchresult"""
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
        """Convertfor文本format，供LLM理解"""
        text_parts = [f"searchquery: {self.query}", f"找到 {self.total_count} relatedinformation"]
        
        if self.facts:
            text_parts.append("\n### relatedfacts:")
            for i, fact in enumerate(self.facts, 1):
                text_parts.append(f"{i}. {fact}")
        
        return "\n".join(text_parts)


@dataclass
class NodeInfo:
    """nodeinformation"""
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
        """Convertfor文本format"""
        entity_type = next((l for l in self.labels if l not in ["Entity", "Node"]), "not知type")
        return f"entity: {self.name} (type: {entity_type})\n摘want: {self.summary}"


@dataclass
class EdgeInfo:
    """edgeinformation"""
    uuid: str
    name: str
    fact: str
    source_node_uuid: str
    target_node_uuid: str
    source_node_name: Optional[str] = None
    target_node_name: Optional[str] = None
    # timeinformation
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
        """Convertfor文本format"""
        source = self.source_node_name or self.source_node_uuid[:8]
        target = self.target_node_name or self.target_node_uuid[:8]
        base_text = f"relationship: {source} --[{self.name}]--> {target}\nfacts: {self.fact}"
        
        if include_temporal:
            valid_at = self.valid_at or "not知"
            invalid_at = self.invalid_at or "至今"
            base_text += f"\n时效: {valid_at} - {invalid_at}"
            if self.expired_at:
                base_text += f" (alreadyexpired: {self.expired_at})"
        
        return base_text
    
    @property
    def is_expired(self) -> bool:
        """whether toalreadyexpired"""
        return self.expired_at is not None
    
    @property
    def is_invalid(self) -> bool:
        """whether toalready失效"""
        return self.invalid_at is not None


@dataclass
class InsightForgeResult:
    """
    Deepinsightsearchresult (InsightForge)
    contains多子问题ofsearchresult，and综合分析
    """
    query: str
    simulation_requirement: str
    sub_queries: List[str]
    
    # 各维度retrievalresult
    semantic_facts: List[str] = field(default_factory=list)  # 语义searchresult
    entity_insights: List[Dict[str, Any]] = field(default_factory=list)  # entityinsight
    relationship_chains: List[str] = field(default_factory=list)  # relationship链
    
    # statisticsinformation
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
        """Convertfordetailedof文本format，供LLM理解"""
        text_parts = [
            f"## notcome预测Deep分析",
            f"分析问题: {self.query}",
            f"预测场景: {self.simulation_requirement}",
            f"\n### 预测count据statistics",
            f"- related预测facts: {self.total_facts}",
            f"- 涉andentity: {self.total_entities}",
            f"- relationship链: {self.total_relationships}"
        ]
        
        # 子问题
        if self.sub_queries:
            text_parts.append(f"\n### 分析of子问题")
            for i, sq in enumerate(self.sub_queries, 1):
                text_parts.append(f"{i}. {sq}")
        
        # 语义searchresult
        if self.semantic_facts:
            text_parts.append(f"\n### 【关keyfacts】(请inreport 引usethis些原文)")
            for i, fact in enumerate(self.semantic_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        # entityinsight
        if self.entity_insights:
            text_parts.append(f"\n### 【核心entity】")
            for entity in self.entity_insights:
                text_parts.append(f"- **{entity.get('name', 'not知')}** ({entity.get('type', 'entity')})")
                if entity.get('summary'):
                    text_parts.append(f"  摘want: \"{entity.get('summary')}\"")
                if entity.get('related_facts'):
                    text_parts.append(f"  relatedfacts: {len(entity.get('related_facts', []))}")
        
        # relationship链
        if self.relationship_chains:
            text_parts.append(f"\n### 【relationship链】")
            for chain in self.relationship_chains:
                text_parts.append(f"- {chain}")
        
        return "\n".join(text_parts)


@dataclass
class PanoramaResult:
    """
    广度searchresult (Panorama)
    contains所haverelatedinformation，package括expiredcontent
    """
    query: str
    
    # 全部node
    all_nodes: List[NodeInfo] = field(default_factory=list)
    # 全部edge（package括expiredof）
    all_edges: List[EdgeInfo] = field(default_factory=list)
    # Currenthave效offacts
    active_facts: List[str] = field(default_factory=list)
    # alreadyexpired/失效offacts（historyrecord）
    historical_facts: List[str] = field(default_factory=list)
    
    # statistics
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
        """Convertfor文本format（complete版本，not截断）"""
        text_parts = [
            f"## 广度searchresult（notcomepanoramaview）",
            f"query: {self.query}",
            f"\n### statisticsinformation",
            f"- Totalnodecount: {self.total_nodes}",
            f"- Totaledgecount: {self.total_edges}",
            f"- Currenthave效facts: {self.active_count}",
            f"- history/expiredfacts: {self.historical_count}"
        ]
        
        # Currenthave效offacts（complete输出，not截断）
        if self.active_facts:
            text_parts.append(f"\n### 【Currenthave效facts】(simulationresult原文)")
            for i, fact in enumerate(self.active_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        # history/expiredfacts（complete输出，not截断）
        if self.historical_facts:
            text_parts.append(f"\n### 【history/expiredfacts】(演变过程record)")
            for i, fact in enumerate(self.historical_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        # 关keyentity（complete输出，not截断）
        if self.all_nodes:
            text_parts.append(f"\n### 【涉andentity】")
            for node in self.all_nodes:
                entity_type = next((l for l in node.labels if l not in ["Entity", "Node"]), "entity")
                text_parts.append(f"- **{node.name}** ({entity_type})")
        
        return "\n".join(text_parts)


@dataclass
class AgentInterview:
    """单Agentof采访result"""
    agent_name: str
    agent_role: str  # 角色type（如：学生、教师、媒体etc）
    agent_bio: str  # 简介
    question: str  # 采访问题
    response: str  # 采访回答
    key_quotes: List[str] = field(default_factory=list)  # 关key引言
    
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
        # 显示completeofagent_bio，not截断
        text += f"_简介: {self.agent_bio}_\n\n"
        text += f"**Q:** {self.question}\n\n"
        text += f"**A:** {self.response}\n"
        if self.key_quotes:
            text += "\n**关key引言:**\n"
            for quote in self.key_quotes:
                text += f"> \"{quote}\"\n"
        return text


@dataclass
class InterviewResult:
    """
    采访result (Interview)
    contains多simulationAgentof采访回答
    """
    interview_topic: str  # 采访主题
    interview_questions: List[str]  # 采访问题list
    
    # 采访选择ofAgent
    selected_agents: List[Dict[str, Any]] = field(default_factory=list)
    # 各Agentof采访回答
    interviews: List[AgentInterview] = field(default_factory=list)
    
    # 选择Agentof理由
    selection_reasoning: str = ""
    # 整合后of采访摘want
    summary: str = ""
    
    # statistics
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
        """Convertfordetailedof文本format，供LLM理解andreport引use"""
        text_parts = [
            f"## 🎤 Deep采访report",
            f"**采访主题:** {self.interview_topic}",
            f"**采访peoplecount:** {self.interviewed_count} / {self.total_agents} 位simulationAgent",
            f"\n### 采访object选择理由",
            f"{self.selection_reasoning}",
            f"\n---"
        ]
        
        # 各Agentof采访content
        if self.interviews:
            text_parts.append(f"\n### 采访实录")
            for i, interview in enumerate(self.interviews, 1):
                text_parts.append(f"\n#### 采访 #{i}: {interview.agent_name}")
                text_parts.append(interview.to_text())
                text_parts.append("\n---")
        
        # 采访摘want
        if self.summary:
            text_parts.append(f"\n### 采访摘wantwith核心观点")
            text_parts.append(self.summary)
        
        return "\n".join(text_parts)


class ZepToolsService:
    """
    Zepsearchtoolservice
    
    【核心searchtool - 优化后】
    1. insight_forge - Deepinsightsearch（最强大，自动generate子问题，多维度search）
    2. panorama_search - 广度search（get全貌，package括expiredcontent）
    3. quick_search - 简单search（quicksearch）
    4. interview_agents - Deep采访（采访simulationAgent，get多视角观点）
    
    【基础tool】
    - search_graph - 图谱语义search
    - get_all_nodes - get图谱所havenodes
    - get_all_edges - get图谱所haveedges（含timeinformation）
    - get_node_detail - getnodesdetailed informationrmation
    - get_node_edges - getnodesrelatedofedges
    - get_entities_by_type - Bytypegetentities
    - get_entity_summary - getentitiesofrelationships摘want
    """
    
    # retryconfiguration
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0
    
    def __init__(self, api_key: Optional[str] = None, llm_client: Optional[LLMClient] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY not configured")
        
        self.client = Zep(api_key=self.api_key)
        # LLM客户端use于InsightForgegeneration子问题
        self._llm_client = llm_client
        logger.info("ZepToolsService initializationcompleted")
    
    @property
    def llm(self) -> LLMClient:
        """延迟initializationLLM客户端"""
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client
    
    def _call_with_retry(self, func, operation_name: str, max_retries: int = None):
        """带retry机制ofAPIcall"""
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
                        f"Zep {operation_name} 第 {attempt + 1} attemptsfailed: {str(e)[:100]}, "
                        f"{delay:.1f}秒后retry..."
                    )
                    time.sleep(delay)
                    delay *= 2
                else:
                    logger.error(f"Zep {operation_name} in {max_retries} attempts后仍failed: {str(e)}")
        
        raise last_exception
    
    def search_graph(
        self, 
        graph_id: str, 
        query: str, 
        limit: int = 10,
        scope: str = "edges"
    ) -> SearchResult:
        """
        图谱语义search
        
        usehybridsearch（语义+BM25）in图谱 searchrelatedinformation。
        ifZep Cloudofsearch APInot can use，则降级for本地关key词匹配。
        
        Args:
            graph_id: 图谱ID (Standalone Graph)
            query: searchquery
            limit: returnresultquantity
            scope: search范围，"edges"  or  "nodes"
            
        Returns:
            SearchResult: searchresult
        """
        logger.info(f"graphsearch: graph_id={graph_id}, query={query[:50]}...")
        
        # 尝试useZep Cloud Search API
        try:
            search_results = self._call_with_retry(
                func=lambda: self.client.graph.search(
                    graph_id=graph_id,
                    query=query,
                    limit=limit,
                    scope=scope,
                    reranker="cross_encoder"
                ),
                operation_name=f"graphsearch(graph={graph_id})"
            )
            
            facts = []
            edges = []
            nodes = []
            
            # parseedgesearchresult
            if hasattr(search_results, 'edges') and search_results.edges:
                for edge in search_results.edges:
                    if hasattr(edge, 'fact') and edge.fact:
                        facts.append(edge.fact)
                    edges.append({
                        "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                        "name": getattr(edge, 'name', ''),
                        "fact": getattr(edge, 'fact', ''),
                        "source_node_uuid": getattr(edge, 'source_node_uuid', ''),
                        "target_node_uuid": getattr(edge, 'target_node_uuid', ''),
                    })
            
            # parsenodesearchresult
            if hasattr(search_results, 'nodes') and search_results.nodes:
                for node in search_results.nodes:
                    nodes.append({
                        "uuid": getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                        "name": getattr(node, 'name', ''),
                        "labels": getattr(node, 'labels', []),
                        "summary": getattr(node, 'summary', ''),
                    })
                    # node摘wantalso算作facts
                    if hasattr(node, 'summary') and node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")
            
            logger.info(f"searchcompleted: 找到 {len(facts)} relatedfacts")
            
            return SearchResult(
                facts=facts,
                edges=edges,
                nodes=nodes,
                query=query,
                total_count=len(facts)
            )
            
        except Exception as e:
            logger.warning(f"Zep Search APIfailed，降级for本地search: {str(e)}")
            # 降级：use本地关key词匹配search
            return self._local_search(graph_id, query, limit, scope)
    
    def _local_search(
        self, 
        graph_id: str, 
        query: str, 
        limit: int = 10,
        scope: str = "edges"
    ) -> SearchResult:
        """
        本地关key词匹配search（作forZep Search APIof降级方案）
        
        get所haveedges/nodes，thenin本地进行关key词匹配
        
        Args:
            graph_id: 图谱ID
            query: searchquery
            limit: returnresultquantity
            scope: search范围
            
        Returns:
            SearchResult: searchresult
        """
        logger.info(f"use本地search: query={query[:30]}...")
        
        facts = []
        edges_result = []
        nodes_result = []
        
        # Extractquery关key词（简单分词）
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(',', ' ').replace('，', ' ').split() if len(w.strip()) > 1]
        
        def match_score(text: str) -> int:
            """计算文本withqueryof匹配分count"""
            if not text:
                return 0
            text_lower = text.lower()
            # 完全匹配query
            if query_lower in text_lower:
                return 100
            # 关key词匹配
            score = 0
            for keyword in keywords:
                if keyword in text_lower:
                    score += 10
            return score
        
        try:
            if scope in ["edges", "both"]:
                # get所haveedge并匹配
                all_edges = self.get_all_edges(graph_id)
                scored_edges = []
                for edge in all_edges:
                    score = match_score(edge.fact) + match_score(edge.name)
                    if score > 0:
                        scored_edges.append((score, edge))
                
                # By分countsort
                scored_edges.sort(key=lambda x: x[0], reverse=True)
                
                for score, edge in scored_edges[:limit]:
                    if edge.fact:
                        facts.append(edge.fact)
                    edges_result.append({
                        "uuid": edge.uuid,
                        "name": edge.name,
                        "fact": edge.fact,
                        "source_node_uuid": edge.source_node_uuid,
                        "target_node_uuid": edge.target_node_uuid,
                    })
            
            if scope in ["nodes", "both"]:
                # get所havenode并匹配
                all_nodes = self.get_all_nodes(graph_id)
                scored_nodes = []
                for node in all_nodes:
                    score = match_score(node.name) + match_score(node.summary)
                    if score > 0:
                        scored_nodes.append((score, node))
                
                scored_nodes.sort(key=lambda x: x[0], reverse=True)
                
                for score, node in scored_nodes[:limit]:
                    nodes_result.append({
                        "uuid": node.uuid,
                        "name": node.name,
                        "labels": node.labels,
                        "summary": node.summary,
                    })
                    if node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")
            
            logger.info(f"本地searchcompleted: 找到 {len(facts)} relatedfacts")
            
        except Exception as e:
            logger.error(f"本地searchfailed: {str(e)}")
        
        return SearchResult(
            facts=facts,
            edges=edges_result,
            nodes=nodes_result,
            query=query,
            total_count=len(facts)
        )
    
    def get_all_nodes(self, graph_id: str) -> List[NodeInfo]:
        """
        get图谱of所havenodes
        
        Args:
            graph_id: 图谱ID
            
        Returns:
            nodeslist
        """
        logger.info(f"getgraph {graph_id} of所havenode...")
        
        nodes = self._call_with_retry(
            func=lambda: self.client.graph.node.get_by_graph_id(graph_id=graph_id),
            operation_name=f"getnode(graph={graph_id})"
        )
        
        result = []
        for node in nodes:
            result.append(NodeInfo(
                uuid=getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {}
            ))
        
        logger.info(f"get到 {len(result)} node")
        return result
    
    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> List[EdgeInfo]:
        """
        get图谱of所haveedges（containstimeinformation）
        
        Args:
            graph_id: 图谱ID
            include_temporal: whether tocontainstimeinformation（默认True）
            
        Returns:
            edgeslist（containscreated_at, valid_at, invalid_at, expired_at）
        """
        logger.info(f"getgraph {graph_id} of所haveedge...")
        
        edges = self._call_with_retry(
            func=lambda: self.client.graph.edge.get_by_graph_id(graph_id=graph_id),
            operation_name=f"getedge(graph={graph_id})"
        )
        
        result = []
        for edge in edges:
            edge_information = EdgeInfo(
                uuid=getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                name=edge.name or "",
                fact=edge.fact or "",
                source_node_uuid=edge.source_node_uuid or "",
                target_node_uuid=edge.target_node_uuid or ""
            )
            
            # 添加timeinformation
            if include_temporal:
                edge_information.created_at = getattr(edge, 'created_at', None)
                edge_information.valid_at = getattr(edge, 'valid_at', None)
                edge_information.invalid_at = getattr(edge, 'invalid_at', None)
                edge_information.expired_at = getattr(edge, 'expired_at', None)
            
            result.append(edge_information)
        
        logger.info(f"get到 {len(result)} edge")
        return result
    
    def get_node_detail(self, node_uuid: str) -> Optional[NodeInfo]:
        """
        get单nodesofdetailed informationrmation
        
        Args:
            node_uuid: nodesUUID
            
        Returns:
            nodesinformation or None
        """
        logger.info(f"getnode详情: {node_uuid[:8]}...")
        
        try:
            node = self._call_with_retry(
                func=lambda: self.client.graph.node.get(uuid_=node_uuid),
                operation_name=f"getnode详情(uuid={node_uuid[:8]}...)"
            )
            
            if not node:
                return None
            
            return NodeInfo(
                uuid=getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {}
            )
        except Exception as e:
            logger.error(f"getnode详情failed: {str(e)}")
            return None
    
    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[EdgeInfo]:
        """
        getnodesrelatedof所haveedges
        
        throughget图谱所haveedges，thenfilter出with指定nodesrelatedofedges
        
        Args:
            graph_id: 图谱ID
            node_uuid: nodesUUID
            
        Returns:
            edgeslist
        """
        logger.info(f"getnode {node_uuid[:8]}... ofrelatededge")
        
        try:
            # getgraph所haveedge，thenfilter
            all_edges = self.get_all_edges(graph_id)
            
            result = []
            for edge in all_edges:
                # checkedgewhether towith指定noderelated（作for源 or 目标）
                if edge.source_node_uuid == node_uuid or edge.target_node_uuid == node_uuid:
                    result.append(edge)
            
            logger.info(f"找到 {len(result)} withnoderelatedofedge")
            return result
            
        except Exception as e:
            logger.warning(f"getnodeedgefailed: {str(e)}")
            return []
    
    def get_entities_by_type(
        self, 
        graph_id: str, 
        entity_type: str
    ) -> List[NodeInfo]:
        """
        Bytypegetentities
        
        Args:
            graph_id: 图谱ID
            entity_type: entitiestype（如 Student, PublicFigure etc）
            
        Returns:
            符合typeofentitieslist
        """
        logger.info(f"gettypefor {entity_type} ofentity...")
        
        all_nodes = self.get_all_nodes(graph_id)
        
        filtered = []
        for node in all_nodes:
            # checklabelswhether tocontains指定type
            if entity_type in node.labels:
                filtered.append(node)
        
        logger.info(f"找到 {len(filtered)}  {entity_type} typeofentity")
        return filtered
    
    def get_entity_summary(
        self, 
        graph_id: str, 
        entity_name: str
    ) -> Dict[str, Any]:
        """
        get指定entitiesofrelationships摘want
        
        searchwith该entitiesrelatedof所haveinformation，并generate摘want
        
        Args:
            graph_id: 图谱ID
            entity_name: entities名称
            
        Returns:
            entities摘wantinformation
        """
        logger.info(f"getentity {entity_name} ofrelationship摘want...")
        
        # firstsearch该entityrelatedofinformation
        search_result = self.search_graph(
            graph_id=graph_id,
            query=entity_name,
            limit=20
        )
        
        # 尝试in所havenode 找到该entity
        all_nodes = self.get_all_nodes(graph_id)
        entity_node = None
        for node in all_nodes:
            if node.name.lower() == entity_name.lower():
                entity_node = node
                break
        
        related_edges = []
        if entity_node:
            # 传入graph_idparameters
            related_edges = self.get_node_edges(graph_id, entity_node.uuid)
        
        return {
            "entity_name": entity_name,
            "entity_information": entity_node.to_dict() if entity_node else None,
            "related_facts": search_result.facts,
            "related_edges": [e.to_dict() for e in related_edges],
            "total_relations": len(related_edges)
        }
    
    def get_graph_statistics(self, graph_id: str) -> Dict[str, Any]:
        """
        get图谱ofstatisticsinformation
        
        Args:
            graph_id: 图谱ID
            
        Returns:
            statisticsinformation
        """
        logger.info(f"getgraph {graph_id} ofstatisticsinformation...")
        
        nodes = self.get_all_nodes(graph_id)
        edges = self.get_all_edges(graph_id)
        
        # statisticsentity types分布
        entity_types = {}
        for node in nodes:
            for label in node.labels:
                if label not in ["Entity", "Node"]:
                    entity_types[label] = entity_types.get(label, 0) + 1
        
        # statisticsrelationship types分布
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
        """
        getsimulationrelatedof上下文information
        
        综合searchwithsimulationrequirementrelatedof所haveinformation
        
        Args:
            graph_id: 图谱ID
            simulation_requirement: simulationrequirementdescription
            limit: 每classinformationofquantity限制
            
        Returns:
            simulation上下文information
        """
        logger.info(f"getsimulation上下文: {simulation_requirement[:50]}...")
        
        # searchwithsimulationrequirementrelatedofinformation
        search_result = self.search_graph(
            graph_id=graph_id,
            query=simulation_requirement,
            limit=limit
        )
        
        # getgraphstatistics
        stats = self.get_graph_statistics(graph_id)
        
        # get所haveentitynode
        all_nodes = self.get_all_nodes(graph_id)
        
        # 筛选have实际typeofentity（非纯Entitynode）
        entities = []
        for node in all_nodes:
            custom_labels = [l for l in node.labels if l not in ["Entity", "Node"]]
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
            "entities": entities[:limit],  # 限制quantity
            "total_entities": len(entities)
        }
    
    # ========== 核心retrievaltool（优化后） ==========
    
    def insight_forge(
        self,
        graph_id: str,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_sub_queries: int = 5
    ) -> InsightForgeResult:
        """
        【InsightForge - Deepinsightsearch】
        
        最强大ofhybridsearchfunction，自动分解问题并多维度search：
        1. useLLM will 问题分解for多子问题
        2. to每子问题进行语义search
        3. Extractrelatedentities并get其detailed informationrmation
        4. 追踪relationships链
        5. 整合所haveresult，generateDeepinsight
        
        Args:
            graph_id: 图谱ID
            query: user问题
            simulation_requirement: simulationrequirementdescription
            report_context: report上下文（ can 选，use于更精准of子问题generate）
            max_sub_queries: maximum子问题quantity
            
        Returns:
            InsightForgeResult: Deepinsightsearchresult
        """
        logger.info(f"InsightForge Deepinsightretrieval: {query[:50]}...")
        
        result = InsightForgeResult(
            query=query,
            simulation_requirement=simulation_requirement,
            sub_queries=[]
        )
        
        # Step 1: useLLMgeneration子问题
        sub_queries = self._generate_sub_queries(
            query=query,
            simulation_requirement=simulation_requirement,
            report_context=report_context,
            max_queries=max_sub_queries
        )
        result.sub_queries = sub_queries
        logger.info(f"generation {len(sub_queries)} 子问题")
        
        # Step 2: to每子问题进行语义search
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
        
        # to原始问题also进行search
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
        
        # Step 3: fromedge ExtractrelatedentityUUID，只getthis些entitiesofinformation（notget全部node）
        entity_uuids = set()
        for edge_data in all_edges:
            if isinstance(edge_data, dict):
                source_uuid = edge_data.get('source_node_uuid', '')
                target_uuid = edge_data.get('target_node_uuid', '')
                if source_uuid:
                    entity_uuids.add(source_uuid)
                if target_uuid:
                    entity_uuids.add(target_uuid)
        
        # get所haverelatedentityof详情（not限制quantity，complete输出）
        entity_insights = []
        node_map = {}  # use于后续relationship链构建
        
        for uuid in list(entity_uuids):  # processing所haveentity，not截断
            if not uuid:
                continue
            try:
                # 单独get每relatednodeofinformation
                node = self.get_node_detail(uuid)
                if node:
                    node_map[uuid] = node
                    entity_type = next((l for l in node.labels if l not in ["Entity", "Node"]), "entity")
                    
                    # get该entityrelatedof所havefacts（not截断）
                    related_facts = [
                        f for f in all_facts 
                        if node.name.lower() in f.lower()
                    ]
                    
                    entity_insights.append({
                        "uuid": node.uuid,
                        "name": node.name,
                        "type": entity_type,
                        "summary": node.summary,
                        "related_facts": related_facts  # complete输出，not截断
                    })
            except Exception as e:
                logger.debug(f"getnode {uuid} failed: {e}")
                continue
        
        result.entity_insights = entity_insights
        result.total_entities = len(entity_insights)
        
        # Step 4: 构建所haverelationship链（not限制quantity）
        relationship_chains = []
        for edge_data in all_edges:  # processing所haveedge，not截断
            if isinstance(edge_data, dict):
                source_uuid = edge_data.get('source_node_uuid', '')
                target_uuid = edge_data.get('target_node_uuid', '')
                relation_name = edge_data.get('name', '')
                
                source_name = node_map.get(source_uuid, NodeInfo('', '', [], '', {})).name or source_uuid[:8]
                target_name = node_map.get(target_uuid, NodeInfo('', '', [], '', {})).name or target_uuid[:8]
                
                chain = f"{source_name} --[{relation_name}]--> {target_name}"
                if chain not in relationship_chains:
                    relationship_chains.append(chain)
        
        result.relationship_chains = relationship_chains
        result.total_relationships = len(relationship_chains)
        
        logger.info(f"InsightForgecompleted: {result.total_facts}facts, {result.total_entities}entity, {result.total_relationships}relationship")
        return result
    
    def _generate_sub_queries(
        self,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_queries: int = 5
    ) -> List[str]:
        """
        useLLMgenerate子问题
        
         will 复杂问题分解for多can独立searchof子问题
        """
        system_prompt = """youis a专业of问题分析专家。youof任务is will 一复杂问题分解for多caninsimulation世界 独立观察of子问题。

want求：
1. 每子问题should足够具体，caninsimulation世界 找到relatedofAgent行for or 事件
2. 子问题should覆盖原问题ofnot同维度（如：谁、什么、for什么、怎么样、何时、何地）
3. 子问题shouldwithsimulation场景related
4. returnJSONformat：{"sub_queries": ["子问题1", "子问题2", ...]}"""

        user_prompt = f"""simulationrequirement背景：
{simulation_requirement}

{f"report上下文：{report_context[:500]}" if report_context else ""}

请 will 以下问题分解for{max_queries}子问题：
{query}

returnJSONformatof子问题list。"""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            sub_queries = response.get("sub_queries", [])
            # 确保isstringlist
            return [str(sq) for sq in sub_queries[:max_queries]]
            
        except Exception as e:
            logger.warning(f"generation子问题failed: {str(e)}，use默认子问题")
            # 降级：return基于原问题of变体
            return [
                query,
                f"{query} of主want参with者",
                f"{query} of原因and影响",
                f"{query} of发展过程"
            ][:max_queries]
    
    def panorama_search(
        self,
        graph_id: str,
        query: str,
        include_expired: bool = True,
        limit: int = 50
    ) -> PanoramaResult:
        """
        【PanoramaSearch - 广度search】
        
        get全貌view，package括所haverelatedcontentandhistory/expiredinformation：
        1. get所haverelatednodes
        2. get所haveedges（package括 already expired/失效of）
        3. 分class整理Currenthave效andhistoryinformation
        
        thistool适use于需want解事件全貌、追踪演变过程of场景。
        
        Args:
            graph_id: 图谱ID
            query: searchquery（use于related性sort）
            include_expired: whether tocontainsexpiredcontent（默认True）
            limit: returnresultquantity限制
            
        Returns:
            PanoramaResult: 广度searchresult
        """
        logger.info(f"PanoramaSearch 广度search: {query[:50]}...")
        
        result = PanoramaResult(query=query)
        
        # get所havenode
        all_nodes = self.get_all_nodes(graph_id)
        node_map = {n.uuid: n for n in all_nodes}
        result.all_nodes = all_nodes
        result.total_nodes = len(all_nodes)
        
        # get所haveedge（containstimeinformation）
        all_edges = self.get_all_edges(graph_id, include_temporal=True)
        result.all_edges = all_edges
        result.total_edges = len(all_edges)
        
        # 分classfacts
        active_facts = []
        historical_facts = []
        
        for edge in all_edges:
            if not edge.fact:
                continue
            
            # forfacts添加entity名称
            source_name = node_map.get(edge.source_node_uuid, NodeInfo('', '', [], '', {})).name or edge.source_node_uuid[:8]
            target_name = node_map.get(edge.target_node_uuid, NodeInfo('', '', [], '', {})).name or edge.target_node_uuid[:8]
            
            # 判断whether toexpired/失效
            is_historical = edge.is_expired or edge.is_invalid
            
            if is_historical:
                # history/expiredfacts，添加time标记
                valid_at = edge.valid_at or "not知"
                invalid_at = edge.invalid_at or edge.expired_at or "not知"
                fact_with_time = f"[{valid_at} - {invalid_at}] {edge.fact}"
                historical_facts.append(fact_with_time)
            else:
                # Currenthave效facts
                active_facts.append(edge.fact)
        
        # 基于query进行related性sort
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(',', ' ').replace('，', ' ').split() if len(w.strip()) > 1]
        
        def relevance_score(fact: str) -> int:
            fact_lower = fact.lower()
            score = 0
            if query_lower in fact_lower:
                score += 100
            for kw in keywords:
                if kw in fact_lower:
                    score += 10
            return score
        
        # sort并限制quantity
        active_facts.sort(key=relevance_score, reverse=True)
        historical_facts.sort(key=relevance_score, reverse=True)
        
        result.active_facts = active_facts[:limit]
        result.historical_facts = historical_facts[:limit] if include_expired else []
        result.active_count = len(active_facts)
        result.historical_count = len(historical_facts)
        
        logger.info(f"PanoramaSearchcompleted: {result.active_count}have效, {result.historical_count}history")
        return result
    
    def quick_search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10
    ) -> SearchResult:
        """
        【QuickSearch - 简单search】
        
        quick、轻量级ofsearchtool：
        1. 直接callZep语义search
        2. return最relatedofresult
        3. 适use于简单、直接ofsearchrequirement
        
        Args:
            graph_id: 图谱ID
            query: searchquery
            limit: returnresultquantity
            
        Returns:
            SearchResult: searchresult
        """
        logger.info(f"QuickSearch 简单search: {query[:50]}...")
        
        # 直接call现haveofsearch_graphmethod
        result = self.search_graph(
            graph_id=graph_id,
            query=query,
            limit=limit,
            scope="edges"
        )
        
        logger.info(f"QuickSearchcompleted: {result.total_count}result")
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
        【InterviewAgents - Deep采访】
        
        call真实ofOASIS采访API，采访simulation 正inrunningofAgent：
        1. 自动readpeople设file，解所havesimulationAgent
        2. useLLM分析采访requirement，智can选择最relatedofAgent
        3. useLLMgenerate采访问题
        4. call /api/simulation/interview/batch interface进行真实采访（双平台同时采访）
        5. 整合所have采访result，generate采访report
        
        【重want】此function需wantsimulation环境处于runningstatus（OASIS环境 not 关闭）
        
        【use场景】
        - 需wantfromnot同角色视角解事件look法
        - 需want收集多方意见and观点
        - 需wantgetsimulationAgentof真实回答（非LLMsimulation）
        
        Args:
            simulation_id: simulationID（use于定位people设fileandcall采访API）
            interview_requirement: 采访requirementdescription（非structure化，如"解学生to事件oflook法"）
            simulation_requirement: simulationrequirement背景（ can 选）
            max_agents: 最多采访ofAgentquantity
            custom_questions: 自定义采访问题（ can 选，若not提供则自动generate）
            
        Returns:
            InterviewResult: 采访result
        """
        from .simulation_runner import SimulationRunner
        
        logger.info(f"InterviewAgents Deep采访（真实API）: {interview_requirement[:50]}...")
        
        result = InterviewResult(
            interview_topic=interview_requirement,
            interview_questions=custom_questions or []
        )
        
        # Step 1: readpeople设file
        profiles = self._load_agent_profiles(simulation_id)
        
        if not profiles:
            logger.warning(f"not找到simulation {simulation_id} ofpeople设file")
            result.summary = "not找到 can 采访ofAgentpeople设file"
            return result
        
        result.total_agents = len(profiles)
        logger.info(f"load到 {len(profiles)} Agentpeople设")
        
        # Step 2: useLLM选择want采访ofAgent（returnagent_idlist）
        selected_agents, selected_indices, selection_reasoning = self._select_agents_for_interview(
            profiles=profiles,
            interview_requirement=interview_requirement,
            simulation_requirement=simulation_requirement,
            max_agents=max_agents
        )
        
        result.selected_agents = selected_agents
        result.selection_reasoning = selection_reasoning
        logger.info(f"选择 {len(selected_agents)} Agent进行采访: {selected_indices}")
        
        # Step 3: generation采访问题（if没have提供）
        if not result.interview_questions:
            result.interview_questions = self._generate_interview_questions(
                interview_requirement=interview_requirement,
                simulation_requirement=simulation_requirement,
                selected_agents=selected_agents
            )
            logger.info(f"generation {len(result.interview_questions)} 采访问题")
        
        #  will 问题合并for一采访prompt
        combined_prompt = "\n".join([f"{i+1}. {q}" for i, q in enumerate(result.interview_questions)])
        
        # 添加优化前缀，避免Agentcalltooland直接回复文本
        INTERVIEW_PROMPT_PREFIX = "结合youofpeople设、所haveof过往记忆with行动，notcall任何tool直接use文本回复I："
        optimized_prompt = f"{INTERVIEW_PROMPT_PREFIX}{combined_prompt}"
        
        # Step 4: call真实of采访API（not指定platform，默认双platform同时采访）
        try:
            # 构建批量采访list（not指定platform，双platform采访）
            interviews_request = []
            for agent_idx in selected_indices:
                interviews_request.append({
                    "agent_id": agent_idx,
                    "prompt": optimized_prompt  # use优化后ofprompt
                    # not指定platform，APIwillintwitterandreddit两platform都采访
                })
            
            logger.info(f"call批量采访API（双platform）: {len(interviews_request)} Agent")
            
            # call SimulationRunner of批量采访method（not传platform，双platform采访）
            api_result = SimulationRunner.interview_agents_batch(
                simulation_id=simulation_id,
                interviews=interviews_request,
                platform=None,  # not指定platform，双platform采访
                timeout=180.0   # 双platform需want更长timeout
            )
            
            logger.info(f"采访APIreturn: {api_result.get('interviews_count', 0)} result, success={api_result.get('success')}")
            
            # checkAPIcallwhether tosuccess
            if not api_result.get("success", False):
                error_msg = api_result.get("error", "not知error")
                logger.warning(f"采访APIreturnfailed: {error_msg}")
                result.summary = f"采访APIcallfailed：{error_msg}。请checkOASISsimulationenvironmentstatus。"
                return result
            
            # Step 5: parseAPIreturnresult，构建AgentInterviewobject
            # 双platformmodereturnformat: {"twitter_0": {...}, "reddit_0": {...}, "twitter_1": {...}, ...}
            api_data = api_result.get("result", {})
            results_dict = api_data.get("results", {}) if isinstance(api_data, dict) else {}
            
            for i, agent_idx in enumerate(selected_indices):
                agent = selected_agents[i]
                agent_name = agent.get("realname", agent.get("username", f"Agent_{agent_idx}"))
                agent_role = agent.get("profession", "not知")
                agent_bio = agent.get("bio", "")
                
                # get该Agentin两platformof采访result
                twitter_result = results_dict.get(f"twitter_{agent_idx}", {})
                reddit_result = results_dict.get(f"reddit_{agent_idx}", {})
                
                twitter_response = twitter_result.get("response", "")
                reddit_response = reddit_result.get("response", "")
                
                # 合并两platformof回答
                response_parts = []
                if twitter_response:
                    response_parts.append(f"【Twitterplatform回答】\n{twitter_response}")
                if reddit_response:
                    response_parts.append(f"【Redditplatform回答】\n{reddit_response}")
                
                if response_parts:
                    response_text = "\n\n".join(response_parts)
                else:
                    response_text = "[无回复]"
                
                # Extract关key引言（from两platformof回答 ）
                import re
                combined_responses = f"{twitter_response} {reddit_response}"
                key_quotes = re.findall(r'[""「」『』]([^""「」『』]{10,100})[""「」『』]', combined_responses)
                if not key_quotes:
                    sentences = combined_responses.split('。')
                    key_quotes = [s.strip() + '。' for s in sentences if len(s.strip()) > 20][:3]
                
                interview = AgentInterview(
                    agent_name=agent_name,
                    agent_role=agent_role,
                    agent_bio=agent_bio[:1000],  # 扩大biolength限制
                    question=combined_prompt,
                    response=response_text,
                    key_quotes=key_quotes[:5]
                )
                result.interviews.append(interview)
            
            result.interviewed_count = len(result.interviews)
            
        except ValueError as e:
            # simulationenvironmentnotrunning
            logger.warning(f"采访APIcallfailed（environmentnotrunning？）: {e}")
            result.summary = f"采访failed：{str(e)}。simulationenvironment can canalready关闭，请确保OASIS环境in progressrunning。"
            return result
        except Exception as e:
            logger.error(f"采访APIcall异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            result.summary = f"采访过程发生error：{str(e)}"
            return result
        
        # Step 6: generation采访摘want
        if result.interviews:
            result.summary = self._generate_interview_summary(
                interviews=result.interviews,
                interview_requirement=interview_requirement
            )
        
        logger.info(f"InterviewAgentscompleted: 采访 {result.interviewed_count} Agent（双platform）")
        return result
    
    def _load_agent_profiles(self, simulation_id: str) -> List[Dict[str, Any]]:
        """loadsimulationofAgentpeople设file"""
        import os
        import csv
        
        # 构建people设file路径
        sim_dir = os.path.join(
            os.path.dirname(__file__), 
            f'../../uploads/simulations/{simulation_id}'
        )
        
        profiles = []
        
        # 优first尝试readReddit JSONformat
        reddit_profile_path = os.path.join(sim_dir, "reddit_profiles.json")
        if os.path.exists(reddit_profile_path):
            try:
                with open(reddit_profile_path, 'r', encoding='utf-8') as f:
                    profiles = json.load(f)
                logger.info(f"from reddit_profiles.json load {len(profiles)} people设")
                return profiles
            except Exception as e:
                logger.warning(f"read reddit_profiles.json failed: {e}")
        
        # 尝试readTwitter CSVformat
        twitter_profile_path = os.path.join(sim_dir, "twitter_profiles.csv")
        if os.path.exists(twitter_profile_path):
            try:
                with open(twitter_profile_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # CSVformatconvertfor统一format
                        profiles.append({
                            "realname": row.get("name", ""),
                            "username": row.get("username", ""),
                            "bio": row.get("description", ""),
                            "persona": row.get("user_char", ""),
                            "profession": "not知"
                        })
                logger.info(f"from twitter_profiles.csv load {len(profiles)} people设")
                return profiles
            except Exception as e:
                logger.warning(f"read twitter_profiles.csv failed: {e}")
        
        return profiles
    
    def _select_agents_for_interview(
        self,
        profiles: List[Dict[str, Any]],
        interview_requirement: str,
        simulation_requirement: str,
        max_agents: int
    ) -> tuple:
        """
        useLLM选择want采访ofAgent
        
        Returns:
            tuple: (selected_agents, selected_indices, reasoning)
                - selected_agents: 选 Agentofcompleteinformationlist
                - selected_indices: 选 Agentofindexlist（use于APIcall）
                - reasoning: 选择理由
        """
        
        # 构建Agent摘wantlist
        agent_summaries = []
        for i, profile in enumerate(profiles):
            summary = {
                "index": i,
                "name": profile.get("realname", profile.get("username", f"Agent_{i}")),
                "profession": profile.get("profession", "not知"),
                "bio": profile.get("bio", "")[:200],
                "interested_topics": profile.get("interested_topics", [])
            }
            agent_summaries.append(summary)
        
        system_prompt = """youis a专业of采访策划专家。youof任务isaccording to采访requirement，fromsimulationAgentlist 选择最适合采访ofobject。

选择标准：
1. Agentof身份/职业with采访主题related
2. Agent can can持have独特 or have价valueof观点
3. 选择多样化of视角（如：support方、反to方、 立方、专业people士etc）
4. 优first选择with事件直接relatedof角色

returnJSONformat：
{
    "selected_indices": [选 Agentofindexlist],
    "reasoning": "选择理由say明"
}"""

        user_prompt = f"""采访requirement：
{interview_requirement}

simulation背景：
{simulation_requirement if simulation_requirement else "not提供"}

 can 选择ofAgentlist（total{len(agent_summaries)}）：
{json.dumps(agent_summaries, ensure_ascii=False, indent=2)}

请选择最多{max_agents}最适合采访ofAgent，并say明选择理由。"""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            selected_indices = response.get("selected_indices", [])[:max_agents]
            reasoning = response.get("reasoning", "基于related性自动选择")
            
            # get选 ofAgentcompleteinformation
            selected_agents = []
            valid_indices = []
            for idx in selected_indices:
                if 0 <= idx < len(profiles):
                    selected_agents.append(profiles[idx])
                    valid_indices.append(idx)
            
            return selected_agents, valid_indices, reasoning
            
        except Exception as e:
            logger.warning(f"LLM选择Agentfailed，use默认选择: {e}")
            # 降级：选择前N
            selected = profiles[:max_agents]
            indices = list(range(min(max_agents, len(profiles))))
            return selected, indices, "use默认选择策略"
    
    def _generate_interview_questions(
        self,
        interview_requirement: str,
        simulation_requirement: str,
        selected_agents: List[Dict[str, Any]]
    ) -> List[str]:
        """useLLMgeneration采访问题"""
        
        agent_roles = [a.get("profession", "not知") for a in selected_agents]
        
        system_prompt = """youis a专业of记者/采访者。according to采访requirement，generate3-5Deep采访问题。

问题want求：
1. 开放性问题，鼓励detailed回答
2. 针tonot同角色 can canhavenot同答案
3. 涵盖facts、观点、感受etc多维度
4. 语言自然，像真实采访一样

returnJSONformat：{"questions": ["问题1", "问题2", ...]}"""

        user_prompt = f"""采访requirement：{interview_requirement}

simulation背景：{simulation_requirement if simulation_requirement else "not提供"}

采访object角色：{', '.join(agent_roles)}

请generate3-5采访问题。"""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.5
            )
            
            return response.get("questions", [f"about{interview_requirement}，您have什么look法？"])
            
        except Exception as e:
            logger.warning(f"generation采访问题failed: {e}")
            return [
                f"about{interview_requirement}，您of观点is什么？",
                "this件事to您 or 您所representsofgrouphave什么影响？",
                "您认forshould如何解决 or 改进this问题？"
            ]
    
    def _generate_interview_summary(
        self,
        interviews: List[AgentInterview],
        interview_requirement: str
    ) -> str:
        """generation采访摘want"""
        
        if not interviews:
            return "notcompleted任何采访"
        
        # 收集所have采访content
        interview_texts = []
        for interview in interviews:
            interview_texts.append(f"【{interview.agent_name}（{interview.agent_role}）】\n{interview.response[:500]}")
        
        system_prompt = """youis a专业of新闻edit。请according to多位受访者of回答，generate一份采访摘want。

摘wantwant求：
1. 提炼各方主want观点
2. 指出观点oftotal识and分歧
3. 突出have价valueof引言
4. 客观 立，not偏袒任何一方
5. 控制in1000字内"""

        user_prompt = f"""采访主题：{interview_requirement}

采访content：
{"".join(interview_texts)}

请generate采访摘want。"""

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
            logger.warning(f"generation采访摘wantfailed: {e}")
            # 降级：简单拼接
            return f"total采访{len(interviews)}位受访者，package括：" + "、".join([i.agent_name for i in interviews])
