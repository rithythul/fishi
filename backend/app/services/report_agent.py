"""
Report Agent Service
Use LangChain + Zep to implement ReACT mode simulation report generation

Features:
1. Generate reports according to simulation requirements and Zep graph informationrmation
2. Plan directory structure first, then generate in sections
3. Each section uses ReACT multi-round thinking with reflection mode
4. Support user dialogue, autonomously call search tools in dialogue
"""

import os
import json
import time
import re
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .zep_tools import (
    ZepToolsService, 
    SearchResult, 
    InsightForgeResult, 
    PanoramaResult,
    InterviewResult
)

logger = get_logger('mirofish.report_agent')


class ReportLogger:
    """
    Report Agent detailedlogger
    
    inreportin foldergenerate agent_log.jsonl file，recordeach stepdetailedaction。
    each lineis acompleteof JSON object，containstimestamp、actiontype、detailedcontent, etc。
    """
    
    def __init__(self, report_id: str):
        """
        initializelogger
        
        Args:
            report_id: reportID，use于确定logfile路径
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'agent_log.jsonl'
        )
        self.start_time = datetime.now()
        self._ensure_log_file()
    
    def _ensure_log_file(self):
        """确保logfile所indirectory存in"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _get_elapsed_time(self) -> float:
        """getfromstart到现inof耗时（秒）"""
        return (datetime.now() - self.start_time).total_seconds()
    
    def log(
        self, 
        action: str, 
        stage: str,
        details: Dict[str, Any],
        section_title: str = None,
        section_index: int = None
    ):
        """
        record一log
        
        Args:
            action: actiontype，such as 'start', 'tool_call', 'llm_response', 'section_complete' etc
            stage: Current阶段，such as 'planning', 'generating', 'completed'
            details: detailedcontentdictionary，not截断
            section_title: Currentsectiontitle（ can 选）
            section_index: Currentsectionindex（ can 选）
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(self._get_elapsed_time(), 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "section_title": section_title,
            "section_index": section_index,
            "details": details
        }
        
        # 追加write JSONL file
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    def log_start(self, simulation_id: str, graph_id: str, simulation_requirement: str):
        """recordreport generationstart"""
        self.log(
            action="report_start",
            stage="pending",
            details={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "simulation_requirement": simulation_requirement,
                "message": "report generation任务start"
            }
        )
    
    def log_planning_start(self):
        """recordoutlineplanstart"""
        self.log(
            action="planning_start",
            stage="planning",
            details={"message": "startplanreportoutline"}
        )
    
    def log_planning_context(self, context: Dict[str, Any]):
        """recordplan时getof上下文information"""
        self.log(
            action="planning_context",
            stage="planning",
            details={
                "message": "getsimulation上下文information",
                "context": context
            }
        )
    
    def log_planning_complete(self, outline_dict: Dict[str, Any]):
        """recordoutlineplancompleted"""
        self.log(
            action="planning_complete",
            stage="planning",
            details={
                "message": "outlineplancompleted",
                "outline": outline_dict
            }
        )
    
    def log_section_start(self, section_title: str, section_index: int):
        """recordsectiongenerationstart"""
        self.log(
            action="section_start",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={"message": f"start generating section: {section_title}"}
        )
    
    def log_react_thought(self, section_title: str, section_index: int, iteration: int, thought: str):
        """record ReACT thinking过程"""
        self.log(
            action="react_thought",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "thought": thought,
                "message": f"ReACT 第{iteration}轮thinking"
            }
        )
    
    def log_tool_call(
        self, 
        section_title: str, 
        section_index: int,
        tool_name: str, 
        parameters: Dict[str, Any],
        iteration: int
    ):
        """recordtoolcall"""
        self.log(
            action="tool_call",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": f"calltool: {tool_name}"
            }
        )
    
    def log_tool_result(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        result: str,
        iteration: int
    ):
        """recordtoolcallresult（completecontent，not截断）"""
        self.log(
            action="tool_result",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "result": result,  # completeresult，not截断
                "result_length": len(result),
                "message": f"tool {tool_name} returnresult"
            }
        )
    
    def log_llm_response(
        self,
        section_title: str,
        section_index: int,
        response: str,
        iteration: int,
        has_tool_calls: bool,
        has_final_answer: bool
    ):
        """record LLM response（completecontent，not截断）"""
        self.log(
            action="llm_response",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "response": response,  # completeresponse，not截断
                "response_length": len(response),
                "has_tool_calls": has_tool_calls,
                "has_final_answer": has_final_answer,
                "message": f"LLM response (toolcall: {has_tool_calls}, 最终答案: {has_final_answer})"
            }
        )
    
    def log_section_content(
        self,
        section_title: str,
        section_index: int,
        content: str,
        tool_calls_count: int,
        is_subsection: bool = False
    ):
        """recordsection/子sectioncontentgeneration completed（仅recordcontent，notrepresents整sectioncompleted）"""
        action = "subsection_content" if is_subsection else "section_content"
        self.log(
            action=action,
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": content,  # completecontent，not截断
                "content_length": len(content),
                "tool_calls_count": tool_calls_count,
                "is_subsection": is_subsection,
                "message": f"{'子section' if is_subsection else '主section'} {section_title} contentgeneration completed"
            }
        )
    
    def log_section_full_complete(
        self,
        section_title: str,
        section_index: int,
        full_content: str,
        subsection_count: int
    ):
        """
        recordcompletesectiongeneratecompleted（contains所have子sectionof合并content）
        
        前端应监听此logcome判断一sectionwhether to真正completed，并getcompletecontent
        """
        self.log(
            action="section_complete",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": full_content,  # completesectioncontent（含子section），not截断
                "content_length": len(full_content),
                "subsection_count": subsection_count,
                "message": f"section {section_title} completegeneration completed（含 {subsection_count} 子section）"
            }
        )
    
    def log_report_complete(self, total_sections: int, total_time_seconds: float):
        """recordreport generation completed"""
        self.log(
            action="report_complete",
            stage="completed",
            details={
                "total_sections": total_sections,
                "total_time_seconds": round(total_time_seconds, 2),
                "message": "report generation completed"
            }
        )
    
    def log_error(self, error_message: str, stage: str, section_title: str = None):
        """recorderror"""
        self.log(
            action="error",
            stage=stage,
            section_title=section_title,
            section_index=None,
            details={
                "error": error_message,
                "message": f"发生error: {error_message}"
            }
        )


class ReportConsoleLogger:
    """
    Report Agent 控制台logger
    
     will 控制台风格oflog（INFO、WARNINGetc）writereportin folderof console_log.txt file。
    this些logwith agent_log.jsonl not同，is纯文本Formatof控制台输出。
    """
    
    def __init__(self, report_id: str):
        """
        initialize控制台logger
        
        Args:
            report_id: reportID，use于确定logfile路径
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'console_log.txt'
        )
        self._ensure_log_file()
        self._file_handler = None
        self._setup_file_handler()
    
    def _ensure_log_file(self):
        """确保logfile所indirectory存in"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _setup_file_handler(self):
        """setfileprocessing器， will log同时writefile"""
        import logging
        
        # createfileprocessing器
        self._file_handler = logging.FileHandler(
            self.log_file_path,
            mode='a',
            encoding='utf-8'
        )
        self._file_handler.setLevel(logging.INFO)
        
        # usewith控制台相同of简洁Format
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self._file_handler.setFormatter(formatter)
        
        # 添加到 report_agent relatedof logger
        loggers_to_attach = [
            'mirofish.report_agent',
            'mirofish.zep_tools',
        ]
        
        for logger_name in loggers_to_attach:
            target_logger = logging.getLogger(logger_name)
            # 避免重复添加
            if self._file_handler not in target_logger.handlers:
                target_logger.addHandler(self._file_handler)
    
    def close(self):
        """关闭fileprocessing器并from logger  移除"""
        import logging
        
        if self._file_handler:
            loggers_to_detach = [
                'mirofish.report_agent',
                'mirofish.zep_tools',
            ]
            
            for logger_name in loggers_to_detach:
                target_logger = logging.getLogger(logger_name)
                if self._file_handler in target_logger.handlers:
                    target_logger.removeHandler(self._file_handler)
            
            self._file_handler.close()
            self._file_handler = None
    
    def __del__(self):
        """析构时确保关闭fileprocessing器"""
        self.close()


class ReportStatus(str, Enum):
    """reportstatus"""
    PENDING = "pending"
    PLANNING = "planning"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReportSection:
    """reportsection"""
    title: str
    content: str = ""
    subsections: List['ReportSection'] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content,
            "subsections": [s.to_dict() for s in self.subsections]
        }
    
    def to_markdown(self, level: int = 2) -> str:
        """ConvertforMarkdownFormat"""
        md = f"{'#' * level} {self.title}\n\n"
        if self.content:
            md += f"{self.content}\n\n"
        for sub in self.subsections:
            md += sub.to_markdown(level + 1)
        return md


@dataclass
class ReportOutline:
    """reportoutline"""
    title: str
    summary: str
    sections: List[ReportSection]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "sections": [s.to_dict() for s in self.sections]
        }
    
    def to_markdown(self) -> str:
        """ConvertforMarkdownFormat"""
        md = f"# {self.title}\n\n"
        md += f"> {self.summary}\n\n"
        for section in self.sections:
            md += section.to_markdown()
        return md


@dataclass
class Report:
    """completereport"""
    report_id: str
    simulation_id: str
    graph_id: str
    simulation_requirement: str
    status: ReportStatus
    outline: Optional[ReportOutline] = None
    markdown_content: str = ""
    created_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "status": self.status.value,
            "outline": self.outline.to_dict() if self.outline else None,
            "markdown_content": self.markdown_content,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error
        }


class ReportAgent:
    """
    Report Agent - simulationreportgenerateAgent
    
    useReACT（Reasoning + Acting）mode：
    1. plan阶段：分析simulationrequirement，planreportdirectorystructure
    2. generate阶段：逐sectiongeneratecontent，每section can 多timescalltoolgetinformation
    3. reflection阶段：checkcontentcomplete性and准确性
    
    【核心searchtool - 优化后】
    - insight_forge: Deepinsightsearch（最强大，自动分解问题，多维度search）
    - panorama_search: 广度search（get全貌，package括history/expiredcontent）
    - quick_search: 简单search（quicksearch）
    
    【重want】Report Agentmust优firstcalltoolgetsimulationcount据，and非use自身知识！
    """
    
    # maximumtoolcalltimescount（每section）
    MAX_TOOL_CALLS_PER_SECTION = 5
    
    # maximumreflection轮count
    MAX_REFLECTION_ROUNDS = 3
    
    # in dialogueofmaximumtoolcalltimescount
    MAX_TOOL_CALLS_PER_CHAT = 2
    
    def __init__(
        self, 
        graph_id: str,
        simulation_id: str,
        simulation_requirement: str,
        llm_client: Optional[LLMClient] = None,
        zep_tools: Optional[ZepToolsService] = None
    ):
        """
        initializeReport Agent
        
        Args:
            graph_id: 图谱ID
            simulation_id: simulationID
            simulation_requirement: simulationrequirementdescription
            llm_client: LLM客户端（ can 选）
            zep_tools: Zeptoolservice（ can 选）
        """
        self.graph_id = graph_id
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement
        
        self.llm = llm_client or LLMClient()
        self.zep_tools = zep_tools or ZepToolsService()
        
        # tool定义
        self.tools = self._define_tools()
        
        # logger（in generate_report  initialization）
        self.report_logger: Optional[ReportLogger] = None
        # 控制台logger（in generate_report  initialization）
        self.console_logger: Optional[ReportConsoleLogger] = None
        
        logger.info(f"ReportAgent initializationcompleted: graph_id={graph_id}, simulation_id={simulation_id}")
    
    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        """
        定义 can usetool
        
        【重want】this三toolis专门forfromsimulation图谱 searchinformation设计of，
        must优firstusethis些toolgetcount据，andnotisuseLLM自身of知识！
        """
        return {
            "insight_forge": {
                "name": "insight_forge",
                "description": """【Deepinsightsearch - 最强大ofsearchtool】
thisisI们最强大ofsearchfunction，专forDeep分析设计。itwill：
1. 自动 will youof问题分解for多子问题
2. from多维度searchsimulation图谱 ofinformation
3. 整合语义search、entities分析、Relationship Chain追踪ofresult
4. return最全面、最Deepofsearchcontent

【use场景】
- 需want深入分析某话题
- 需want解事件of多方面
- 需wantget支撑reportsectionof丰富素材

【returncontent】
- relatedfacts原文（ can 直接引use）
- Core Entitiesinsight
- Relationship Chain分析""",
                "parameters": {
                    "query": "youwant深入分析of问题 or 话题",
                    "report_context": "Currentreportsectionof上下文（ can 选，have助于generation更精准of子问题）"
                },
                "priority": "high"
            },
            "panorama_search": {
                "name": "panorama_search",
                "description": """【广度search - get全貌view】
thistooluse于getsimulationresultofcomplete全貌，特别适合解事件演变过程。itwill：
1. get所haverelatednodesandrelationships
2. 区分Currenthave效offactsandhistory/expiredoffacts
3. helpyou解舆情issuch as何演变of

【use场景】
- 需want解事件ofcomplete发展脉络
- 需wantto比not同阶段of舆情变化
- 需wantget全面ofentitiesandrelationshipsinformation

【returncontent】
- Currenthave效facts（simulation最新result）
- history/expiredfacts（演变record）
- 所have涉andofentities""",
                "parameters": {
                    "query": "searchQuery，use于related性sort",
                    "include_expired": "whether tocontainsexpired/historycontent（默认True）"
                },
                "priority": "medium"
            },
            "quick_search": {
                "name": "quick_search",
                "description": """【简单search - quicksearch】
轻量级ofquicksearchtool，适合简单、直接ofinformationQuery。

【use场景】
- 需wantquick查找某具体information
- 需wantvalidate某facts
- 简单ofinformationsearch

【returncontent】
- withQuery最relatedoffactslist""",
                "parameters": {
                    "query": "searchQuerystring",
                    "limit": "returnresultquantity（ can 选，默认10）"
                },
                "priority": "low"
            },
            "interview_agents": {
                "name": "interview_agents",
                "description": """【Deep采访 - 真实Agent采访（双平台）】
callOASISsimulation环境of采访API，to正inrunningofsimulationAgent进行真实采访！
thisnotisLLMsimulation，andiscall真实of采访interfacegetsimulationAgentof原始回答。
默认inTwitterandReddit两平台同时采访，get更全面of观点。

function流程：
1. 自动readpeople设file，解所havesimulationAgent
2. 智can选择withInterview Topic最relatedofAgent（such as学生、媒体、官方etc）
3. 自动generate采访问题
4. call /api/simulation/interview/batch interfacein双平台进行真实采访
5. 整合所have采访result，提供多视角分析

【use场景】
- 需wantfromnot同Role视角解事件look法（学生怎么look？媒体怎么look？官方怎么say？）
- 需want收集多方意见and立场
- 需wantgetsimulationAgentof真实回答（come自OASISsimulation环境）
- want让report更生动，contains"Interview Transcript"

【returncontent】
- 被采访Agentof身份information
- 各AgentinTwitterandReddit两平台of采访回答
- 关key引言（ can 直接引use）
- 采访摘wantand观点to比

【重want】需wantOASISsimulation环境正inrunning才canuse此function！""",
                "parameters": {
                    "interview_topic": "Interview Topic or requirementdescription（such as：'解学生to宿舍甲醛事件oflook法'）",
                    "max_agents": "最多采访ofAgentquantity（ can 选，默认5）"
                },
                "priority": "high"
            }
        }
    
    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        """
        executetoolcall
        
        Args:
            tool_name: tool名称
            parameters: toolparameters
            report_context: report上下文（use于InsightForge）
            
        Returns:
            toolexecuteresult（文本Format）
        """
        logger.info(f"executetool: {tool_name}, parameters: {parameters}")
        
        try:
            # ========== 核心retrievaltool（优化后） ==========
            
            if tool_name == "insight_forge":
                # Deepinsightretrieval - 最强大oftool
                query = parameters.get("query", "")
                ctx = parameters.get("report_context", "") or report_context
                result = self.zep_tools.insight_forge(
                    graph_id=self.graph_id,
                    query=query,
                    simulation_requirement=self.simulation_requirement,
                    report_context=ctx
                )
                return result.to_text()
            
            elif tool_name == "panorama_search":
                # 广度search - get全貌
                query = parameters.get("query", "")
                include_expired = parameters.get("include_expired", True)
                if isinstance(include_expired, str):
                    include_expired = include_expired.lower() in ['true', '1', 'yes']
                result = self.zep_tools.panorama_search(
                    graph_id=self.graph_id,
                    query=query,
                    include_expired=include_expired
                )
                return result.to_text()
            
            elif tool_name == "quick_search":
                # 简单search - quickretrieval
                query = parameters.get("query", "")
                limit = parameters.get("limit", 10)
                if isinstance(limit, str):
                    limit = int(limit)
                result = self.zep_tools.quick_search(
                    graph_id=self.graph_id,
                    query=query,
                    limit=limit
                )
                return result.to_text()
            
            elif tool_name == "interview_agents":
                # Deep采访 - call真实ofOASIS采访APIgetsimulationAgentof回答（双platform）
                interview_topic = parameters.get("interview_topic", parameters.get("query", ""))
                max_agents = parameters.get("max_agents", 20)
                if isinstance(max_agents, str):
                    max_agents = int(max_agents)
                result = self.zep_tools.interview_agents(
                    simulation_id=self.simulation_id,
                    interview_requirement=interview_topic,
                    simulation_requirement=self.simulation_requirement,
                    max_agents=max_agents
                )
                return result.to_text()
            
            # ========== 向后兼容of旧tool（内部重定向到新tool） ==========
            
            elif tool_name == "search_graph":
                # 重定向到 quick_search
                logger.info("search_graph already重定向到 quick_search")
                return self._execute_tool("quick_search", parameters, report_context)
            
            elif tool_name == "get_graph_statistics":
                result = self.zep_tools.get_graph_statistics(self.graph_id)
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_entity_summary":
                entity_name = parameters.get("entity_name", "")
                result = self.zep_tools.get_entity_summary(
                    graph_id=self.graph_id,
                    entity_name=entity_name
                )
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_simulation_context":
                # 重定向到 insight_forge，因forit更强大
                logger.info("get_simulation_context already重定向到 insight_forge")
                query = parameters.get("query", self.simulation_requirement)
                return self._execute_tool("insight_forge", {"query": query}, report_context)
            
            elif tool_name == "get_entities_by_type":
                entity_type = parameters.get("entity_type", "")
                nodes = self.zep_tools.get_entities_by_type(
                    graph_id=self.graph_id,
                    entity_type=entity_type
                )
                result = [n.to_dict() for n in nodes]
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            else:
                return f"not知tool: {tool_name}。请use以下tool之一: insight_forge, panorama_search, quick_search"
                
        except Exception as e:
            logger.error(f"toolexecutefailed: {tool_name}, error: {str(e)}")
            return f"toolexecutefailed: {str(e)}"
    
    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """
        fromLLMresponse parsetoolcall
        
        supportofFormat：
        <tool_call>
        {"name": "tool_name", "parameters": {"param1": "value1"}}
        </tool_call>
        
        or：
        [TOOL_CALL] tool_name(param1="value1", param2="value2")
        """
        tool_calls = []
        
        # Format1: XML风格
        xml_pattern = r'<tool_call>\s*(\{.*?\})\s*</tool_call>'
        for match in re.finditer(xml_pattern, response, re.DOTALL):
            try:
                call_data = json.loads(match.group(1))
                tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass
        
        # Format2: functioncall风格
        func_pattern = r'\[TOOL_CALL\]\s*(\w+)\s*\((.*?)\)'
        for match in re.finditer(func_pattern, response, re.DOTALL):
            tool_name = match.group(1)
            params_str = match.group(2)
            
            # parseparameters
            params = {}
            for param_match in re.finditer(r'(\w+)\s*=\s*["\']([^"\']*)["\']', params_str):
                params[param_match.group(1)] = param_match.group(2)
            
            tool_calls.append({
                "name": tool_name,
                "parameters": params
            })
        
        return tool_calls
    
    def _get_tools_description(self) -> str:
        """generationtooldescription文本"""
        desc_parts = [" can usetool："]
        for name, tool in self.tools.items():
            params_desc = ", ".join([f"{k}: {v}" for k, v in tool["parameters"].items()])
            desc_parts.append(f"- {name}: {tool['description']}")
            if params_desc:
                desc_parts.append(f"  parameters: {params_desc}")
        return "\n".join(desc_parts)
    
    def plan_outline(
        self, 
        progress_callback: Optional[Callable] = None
    ) -> ReportOutline:
        """
        planreportoutline
        
        useLLM分析simulationrequirement，planreportofdirectorystructure
        
        Args:
            progress_callback: 进度回调function
            
        Returns:
            ReportOutline: reportoutline
        """
        logger.info("startplanreportoutline...")
        
        if progress_callback:
            progress_callback("planning", 0, "in progress分析simulationrequirement...")
        
        # 首firstgetsimulation上下文
        context = self.zep_tools.get_simulation_context(
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement
        )
        
        if progress_callback:
            progress_callback("planning", 30, "in progressgenerationreportoutline...")
        
        # 构建planprompt
        system_prompt = """youis a「 not come预测report」of撰写专家，拥havetosimulation世界of「上帝视角」——youcaninsightsimulation 每一位Agentof行for、言论and互动。

【核心理念】
I们构建一simulation世界，并向其 注入特定of「simulationrequirement」作forvariable。simulation世界of演化result，thenisto not come can can发生情况of预测。you正in观察ofnotis"实验count据"，andis"notcomeof预演"。

【youof任务】
撰写一份「 not come预测report」，回答：
1. inI们setof件下， not come发生什么？
2. 各classAgent（people群）issuch as何反应and行动？
3. thissimulation揭示哪些value得关注of not come趋势and风险？

【report定位】
- ✅ thisis a份基于simulationof not come预测report，揭示"ifthis样，notcomewill怎样"
- ✅ 聚焦于预测result：事件走向、group反应、涌现现象、潜in风险
- ✅ simulation世界 ofAgent言行thenisto not comepeople群行forof预测
- ❌ notisto现实世界现状of分析
- ❌ notis泛泛and谈of舆情综述

【sectionquantity限制】
- 最少2主section，最多5主section
- 每sectioncanhave0-2子section
- contentwant精炼，聚焦于核心预测发现
- sectionstructure由youaccording to预测resultautonomous设计

请输出JSONFormatofreportoutline，Formatsuch as下：
{
    "title": "reporttitle",
    "summary": "report摘want（一句话概括核心预测发现）",
    "sections": [
        {
            "title": "sectiontitle",
            "description": "sectioncontentdescription",
            "subsections": [
                {"title": "子sectiontitle", "description": "子sectiondescription"}
            ]
        }
    ]
}

Note:sectionsarray最少2，最多5元素！"""

        user_prompt = f"""【Prediction Scenarioset】
I们向simulation世界注入ofvariable（simulationrequirement）：{self.simulation_requirement}

【simulation世界规模】
- 参withsimulationofentitiesquantity: {context.get('graph_statistics', {}).get('total_nodes', 0)}
- entities间产生ofrelationshipsquantity: {context.get('graph_statistics', {}).get('total_edges', 0)}
- entitiestype分布: {list(context.get('graph_statistics', {}).get('entity_types', {}).keys())}
- 活跃Agentquantity: {context.get('total_entities', 0)}

【simulation预测到of部分 not comefacts样本】
{json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2)}

请以「上帝视角」审视this not come预演：
1. inI们setof件下， not come呈现出什么样ofstatus？
2. 各classpeople群（Agent）issuch as何反应and行动of？
3. thissimulation揭示哪些value得关注of not come趋势？

according to预测result，设计最合适ofreportsectionstructure。

【再timesreminder】reportsectionquantity：最少2，最多5，contentwant精炼聚焦于核心预测发现。"""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            if progress_callback:
                progress_callback("planning", 80, "in progressparseoutlinestructure...")
            
            # parseoutline
            sections = []
            for section_data in response.get("sections", []):
                subsections = []
                for sub_data in section_data.get("subsections", []):
                    subsections.append(ReportSection(
                        title=sub_data.get("title", ""),
                        content=""
                    ))
                
                sections.append(ReportSection(
                    title=section_data.get("title", ""),
                    content="",
                    subsections=subsections
                ))
            
            outline = ReportOutline(
                title=response.get("title", "simulation分析report"),
                summary=response.get("summary", ""),
                sections=sections
            )
            
            if progress_callback:
                progress_callback("planning", 100, "outlineplancompleted")
            
            logger.info(f"outlineplancompleted: {len(sections)} section")
            return outline
            
        except Exception as e:
            logger.error(f"outlineplanfailed: {str(e)}")
            # return默认outline（3section，作forfallback）
            return ReportOutline(
                title="notcome预测report",
                summary="基于simulation预测ofnotcome趋势with风险分析",
                sections=[
                    ReportSection(title="Prediction ScenariowithCore Findings"),
                    ReportSection(title="people群行for预测分析"),
                    ReportSection(title="趋势展望with风险hint")
                ]
            )
    
    def _generate_section_react(
        self, 
        section: ReportSection,
        outline: ReportOutline,
        previous_sections: List[str],
        progress_callback: Optional[Callable] = None,
        section_index: int = 0
    ) -> str:
        """
        useReACTmodegenerate单sectioncontent
        
        ReACT循环：
        1. Thought（thinking）- 分析需want什么information
        2. Action（行动）- calltoolgetinformation
        3. Observation（观察）- 分析toolreturnresult
        4. 重复直到information足够 or reachedmaximumtimescount
        5. Final Answer（最终回答）- generatesectioncontent
        
        Args:
            section: wantgenerateofsection
            outline: completeoutline
            previous_sections: 之前sectionofcontent（use于保持连贯性）
            progress_callback: 进度回调
            section_index: sectionindex（use于logrecord）
            
        Returns:
            sectioncontent（MarkdownFormat）
        """
        logger.info(f"ReACTgenerating section: {section.title}")
        
        # recordsectionstartlog
        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)
        
        # 构建系统prompt - 优化后强调tooluseand引use原文
        # 确定Currentsectionoftitle级别
        section_level = 2  # 默认for二级title（##）
        sub_heading_level = 3  # 子titleuse三级（###）
        sub_sub_heading_level = 4  # 更小of子titleuse四级（####）
        
        system_prompt = f"""youis a「 not come预测report」of撰写专家，正in撰写reportof一section。

reporttitle: {outline.title}
report摘want: {outline.summary}
Prediction Scenario（simulationrequirement）: {self.simulation_requirement}

Currentwant撰写ofsection: {section.title}

═══════════════════════════════════════════════════════════════
【核心理念】
═══════════════════════════════════════════════════════════════

simulation世界isto not comeof预演。I们向simulation世界注入特定件（simulationrequirement），
simulation Agentof行forand互动，thenisto not comepeople群行forof预测。

youof任务is：
- 揭示inset件下， not come发生什么
- 预测各classpeople群（Agent）issuch as何反应and行动of
- 发现value得关注of not come趋势、风险and机will

❌ notwant写成to现实世界现状of分析
✅ want聚焦于"notcomewill怎样"——simulationresultthenis预测of not come

═══════════════════════════════════════════════════════════════
【最重wantof规则 - must遵守】
═══════════════════════════════════════════════════════════════

1. 【mustcalltool观察simulation世界】
   - you正in以「上帝视角」观察 not comeof预演
   - 所havecontentmustcome自simulation世界 发生of事件andAgent言行
   - 禁止useyou自己of知识come编写reportcontent
   - 每section至少call2timestool（最多4times）come观察simulationof世界，itrepresents not come

2. 【must引useAgentof原始言行】
   - Agentof发言and行foristo not comepeople群行forof预测
   - inreport use引useFormat展示this些预测，For example：
     > "某classpeople群willexpress：原文content..."
   - this些引useissimulation预测of核心证据

3. 【忠实呈现预测result】
   - reportcontentmust反映simulation世界 ofrepresents not comeofsimulationresult
   - notwant添加simulation not存inofinformation
   - if某方面informationnot足，such as实say明

═══════════════════════════════════════════════════════════════
【⚠️ Format规范 - 极其重want！】
═══════════════════════════════════════════════════════════════

【一section = minimumcontent单位】
- 每sectionisreportofminimum分blocks单位
- ❌ 禁止insection内use任何 Markdown title（#、##、###、#### etc）
- ❌ 禁止incontent开头添加section主title
- ✅ sectiontitle由系统自动添加，you只需撰写纯正文content
- ✅ use**粗体**、段落分隔、引use、listcome组织content，butnotwantusetitle

【正确example】
```
本section分析事件of舆论传播态势。throughtosimulationcount据of深入分析，I们发现...

**首发引爆阶段**

微博作for舆情of第一现场，承担information首发of核心Features:

> "微博贡献68%of首发声量..."

**情绪放大阶段**

抖音平台进一步放大事件影响力：

- 视觉冲击力强
- 情绪total鸣度高
```

【errorexample】
```
## execute摘want          ← error！notwant添加任何title
### 一、首发阶段     ← error！notwantuse###分小节
#### 1.1 detailed分析   ← error！notwantuse####细分

本section分析...
```

═══════════════════════════════════════════════════════════════
【 can usesearchtool】（每sectioncall2-4times）
═══════════════════════════════════════════════════════════════

{self._get_tools_description()}

【tooluse建议】
- insight_forge: use于Deep分析，will自动分解问题并多维度search
- panorama_search: use于解全貌and演变过程
- quick_search: use于quickvalidate某具体information
- interview_agents: use于采访simulationAgent，getnot同Roleof真实观点andlook法

═══════════════════════════════════════════════════════════════
【ReACT工作流程】
═══════════════════════════════════════════════════════════════

1. Thought: [分析需want什么information，plansearch策略]
2. Action: [calltoolgetinformation]
   <tool_call>
   {{"name": "tool名称", "parameters": {{"parameters名": "parametersvalue"}}}}
   </tool_call>
3. Observation: [分析toolreturnofresult]
4. 重复步骤1-3，直到收集到足够information（最多5轮）
5. Final Answer: [基于searchresult撰写sectioncontent]

═══════════════════════════════════════════════════════════════
【sectioncontentwant求】
═══════════════════════════════════════════════════════════════

1. contentmust基于toolsearch到ofsimulationcount据
2. 大量引use原文come展示simulation效果
3. useMarkdownFormat（but禁止usetitle）：
   - use **粗体文字** 标记重点（代替子title）
   - uselist（- or 1.2.3.）组织want点
   - use空行分隔not同段落
   - ❌ 禁止use #、##、###、#### etc任何title语法
4. 【引useFormat规范 - must单独成段】
   引usemust独立成段，前后各have一空行，notcan混in段落 ：
   
   ✅ 正确Format：
   ```
   校方of回应被认for缺乏实质content。
   
   > "校方of应tomodein瞬息万变of社交媒体environment 显得僵化and迟缓。"
   
   this a评价反映公众of普遍not满。
   ```
   
   ❌ errorFormat：
   ```
   校方of回应被认for缺乏实质content。> "校方of应tomode..." this a评价反映...
   ```
5. 保持with其hesectionof逻辑连贯性
6. 【避免重复】仔细阅读下方 already completedofsectioncontent，notwant重复description相同ofinformation
7. 【再times强调】notwant添加任何title！use**粗体**代替小节title"""

        # 构建userprompt - 每alreadycompletedsection各传入maximum4000字
        if previous_sections:
            previous_parts = []
            for sec in previous_sections:
                # 每section最多4000字
                truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
                previous_parts.append(truncated)
            previous_content = "\n\n---\n\n".join(previous_parts)
        else:
            previous_content = "（thisis第一section）"
        
        user_prompt = f""" already completedofsectioncontent（请仔细阅读，避免重复）：
{previous_content}

═══════════════════════════════════════════════════════════════
【Current任务】撰写section: {section.title}
═══════════════════════════════════════════════════════════════

【重wantreminder】
1. 仔细阅读上方 already completedofsection，避免重复相同ofcontent！
2. start前mustfirstcalltoolgetsimulationcount据
3. 推荐firstuse insight_forge 进行Deepsearch
4. reportcontentmustcome自searchresult，notwantuse自己of知识

【⚠️ Formatwarning - must遵守】
- ❌ notwant写任何title（#、##、###、####都not行）
- ❌ notwant写"{section.title}"作for开头
- ✅ sectiontitle由系统自动添加
- ✅ 直接写正文，use**粗体**代替小节title

请start：
1. 首firstthinking（Thought）thissection需want什么information
2. thencalltool（Action）getsimulationcount据
3. 收集足够information后输出 Final Answer（纯正文，无任何title）"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # ReACT循环
        tool_calls_count = 0
        max_iterations = 5  # maximum迭代轮count
        min_tool_calls = 2  # 最少toolcalltimescount
        
        # report上下文，use于InsightForgeof子问题generation
        report_context = f"sectiontitle: {section.title}\nsimulationrequirement: {self.simulation_requirement}"
        
        for iteration in range(max_iterations):
            if progress_callback:
                progress_callback(
                    "generating", 
                    int((iteration / max_iterations) * 100),
                    f"Deepretrievalwith撰写  ({tool_calls_count}/{self.MAX_TOOL_CALLS_PER_SECTION})"
                )
            
            # callLLM
            response = self.llm.chat(
                messages=messages,
                temperature=0.5,
                max_tokens=4096
            )
            
            logger.debug(f"LLMresponse: {response[:200]}...")
            
            # checkwhether tohavetoolcalland最终答案
            has_tool_calls = bool(self._parse_tool_calls(response))
            has_final_answer = "Final Answer:" in response
            
            # record LLM responselog
            if self.report_logger:
                self.report_logger.log_llm_response(
                    section_title=section.title,
                    section_index=section_index,
                    response=response,
                    iteration=iteration + 1,
                    has_tool_calls=has_tool_calls,
                    has_final_answer=has_final_answer
                )
            
            # checkwhether tohave最终答案
            if has_final_answer:
                # iftoolcalltimescountnot足，reminder需want更多retrieval
                if tool_calls_count < min_tool_calls:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user", 
                        "content": f"""【Note】you只call{tool_calls_count}timestool，information can cannot够充分。

请再call1-2timestoolcomeget更多simulationcount据，then再输出 Final Answer。
建议：
- use insight_forge Deepsearch更多细节
- use panorama_search 解事件全貌

记住：reportcontentmustcome自simulationresult，andnotisyouof知识！"""
                    })
                    continue
                
                # Extract最终答案
                final_answer = response.split("Final Answer:")[-1].strip()
                logger.info(f"section {section.title} generation completed（toolcall: {tool_calls_count}times）")
                
                # recordsectioncontentgeneration completedlog（Note：this只iscontentcompleted，notrepresents整sectioncompleted）
                # ifis子section，section_index >= 100
                is_subsection = section_index >= 100
                if self.report_logger:
                    self.report_logger.log_section_content(
                        section_title=section.title,
                        section_index=section_index,
                        content=final_answer,
                        tool_calls_count=tool_calls_count,
                        is_subsection=is_subsection
                    )
                
                return final_answer
            
            # parsetoolcall
            tool_calls = self._parse_tool_calls(response)
            
            if not tool_calls:
                # 没havetoolcallalso没have最终答案
                messages.append({"role": "assistant", "content": response})
                
                if tool_calls_count < min_tool_calls:
                    # 还没have足够oftoolcall，强烈hint需wantcalltool
                    messages.append({
                        "role": "user", 
                        "content": f"""【重want】you还没havecall足够oftoolcomegetsimulationcount据！

Current只call {tool_calls_count} timestool，至少需want {min_tool_calls} times。

请立即calltoolgetinformation：
<tool_call>
{{"name": "insight_forge", "parameters": {{"query": "{section.title}relatedofsimulationresultand分析"}}}}
</tool_call>

【记住】reportcontentmust100%come自simulationresult，notcanuseyou自己of知识！"""
                    })
                else:
                    # alreadyhave足够call，cangeneration最终答案
                    messages.append({
                        "role": "user", 
                        "content": "youalready经get足够ofsimulationcount据。请基于retrieval到ofinformation，输出 Final Answer: 并撰写sectioncontent。\n\n【重want】contentmust大量引usesearch到of原文，use > Format引use。"
                    })
                continue
            
            # executetoolcall
            tool_results = []
            for call in tool_calls:
                if tool_calls_count >= self.MAX_TOOL_CALLS_PER_SECTION:
                    break
                
                # recordtoolcalllog
                if self.report_logger:
                    self.report_logger.log_tool_call(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        parameters=call.get("parameters", {}),
                        iteration=iteration + 1
                    )
                
                result = self._execute_tool(
                    call["name"], 
                    call.get("parameters", {}),
                    report_context=report_context
                )
                
                # recordtoolresultlog
                if self.report_logger:
                    self.report_logger.log_tool_result(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        result=result,
                        iteration=iteration + 1
                    )
                
                tool_results.append(f"═══ tool {call['name']} return ═══\n{result}")
                tool_calls_count += 1
            
            #  will result添加到message
            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user",
                "content": f"""Observation（searchresult）:

{"".join(tool_results)}

═══════════════════════════════════════════════════════════════
【下一步行动】
- ifinformation充分：输出 Final Answer 并撰写sectioncontent（must引use上述原文）
- if需want更多information：continuecalltoolsearch

 already calltool {tool_calls_count}/{self.MAX_TOOL_CALLS_PER_SECTION} times
═══════════════════════════════════════════════════════════════"""
            })
        
        # reachedmaximum迭代timescount，forcedgenerationcontent
        logger.warning(f"section {section.title} reachedmaximum迭代timescount，forcedgeneration")
        messages.append({
            "role": "user",
            "content": "alreadyreachedtoolcall限制，请直接输出 Final Answer: 并generating sectioncontent。"
        })
        
        response = self.llm.chat(
            messages=messages,
            temperature=0.5,
            max_tokens=4096
        )
        
        if "Final Answer:" in response:
            final_answer = response.split("Final Answer:")[-1].strip()
        else:
            final_answer = response
        
        # recordsectioncontentgeneration completedlog（Note：this只iscontentcompleted，notrepresents整sectioncompleted）
        is_subsection = section_index >= 100
        if self.report_logger:
            self.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count,
                is_subsection=is_subsection
            )
        
        return final_answer
    
    def generate_report(
        self, 
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
        report_id: Optional[str] = None
    ) -> Report:
        """
        generatecompletereport（分section实时输出）
        
        每sectiongeneratecompleted后立即saveto file夹，not需wantetc待整reportcompleted。
        filestructure：
        reports/{report_id}/
            meta.json       - report元information
            outline.json    - reportoutline
            progress.json   - generate进度
            section_01.md   - 第1section
            section_02.md   - 第2section
            ...
            full_report.md  - completereport
        
        Args:
            progress_callback: 进度回调function (stage, progress, message)
            report_id: reportID（ can 选，ifnot传则自动generate）
            
        Returns:
            Report: completereport
        """
        import uuid
        
        # if没have传入 report_id，则自动generation
        if not report_id:
            report_id = f"report_{uuid.uuid4().hex[:12]}"
        start_time = datetime.now()
        
        report = Report(
            report_id=report_id,
            simulation_id=self.simulation_id,
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement,
            status=ReportStatus.PENDING,
            created_at=datetime.now().isoformat()
        )
        
        # alreadycompletedofsectiontitlelist（use于进度追踪）
        completed_section_titles = []
        
        try:
            # initialization：createreportfile夹并save初始status
            ReportManager._ensure_report_folder(report_id)
            
            # initializationlogger（structure化log agent_log.jsonl）
            self.report_logger = ReportLogger(report_id)
            self.report_logger.log_start(
                simulation_id=self.simulation_id,
                graph_id=self.graph_id,
                simulation_requirement=self.simulation_requirement
            )
            
            # initialization控制台logger（console_log.txt）
            self.console_logger = ReportConsoleLogger(report_id)
            
            ReportManager.update_progress(
                report_id, "pending", 0, "initializationreport...",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            # 阶段1: planoutline
            report.status = ReportStatus.PLANNING
            ReportManager.update_progress(
                report_id, "planning", 5, "startplanreportoutline...",
                completed_sections=[]
            )
            
            # recordplanstartlog
            self.report_logger.log_planning_start()
            
            if progress_callback:
                progress_callback("planning", 0, "startplanreportoutline...")
            
            outline = self.plan_outline(
                progress_callback=lambda stage, prog, msg: 
                    progress_callback(stage, prog // 5, msg) if progress_callback else None
            )
            report.outline = outline
            
            # recordplancompletedlog
            self.report_logger.log_planning_complete(outline.to_dict())
            
            # saveoutlineto file
            ReportManager.save_outline(report_id, outline)
            ReportManager.update_progress(
                report_id, "planning", 15, f"outlineplancompleted, total{len(outline.sections)}section",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            logger.info(f"outline savedto file: {report_id}/outline.json")
            
            # 阶段2: 逐sectiongeneration（分sectionsave）
            report.status = ReportStatus.GENERATING
            
            total_sections = len(outline.sections)
            generated_sections = []  # savecontentuse于上下文
            
            for i, section in enumerate(outline.sections):
                section_num = i + 1
                base_progress = 20 + int((i / total_sections) * 70)
                
                # update进度
                ReportManager.update_progress(
                    report_id, "generating", base_progress,
                    f"in progressgenerating section: {section.title} ({section_num}/{total_sections})",
                    current_section=section.title,
                    completed_sections=completed_section_titles
                )
                
                if progress_callback:
                    progress_callback(
                        "generating", 
                        base_progress, 
                        f"in progressgenerating section: {section.title} ({section_num}/{total_sections})"
                    )
                
                # generation主sectioncontent
                section_content = self._generate_section_react(
                    section=section,
                    outline=outline,
                    previous_sections=generated_sections,
                    progress_callback=lambda stage, prog, msg:
                        progress_callback(
                            stage, 
                            base_progress + int(prog * 0.7 / total_sections),
                            msg
                        ) if progress_callback else None,
                    section_index=section_num
                )
                
                section.content = section_content
                generated_sections.append(f"## {section.title}\n\n{section_content}")
                
                # ifhave子section，also一并generation并合并到主section 
                subsection_contents = []
                for j, subsection in enumerate(section.subsections):
                    subsection_num = j + 1
                    
                    if progress_callback:
                        progress_callback(
                            "generating",
                            base_progress + int(((j + 1) / max(len(section.subsections), 1)) * 5),
                            f"in progressgeneration子section: {subsection.title}"
                        )
                    
                    ReportManager.update_progress(
                        report_id, "generating",
                        base_progress + int(((j + 1) / max(len(section.subsections), 1)) * 5),
                        f"in progressgeneration子section: {subsection.title}",
                        current_section=subsection.title,
                        completed_sections=completed_section_titles
                    )
                    
                    subsection_content = self._generate_section_react(
                        section=subsection,
                        outline=outline,
                        previous_sections=generated_sections,
                        progress_callback=None,
                        section_index=section_num * 100 + subsection_num  # 子sectionindex
                    )
                    subsection.content = subsection_content
                    generated_sections.append(f"### {subsection.title}\n\n{subsection_content}")
                    subsection_contents.append((subsection.title, subsection_content))
                    completed_section_titles.append(f"  └─ {subsection.title}")
                    
                    logger.info(f"子sectionalreadygeneration: {subsection.title}")
                
                # 【关key】 will 主sectionand所have子section合并save到一file
                ReportManager.save_section_with_subsections(
                    report_id, section_num, section, subsection_contents
                )
                completed_section_titles.append(section.title)
                
                # 【重want】recordcompletesectioncompletedlog，contains合并后ofcompletecontent
                # 构建completesectioncontent（主section + 所have子section）
                full_section_content = f"## {section.title}\n\n{section_content}\n\n"
                for sub_title, sub_content in subsection_contents:
                    full_section_content += f"### {sub_title}\n\n{sub_content}\n\n"
                
                if self.report_logger:
                    self.report_logger.log_section_full_complete(
                        section_title=section.title,
                        section_index=section_num,
                        full_content=full_section_content.strip(),
                        subsection_count=len(subsection_contents)
                    )
                
                logger.info(f"sectionalreadysave（contains{len(subsection_contents)}子section）: {report_id}/section_{section_num:02d}.md")
                
                # update进度
                ReportManager.update_progress(
                    report_id, "generating", 
                    base_progress + int(70 / total_sections),
                    f"section {section.title} alreadycompleted",
                    current_section=None,
                    completed_sections=completed_section_titles
                )
            
            # 阶段3: 组装completereport
            if progress_callback:
                progress_callback("generating", 95, "in progress组装completereport...")
            
            ReportManager.update_progress(
                report_id, "generating", 95, "in progress组装completereport...",
                completed_sections=completed_section_titles
            )
            
            # useReportManager组装completereport
            report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
            report.status = ReportStatus.COMPLETED
            report.completed_at = datetime.now().isoformat()
            
            # 计算Total耗时
            total_time_seconds = (datetime.now() - start_time).total_seconds()
            
            # recordreportcompletedlog
            if self.report_logger:
                self.report_logger.log_report_complete(
                    total_sections=total_sections,
                    total_time_seconds=total_time_seconds
                )
            
            # save最终report
            ReportManager.save_report(report)
            ReportManager.update_progress(
                report_id, "completed", 100, "report generation completed",
                completed_sections=completed_section_titles
            )
            
            if progress_callback:
                progress_callback("completed", 100, "report generation completed")
            
            logger.info(f"report generation completed: {report_id}")
            
            # 关闭控制台logger
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
            
        except Exception as e:
            logger.error(f"report generationfailed: {str(e)}")
            report.status = ReportStatus.FAILED
            report.error = str(e)
            
            # recorderrorlog
            if self.report_logger:
                self.report_logger.log_error(str(e), "failed")
            
            # savefailedstatus
            try:
                ReportManager.save_report(report)
                ReportManager.update_progress(
                    report_id, "failed", -1, f"report generationfailed: {str(e)}",
                    completed_sections=completed_section_titles
                )
            except Exception:
                pass  # 忽略savefailedoferror
            
            # 关闭控制台logger
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
    
    def chat(
        self, 
        message: str,
        chat_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        withReport Agentdialogue
        
        inin dialogueAgentcanautonomouscallsearchtoolcome回答问题
        
        Args:
            message: usermessage
            chat_history: dialoguehistory
            
        Returns:
            {
                "response": "Agent回复",
                "tool_calls": [calloftoollist],
                "sources": [informationcome源]
            }
        """
        logger.info(f"Report Agentdialogue: {message[:50]}...")
        
        chat_history = chat_history or []
        
        # getalreadygenerationofreportcontent
        report_content = ""
        try:
            report = ReportManager.get_report_by_simulation(self.simulation_id)
            if report and report.markdown_content:
                # 限制reportlength，避免上下文过长
                report_content = report.markdown_content[:15000]
                if len(report.markdown_content) > 15000:
                    report_content += "\n\n... [reportcontentalready截断] ..."
        except Exception as e:
            logger.warning(f"getreportcontentfailed: {e}")
        
        # 构建系统hint
        system_prompt = f"""youis a简洁高效ofsimulation预测助手。

【背景】
预测件: {self.simulation_requirement}

【 already generateof分析report】
{report_content if report_content else "（暂无report）"}

【规则】
1. 优first基于上述reportcontent回答问题
2. 直接回答问题，避免冗长ofthinking论述
3. 仅inreportcontentnot足以回答时，才calltoolsearch更多count据
4. 回答want简洁、清晰、have理

【 can usetool】（仅in需want时use，最多call1-2times）
{self._get_tools_description()}

【toolcallFormat】
<tool_call>
{{"name": "tool名称", "parameters": {{"parameters名": "parametersvalue"}}}}
</tool_call>

【回答风格】
- 简洁直接，notwant长篇大论
- use > Format引use关keycontent
- 优firstgive出结论，再解释原因"""

        # 构建message
        messages = [{"role": "system", "content": system_prompt}]
        
        # 添加historydialogue
        for h in chat_history[-10:]:  # 限制historylength
            messages.append(h)
        
        # 添加usermessage
        messages.append({
            "role": "user", 
            "content": message
        })
        
        # ReACT循环（简化版）
        tool_calls_made = []
        max_iterations = 2  # 减少迭代轮count
        
        for iteration in range(max_iterations):
            response = self.llm.chat(
                messages=messages,
                temperature=0.5
            )
            
            # parsetoolcall
            tool_calls = self._parse_tool_calls(response)
            
            if not tool_calls:
                # 没havetoolcall，直接returnresponse
                clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', response, flags=re.DOTALL)
                clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
                
                return {
                    "response": clean_response.strip(),
                    "tool_calls": tool_calls_made,
                    "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
                }
            
            # executetoolcall（限制quantity）
            tool_results = []
            for call in tool_calls[:1]:  # 每轮最多execute1timestoolcall
                if len(tool_calls_made) >= self.MAX_TOOL_CALLS_PER_CHAT:
                    break
                result = self._execute_tool(call["name"], call.get("parameters", {}))
                tool_results.append({
                    "tool": call["name"],
                    "result": result[:1500]  # 限制resultlength
                })
                tool_calls_made.append(call)
            
            #  will result添加到message
            messages.append({"role": "assistant", "content": response})
            observation = "\n".join([f"[{r['tool']}result]\n{r['result']}" for r in tool_results])
            messages.append({
                "role": "user", 
                "content": observation + "\n\n请简洁回答问题。"
            })
        
        # reachedmaximum迭代，get最终response
        final_response = self.llm.chat(
            messages=messages,
            temperature=0.5
        )
        
        # 清理response
        clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
        clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
        
        return {
            "response": clean_response.strip(),
            "tool_calls": tool_calls_made,
            "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
        }


class ReportManager:
    """
    report管理器
    
    负责reportof持久化存储andsearch
    
    filestructure（分section输出）：
    reports/
      {report_id}/
        meta.json          - report元informationandstatus
        outline.json       - reportoutline
        progress.json      - generate进度
        section_01.md      - 第1section
        section_02.md      - 第2section
        ...
        full_report.md     - completereport
    """
    
    # report存储directory
    REPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'reports')
    
    @classmethod
    def _ensure_reports_dir(cls):
        """确保report根directory存in"""
        os.makedirs(cls.REPORTS_DIR, exist_ok=True)
    
    @classmethod
    def _get_report_folder(cls, report_id: str) -> str:
        """getreportfile夹路径"""
        return os.path.join(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _ensure_report_folder(cls, report_id: str) -> str:
        """确保reportfile夹存in并return路径"""
        folder = cls._get_report_folder(report_id)
        os.makedirs(folder, exist_ok=True)
        return folder
    
    @classmethod
    def _get_report_path(cls, report_id: str) -> str:
        """getreport元informationfile路径"""
        return os.path.join(cls._get_report_folder(report_id), "meta.json")
    
    @classmethod
    def _get_report_markdown_path(cls, report_id: str) -> str:
        """getcompletereportMarkdownfile路径"""
        return os.path.join(cls._get_report_folder(report_id), "full_report.md")
    
    @classmethod
    def _get_outline_path(cls, report_id: str) -> str:
        """getoutlinefile路径"""
        return os.path.join(cls._get_report_folder(report_id), "outline.json")
    
    @classmethod
    def _get_progress_path(cls, report_id: str) -> str:
        """get进度file路径"""
        return os.path.join(cls._get_report_folder(report_id), "progress.json")
    
    @classmethod
    def _get_section_path(cls, report_id: str, section_index: int) -> str:
        """getsectionMarkdownfile路径"""
        return os.path.join(cls._get_report_folder(report_id), f"section_{section_index:02d}.md")
    
    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        """get Agent logfile路径"""
        return os.path.join(cls._get_report_folder(report_id), "agent_log.jsonl")
    
    @classmethod
    def _get_console_log_path(cls, report_id: str) -> str:
        """get控制台logfile路径"""
        return os.path.join(cls._get_report_folder(report_id), "console_log.txt")
    
    @classmethod
    def get_console_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        get控制台logcontent
        
        thisisreportgenerate过程 of控制台输出log（INFO、WARNINGetc），
        with agent_log.jsonl ofstructure化lognot同。
        
        Args:
            report_id: reportID
            from_line: from第几行startread（use于增量get，0 expressfrom头start）
            
        Returns:
            {
                "logs": [log行list],
                "total_lines": Total行count,
                "from_line": 起始行号,
                "has_more": whether to还have更多log
            }
        """
        log_path = cls._get_console_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    # 保留原始log行，go掉末尾换行符
                    logs.append(line.rstrip('\n\r'))
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # alreadyread到末尾
        }
    
    @classmethod
    def get_console_log_stream(cls, report_id: str) -> List[str]:
        """
        getcompleteof控制台log（一times性get全部）
        
        Args:
            report_id: reportID
            
        Returns:
            log行list
        """
        result = cls.get_console_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        get Agent logcontent
        
        Args:
            report_id: reportID
            from_line: from第几行startread（use于增量get，0 expressfrom头start）
            
        Returns:
            {
                "logs": [log目list],
                "total_lines": Total行count,
                "from_line": 起始行号,
                "has_more": whether to还have更多log
            }
        """
        log_path = cls._get_agent_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    try:
                        log_entry = json.loads(line.strip())
                        logs.append(log_entry)
                    except json.JSONDecodeError:
                        # 跳过parsefailedof行
                        continue
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # alreadyread到末尾
        }
    
    @classmethod
    def get_agent_log_stream(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        getcompleteof Agent log（use于一times性get全部）
        
        Args:
            report_id: reportID
            
        Returns:
            log目list
        """
        result = cls.get_agent_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        """
        savereportoutline
        
        inplan阶段completed后立即call
        """
        cls._ensure_report_folder(report_id)
        
        with open(cls._get_outline_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(outline.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"outline saved: {report_id}")
    
    @classmethod
    def save_section(
        cls, 
        report_id: str, 
        section_index: int, 
        section: ReportSection,
        is_subsection: bool = False,
        parent_index: int = None
    ) -> str:
        """
        save单section（not推荐use，建议use save_section_with_subsections）
        
        in每sectiongeneratecompleted后立即call，implement分section输出
        
        Args:
            report_id: reportID
            section_index: sectionindex（from1start）
            section: sectionobject
            is_subsection: whether tois子section
            parent_index: 父sectionindex（子section时use）
            
        Returns:
            saveoffile路径
        """
        cls._ensure_report_folder(report_id)
        
        # 确定section级别andtitleFormat
        if is_subsection and parent_index is not None:
            level = "###"
            file_suffix = f"section_{parent_index:02d}_{section_index:02d}.md"
        else:
            level = "##"
            file_suffix = f"section_{section_index:02d}.md"
        
        # 构建sectionMarkdowncontent - 清理 can can存inof重复title
        cleaned_content = cls._clean_section_content(section.content, section.title)
        md_content = f"{level} {section.title}\n\n"
        if cleaned_content:
            md_content += f"{cleaned_content}\n\n"
        
        # savefile
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"sectionalreadysave: {report_id}/{file_suffix}")
        return file_path
    
    @classmethod
    def save_section_with_subsections(
        cls,
        report_id: str,
        section_index: int,
        section: ReportSection,
        subsection_contents: List[tuple]
    ) -> str:
        """
        savesectionand其所have子section到一file
        
        Args:
            report_id: reportID
            section_index: sectionindex（from1start）
            section: 主sectionobject
            subsection_contents: 子sectionlist [(title, content), ...]
            
        Returns:
            saveoffile路径
        """
        cls._ensure_report_folder(report_id)
        
        # 构建主sectionMarkdowncontent
        cleaned_main_content = cls._clean_section_content(section.content, section.title)
        md_content = f"## {section.title}\n\n"
        if cleaned_main_content:
            md_content += f"{cleaned_main_content}\n\n"
        
        # 添加所have子sectioncontent
        for sub_title, sub_content in subsection_contents:
            cleaned_sub_content = cls._clean_section_content(sub_content, sub_title)
            md_content += f"### {sub_title}\n\n"
            if cleaned_sub_content:
                md_content += f"{cleaned_sub_content}\n\n"
        
        # savefile
        file_suffix = f"section_{section_index:02d}.md"
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"sectionalreadysave（含{len(subsection_contents)}子section）: {report_id}/{file_suffix}")
        return file_path
    
    @classmethod
    def _clean_section_content(cls, content: str, section_title: str) -> str:
        """
        清理sectioncontent
        
        1. 移除content开头withsectiontitle重复ofMarkdowntitle行
        2.  will 所have ### and以下级别oftitleconvertfor粗体文本
        
        Args:
            content: 原始content
            section_title: sectiontitle
            
        Returns:
            清理后ofcontent
        """
        import re
        
        if not content:
            return content
        
        content = content.strip()
        lines = content.split('\n')
        cleaned_lines = []
        skip_next_empty = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # checkwhether toisMarkdowntitle行
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title_text = heading_match.group(2).strip()
                
                # checkwhether toiswithsectiontitle重复oftitle（跳过前5行内of重复）
                if i < 5:
                    if title_text == section_title or title_text.replace(' ', '') == section_title.replace(' ', ''):
                        skip_next_empty = True
                        continue
                
                #  will 所have级别oftitle（#, ##, ###, ####etc）convertfor粗体
                # 因forsectiontitle由系统添加，content not应have任何title
                cleaned_lines.append(f"**{title_text}**")
                cleaned_lines.append("")  # 添加空行
                continue
            
            # if上一行is被跳过oftitle，且Current行for空，also跳过
            if skip_next_empty and stripped == '':
                skip_next_empty = False
                continue
            
            skip_next_empty = False
            cleaned_lines.append(line)
        
        # 移除开头of空行
        while cleaned_lines and cleaned_lines[0].strip() == '':
            cleaned_lines.pop(0)
        
        # 移除开头of分隔线
        while cleaned_lines and cleaned_lines[0].strip() in ['---', '***', '___']:
            cleaned_lines.pop(0)
            # 同时移除分隔线后of空行
            while cleaned_lines and cleaned_lines[0].strip() == '':
                cleaned_lines.pop(0)
        
        return '\n'.join(cleaned_lines)
    
    @classmethod
    def update_progress(
        cls, 
        report_id: str, 
        status: str, 
        progress: int, 
        message: str,
        current_section: str = None,
        completed_sections: List[str] = None
    ) -> None:
        """
        updatereportgenerate进度
        
        前端canthroughreadprogress.jsonget实时进度
        """
        cls._ensure_report_folder(report_id)
        
        progress_data = {
            "status": status,
            "progress": progress,
            "message": message,
            "current_section": current_section,
            "completed_sections": completed_sections or [],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(cls._get_progress_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def get_progress(cls, report_id: str) -> Optional[Dict[str, Any]]:
        """getreport generation进度"""
        path = cls._get_progress_path(report_id)
        
        if not os.path.exists(path):
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @classmethod
    def get_generated_sections(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        get already generateofsectionlist
        
        return所have already saveofsectionfileinformation
        """
        folder = cls._get_report_folder(report_id)
        
        if not os.path.exists(folder):
            return []
        
        sections = []
        for filename in sorted(os.listdir(folder)):
            if filename.startswith('section_') and filename.endswith('.md'):
                file_path = os.path.join(folder, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # fromfile名parsesectionindex
                parts = filename.replace('.md', '').split('_')
                section_index = int(parts[1])
                subsection_index = int(parts[2]) if len(parts) > 2 else None
                
                sections.append({
                    "filename": filename,
                    "section_index": section_index,
                    "subsection_index": subsection_index,
                    "content": content,
                    "is_subsection": subsection_index is not None
                })
        
        return sections
    
    @classmethod
    def assemble_full_report(cls, report_id: str, outline: ReportOutline) -> str:
        """
        组装completereport
        
        from already saveofsectionfile组装completereport，并进行title清理
        """
        folder = cls._get_report_folder(report_id)
        
        # 构建report头部
        md_content = f"# {outline.title}\n\n"
        md_content += f"> {outline.summary}\n\n"
        md_content += f"---\n\n"
        
        # By顺序read所havesectionfile（只read主sectionfile，notread子sectionfile）
        sections = cls.get_generated_sections(report_id)
        for section_information in sections:
            # 跳过子sectionfile（already合并到主section ）
            if section_information.get("is_subsection", False):
                continue
            md_content += section_information["content"]
        
        # 后processing：清理整reportoftitle问题
        md_content = cls._post_process_report(md_content, outline)
        
        # savecompletereport
        full_path = cls._get_report_markdown_path(report_id)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"completereportalready组装: {report_id}")
        return md_content
    
    @classmethod
    def _post_process_report(cls, content: str, outline: ReportOutline) -> str:
        """
        后processreportcontent
        
        1. 移除重复oftitle
        2. 保留report主title(#)andsectiontitle(##)，移除其he级别oftitle(###, ####etc)
        3. 清理多余of空行and分隔线
        
        Args:
            content: 原始reportcontent
            outline: reportoutline
            
        Returns:
            process后ofcontent
        """
        import re
        
        lines = content.split('\n')
        processed_lines = []
        prev_was_heading = False
        
        # 收集outline of所havesectiontitle
        section_titles = set()
        for section in outline.sections:
            section_titles.add(section.title)
            for sub in section.subsections:
                section_titles.add(sub.title)
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # checkwhether toistitle行
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                
                # checkwhether tois重复title（in连续5行内出现相同contentoftitle）
                is_duplicate = False
                for j in range(max(0, len(processed_lines) - 5), len(processed_lines)):
                    prev_line = processed_lines[j].strip()
                    prev_match = re.match(r'^(#{1,6})\s+(.+)$', prev_line)
                    if prev_match:
                        prev_title = prev_match.group(2).strip()
                        if prev_title == title:
                            is_duplicate = True
                            break
                
                if is_duplicate:
                    # 跳过重复titleand其后of空行
                    i += 1
                    while i < len(lines) and lines[i].strip() == '':
                        i += 1
                    continue
                
                # title层级processing：
                # - # (level=1) 只保留report主title
                # - ## (level=2) 保留sectiontitle
                # - ### and以下 (level>=3) convertfor粗体文本
                
                if level == 1:
                    if title == outline.title:
                        # 保留report主title
                        processed_lines.append(line)
                        prev_was_heading = True
                    elif title in section_titles:
                        # sectiontitleerroruse#，修正for##
                        processed_lines.append(f"## {title}")
                        prev_was_heading = True
                    else:
                        # 其he一级title转for粗体
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                elif level == 2:
                    if title in section_titles or title == outline.title:
                        # 保留sectiontitle
                        processed_lines.append(line)
                        prev_was_heading = True
                    else:
                        # 非sectionof二级title转for粗体
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                else:
                    # ### and以下级别oftitleconvertfor粗体文本
                    processed_lines.append(f"**{title}**")
                    processed_lines.append("")
                    prev_was_heading = False
                
                i += 1
                continue
            
            elif stripped == '---' and prev_was_heading:
                # 跳过title后紧跟of分隔线
                i += 1
                continue
            
            elif stripped == '' and prev_was_heading:
                # title后只保留一空行
                if processed_lines and processed_lines[-1].strip() != '':
                    processed_lines.append(line)
                prev_was_heading = False
            
            else:
                processed_lines.append(line)
                prev_was_heading = False
            
            i += 1
        
        # 清理连续of多空行（保留最多2）
        result_lines = []
        empty_count = 0
        for line in processed_lines:
            if line.strip() == '':
                empty_count += 1
                if empty_count <= 2:
                    result_lines.append(line)
            else:
                empty_count = 0
                result_lines.append(line)
        
        return '\n'.join(result_lines)
    
    @classmethod
    def save_report(cls, report: Report) -> None:
        """savereport元informationandcompletereport"""
        cls._ensure_report_folder(report.report_id)
        
        # save元informationJSON
        with open(cls._get_report_path(report.report_id), 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        
        # saveoutline
        if report.outline:
            cls.save_outline(report.report_id, report.outline)
        
        # savecompleteMarkdownreport
        if report.markdown_content:
            with open(cls._get_report_markdown_path(report.report_id), 'w', encoding='utf-8') as f:
                f.write(report.markdown_content)
        
        logger.info(f"report saved: {report.report_id}")
    
    @classmethod
    def get_report(cls, report_id: str) -> Optional[Report]:
        """getreport"""
        path = cls._get_report_path(report_id)
        
        if not os.path.exists(path):
            # 兼容旧Format：check直接存储inreportsdirectory下offile
            old_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
            if os.path.exists(old_path):
                path = old_path
            else:
                return None
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 重建Reportobject
        outline = None
        if data.get('outline'):
            outline_data = data['outline']
            sections = []
            for s in outline_data.get('sections', []):
                subsections = [
                    ReportSection(title=sub['title'], content=sub.get('content', ''))
                    for sub in s.get('subsections', [])
                ]
                sections.append(ReportSection(
                    title=s['title'],
                    content=s.get('content', ''),
                    subsections=subsections
                ))
            outline = ReportOutline(
                title=outline_data['title'],
                summary=outline_data['summary'],
                sections=sections
            )
        
        # ifmarkdown_contentfor空，尝试fromfull_report.mdread
        markdown_content = data.get('markdown_content', '')
        if not markdown_content:
            full_report_path = cls._get_report_markdown_path(report_id)
            if os.path.exists(full_report_path):
                with open(full_report_path, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
        
        return Report(
            report_id=data['report_id'],
            simulation_id=data['simulation_id'],
            graph_id=data['graph_id'],
            simulation_requirement=data['simulation_requirement'],
            status=ReportStatus(data['status']),
            outline=outline,
            markdown_content=markdown_content,
            created_at=data.get('created_at', ''),
            completed_at=data.get('completed_at', ''),
            error=data.get('error')
        )
    
    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Optional[Report]:
        """according tosimulationIDgetreport"""
        cls._ensure_reports_dir()
        
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # 新Format：file夹
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report and report.simulation_id == simulation_id:
                    return report
            # 兼容旧Format：JSONfile
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report and report.simulation_id == simulation_id:
                    return report
        
        return None
    
    @classmethod
    def list_reports(cls, simulation_id: Optional[str] = None, limit: int = 50) -> List[Report]:
        """列出report"""
        cls._ensure_reports_dir()
        
        reports = []
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # 新Format：file夹
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
            # 兼容旧Format：JSONfile
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
        
        # Bycreatetime倒序
        reports.sort(key=lambda r: r.created_at, reverse=True)
        
        return reports[:limit]
    
    @classmethod
    def delete_report(cls, report_id: str) -> bool:
        """deletereport（整file夹）"""
        import shutil
        
        folder_path = cls._get_report_folder(report_id)
        
        # 新Format：delete整file夹
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logger.info(f"reportfile夹alreadydelete: {report_id}")
            return True
        
        # 兼容旧Format：delete单独offile
        deleted = False
        old_json_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
        old_md_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.md")
        
        if os.path.exists(old_json_path):
            os.remove(old_json_path)
            deleted = True
        if os.path.exists(old_md_path):
            os.remove(old_md_path)
            deleted = True
        
        return deleted
