"""
Report Agent Service
Use Neo4j + LLM to implement ReACT mode simulation report generation

Features:
1. Generate reports according to simulation requirements and Neo4j graph information
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
from .neo4j_tools import (
    Neo4jToolsService, 
    SearchResult, 
    InsightForgeResult, 
    PanoramaResult,
    InterviewResult
)

logger = get_logger('fishi.report_agent')


class ReportLogger:
    """
    Report Agent detailed logger
    
    Generates agent_log.jsonl file in report folder, recording detailed actions of each step.
    Each line is a complete JSON object, containing timestamp, action type, detailed content, etc.
    """
    
    def __init__(self, report_id: str):
        """
        Initialize logger
        
        Args:
            report_id: Report ID, used to determine log file path
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'agent_log.jsonl'
        )
        self.start_time = datetime.now()
        self._ensure_log_file()
    
    def _ensure_log_file(self):
        """Ensure the directory for log file exists"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _get_elapsed_time(self) -> float:
        """Get elapsed time since start (seconds)"""
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
        Record a log entry
        
        Args:
            action: Action type, e.g., 'start', 'tool_call', 'llm_response', 'section_complete'
            stage: Current stage, e.g., 'planning', 'generating', 'completed'
            details: Detailed content dictionary, not truncated
            section_title: Current section title (optional)
            section_index: Current section index (optional)
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
        
        # Append to JSONL file
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    def log_start(self, simulation_id: str, graph_id: str, simulation_requirement: str):
        """Record report generation start"""
        self.log(
            action="report_start",
            stage="pending",
            details={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "simulation_requirement": simulation_requirement,
                "message": "Report generation task started"
            }
        )
    
    def log_planning_start(self):
        """Record outline planning start"""
        self.log(
            action="planning_start",
            stage="planning",
            details={"message": "Start planning report outline"}
        )
    
    def log_planning_context(self, context: Dict[str, Any]):
        """Record context information obtained during planning"""
        self.log(
            action="planning_context",
            stage="planning",
            details={
                "message": "Got simulation context information",
                "context": context
            }
        )
    
    def log_planning_complete(self, outline_dict: Dict[str, Any]):
        """Record outline planning completion"""
        self.log(
            action="planning_complete",
            stage="planning",
            details={
                "message": "Outline planning completed",
                "outline": outline_dict
            }
        )
    
    def log_section_start(self, section_title: str, section_index: int):
        """Record section generation start"""
        self.log(
            action="section_start",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={"message": f"Start generating section: {section_title}"}
        )
    
    def log_react_thought(self, section_title: str, section_index: int, iteration: int, thought: str):
        """Record ReACT thinking process"""
        self.log(
            action="react_thought",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "thought": thought,
                "message": f"ReACT Round {iteration} thinking"
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
        """Record tool call"""
        self.log(
            action="tool_call",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": f"Call tool: {tool_name}"
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
        """Record tool call result (full content)"""
        self.log(
            action="tool_result",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "result": result,
                "result_length": len(result),
                "message": f"Tool {tool_name} returned result"
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
        """Record LLM response (full content)"""
        self.log(
            action="llm_response",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "response": response,
                "response_length": len(response),
                "has_tool_calls": has_tool_calls,
                "has_final_answer": has_final_answer,
                "message": f"LLM response (tool call: {has_tool_calls}, final answer: {has_final_answer})"
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
        """Record section/subsection content generation completion"""
        action = "subsection_content" if is_subsection else "section_content"
        self.log(
            action=action,
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": content,
                "content_length": len(content),
                "tool_calls_count": tool_calls_count,
                "is_subsection": is_subsection,
                "message": f"{'Subsection' if is_subsection else 'Main section'} {section_title} content generation completed"
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
        Record complete section generation completion (including all subsections)
        """
        self.log(
            action="section_complete",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": full_content,
                "content_length": len(full_content),
                "subsection_count": subsection_count,
                "message": f"Section {section_title} complete generation finished (including {subsection_count} subsections)"
            }
        )
    
    def log_report_complete(self, total_sections: int, total_time_seconds: float):
        """Record report generation completion"""
        self.log(
            action="report_complete",
            stage="completed",
            details={
                "total_sections": total_sections,
                "total_time_seconds": round(total_time_seconds, 2),
                "message": "Report generation completed"
            }
        )
    
    def log_error(self, error_message: str, stage: str, section_title: str = None):
        """Record error"""
        self.log(
            action="error",
            stage=stage,
            section_title=section_title,
            section_index=None,
            details={
                "error": error_message,
                "message": f"Error occurred: {error_message}"
            }
        )


class ReportConsoleLogger:
    """
    Report Agent Console Logger
    
    Writes console-style logs (INFO, WARNING, etc.) to console_log.txt in report folder.
    Different from agent_log.jsonl, this is plain text format.
    """
    
    def __init__(self, report_id: str):
        """
        Initialize console logger
        
        Args:
            report_id: Report ID
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'console_log.txt'
        )
        self._ensure_log_file()
        self._file_handler = None
        self._setup_file_handler()
    
    def _ensure_log_file(self):
        """Ensure log file directory exists"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _setup_file_handler(self):
        """Setup file handler to write logs to file"""
        import logging
        
        # Create file handler
        self._file_handler = logging.FileHandler(
            self.log_file_path,
            mode='a',
            encoding='utf-8'
        )
        self._file_handler.setLevel(logging.INFO)
        
        # Use simple format similar to console
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self._file_handler.setFormatter(formatter)
        
        # Attach to report_agent related loggers
        loggers_to_attach = [
            'fishi.report_agent',
            'fishi.neo4j_tools',
        ]
        
        for logger_name in loggers_to_attach:
            target_logger = logging.getLogger(logger_name)
            # Avoid duplicate attachment
            if self._file_handler not in target_logger.handlers:
                target_logger.addHandler(self._file_handler)
    
    def close(self):
        """Close file handler and remove from logger"""
        import logging
        
        if self._file_handler:
            loggers_to_detach = [
                'fishi.report_agent',
                'fishi.neo4j_tools',
            ]
            
            for logger_name in loggers_to_detach:
                target_logger = logging.getLogger(logger_name)
                if self._file_handler in target_logger.handlers:
                    target_logger.removeHandler(self._file_handler)
            
            self._file_handler.close()
            self._file_handler = None
    
    def __del__(self):
        """Ensure file handler is closed on destruction"""
        self.close()


class ReportStatus(str, Enum):
    """Report status"""
    PENDING = "pending"
    PLANNING = "planning"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReportSection:
    """Report Section"""
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
        """Convert to Markdown format"""
        md = f"{'#' * level} {self.title}\n\n"
        if self.content:
            md += f"{self.content}\n\n"
        for sub in self.subsections:
            md += sub.to_markdown(level + 1)
        return md


@dataclass
class ReportOutline:
    """Report Outline"""
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
        """Convert to Markdown format"""
        md = f"# {self.title}\n\n"
        md += f"> {self.summary}\n\n"
        for section in self.sections:
            md += section.to_markdown()
        return md


@dataclass
class Report:
    """Complete Report"""
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
    Report Agent - Simulation Report Generation Agent
    
    Uses ReACT (Reasoning + Acting) mode:
    1. Planning: Analyze requirements, plan report directory structure
    2. Generation: Generate content section by section, each section calls tools multiple times
    3. Reflection: Check content completeness and accuracy
    
    [Core Search Tools]
    - insight_forge: Deep insight search (Automatic querying, multi-dimensional search)
    - panorama_search: Panorama search (Get full picture, including history/expired content)
    - quick_search: Quick search (Simple retrieval)
    
    [Important] Report Agent must PRIORITIZE using tools to get simulation data, NOT its own knowledge!
    """
    
    MAX_TOOL_CALLS_PER_SECTION = 5
    MAX_REFLECTION_ROUNDS = 3
    MAX_TOOL_CALLS_PER_CHAT = 2
    
    def __init__(
        self, 
        graph_id: str,
        simulation_id: str,
        simulation_requirement: str,
        llm_client: Optional[LLMClient] = None,
        neo4j_tools: Optional[Neo4jToolsService] = None
    ):
        """
        Initialize Report Agent
        
        Args:
            graph_id: Graph ID
            simulation_id: Simulation ID
            simulation_requirement: Simulation requirement description
            llm_client: LLM client (optional)
            neo4j_tools: Neo4j tool service (optional)
        """
        self.graph_id = graph_id
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement
        
        self.llm = llm_client or LLMClient()
        self.neo4j_tools = neo4j_tools or Neo4jToolsService()
        
        self.tools = self._define_tools()
        
        # Loggers (initialized in generate_report)
        self.report_logger: Optional[ReportLogger] = None
        self.console_logger: Optional[ReportConsoleLogger] = None
        
        logger.info(f"ReportAgent initialization completed: graph_id={graph_id}, simulation_id={simulation_id}")
    
    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        """
        Define available tools
        """
        return {
            "insight_forge": {
                "name": "insight_forge",
                "description": """[Deep Insight Search - Most Powerful Search Tool]
Designed for deep analysis. It will:
1. Automatically decompose your question into sub-questions
2. Search simulation graph info from multiple dimensions
3. Integrate semantic search, entity analysis, and relationship chain tracking
4. Return the comprehensive search content

[Usage Scenario]
- Need deep analysis of a topic
- Need to understand multiple aspects of an event
- Need rich material for report section

[Returns]
- Related facts (Source text)
- Core Entities Insight
- Relationship Chain Analysis""",
                "parameters": {
                    "query": "Question or topic to analyze deeply",
                    "report_context": "Context of current report section (optional, helps generate precise sub-questions)"
                },
                "priority": "high"
            },
            "panorama_search": {
                "name": "panorama_search",
                "description": """[Panorama Search - Get Full Picture]
Used to get the complete picture of simulation results, especially for event evolution. It will:
1. Get all related nodes and relationships
2. Distinguish current valid facts vs history/expired facts
3. Help understand how public opinion evolved

[Usage Scenario]
- Need to understand the complete development timeline
- Need to compare changes across different stages
- Need comprehensive entity and relationship info

[Returns]
- Current valid facts
- History/expired facts
- All involved entities""",
                "parameters": {
                    "query": "Search query for relevance sorting",
                    "include_expired": "Whether to include expired/history content (default True)"
                },
                "priority": "medium"
            },
            "quick_search": {
                "name": "quick_search",
                "description": """[Quick Search - Simple Retrieval]
Lightweight quick search tool for simple information queries.

[Usage Scenario]
- Need to quickly look up specific info
- Need to validate a fact
- Simple info retrieval

[Returns]
- List of facts most relevant to query""",
                "parameters": {
                    "query": "Search query string",
                    "limit": "Max results (optional, default 10)"
                },
                "priority": "low"
            },
            "interview_agents": {
                "name": "interview_agents",
                "description": """[Deep Interview - Real Agent Interview (Dual Platform)]
Call OASIS simulation environment interview API to interview running simulation Agents!
This is NOT LLM simulation, but calling real interview interface to get raw answers.
Default interviews on both Twitter and Reddit to get comprehensive views.

Workflow:
1. Auto read persona files
2. Intelligently select Agents relevant to Topic (Student, Media, Official, etc.)
3. Auto generate interview questions
4. Call /api/simulation/interview/batch interface
5. Aggregate results

[Usage Scenario]
- Need views from specific roles (Student view? Media view?)
- Need to collect diverse opinions and stances
- Need raw answers from simulation Agents
- Want to include 'Interview Transcript' in report

[Returns]
- Interviewed Agent identity info
- Agent answers on Twitter/Reddit
- Key quotes
- Summary and contrast""",
                "parameters": {
                    "interview_topic": "Interview Topic or requirement description (e.g. 'Views on dormitory formaldehyde event')",
                    "max_agents": "Max agents to interview (optional, default 5)"
                },
                "priority": "high"
            }
        }
    
    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        """Execute tool call"""
        logger.info(f"Execute tool: {tool_name}, parameters: {parameters}")
        
        try:
            if tool_name == "insight_forge":
                query = parameters.get("query", "")
                ctx = parameters.get("report_context", "") or report_context
                result = self.neo4j_tools.insight_forge(
                    graph_id=self.graph_id,
                    query=query,
                    simulation_requirement=self.simulation_requirement,
                    report_context=ctx
                )
                return result.to_text()
            
            elif tool_name == "panorama_search":
                query = parameters.get("query", "")
                include_expired = parameters.get("include_expired", True)
                if isinstance(include_expired, str):
                    include_expired = include_expired.lower() in ['true', '1', 'yes']
                result = self.neo4j_tools.panorama_search(
                    graph_id=self.graph_id,
                    query=query,
                    include_expired=include_expired
                )
                return result.to_text()
            
            elif tool_name == "quick_search":
                query = parameters.get("query", "")
                limit = parameters.get("limit", 10)
                if isinstance(limit, str):
                    limit = int(limit)
                result = self.neo4j_tools.quick_search(
                    graph_id=self.graph_id,
                    query=query,
                    limit=limit
                )
                return result.to_text()
            
            elif tool_name == "interview_agents":
                interview_topic = parameters.get("interview_topic", parameters.get("query", ""))
                max_agents = parameters.get("max_agents", 20)
                if isinstance(max_agents, str):
                    max_agents = int(max_agents)
                result = self.neo4j_tools.interview_agents(
                    simulation_id=self.simulation_id,
                    interview_requirement=interview_topic,
                    simulation_requirement=self.simulation_requirement,
                    max_agents=max_agents
                )
                return result.to_text()
            
            # Legacy tool redirection
            elif tool_name == "search_graph":
                logger.info("search_graph redirected to quick_search")
                return self._execute_tool("quick_search", parameters, report_context)
            
            elif tool_name == "get_statistics": # Handle alias if needed
                 pass 

            # Handle other Neo4j tools directly if needed or return error
            # For simplicity, focusing on core retrieval tools
            
            elif tool_name == "get_graph_statistics":
                 result = self.neo4j_tools.get_graph_statistics(self.graph_id)
                 return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_entity_summary":
                entity_name = parameters.get("entity_name", "")
                result = self.neo4j_tools.get_entity_summary(
                    graph_id=self.graph_id,
                    entity_name=entity_name
                )
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "get_simulation_context":
                logger.info("get_simulation_context redirected to insight_forge")
                query = parameters.get("query", self.simulation_requirement)
                return self._execute_tool("insight_forge", {"query": query}, report_context)
                
            elif tool_name == "get_entities_by_type":
                entity_type = parameters.get("entity_type", "")
                nodes = self.neo4j_tools.get_entities_by_type(
                    graph_id=self.graph_id,
                    entity_type=entity_type
                )
                result = [n.to_dict() for n in nodes]
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            else:
                return f"Unknown tool: {tool_name}. Please use: insight_forge, panorama_search, quick_search, interview_agents"
                
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name}, error: {str(e)}")
            return f"Tool execution failed: {str(e)}"
    
    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """Parse tool calls from LLM response"""
        tool_calls = []
        
        # XML format
        xml_pattern = r'<tool_call>\s*(\{.*?\})\s*</tool_call>'
        for match in re.finditer(xml_pattern, response, re.DOTALL):
            try:
                call_data = json.loads(match.group(1))
                tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass
        
        # Function call format: [TOOL_CALL] name(param="val")
        func_pattern = r'\[TOOL_CALL\]\s*(\w+)\s*\((.*?)\)'
        for match in re.finditer(func_pattern, response, re.DOTALL):
            tool_name = match.group(1)
            params_str = match.group(2)
            
            params = {}
            for param_match in re.finditer(r'(\w+)\s*=\s*["\']([^"\']*)["\']', params_str):
                params[param_match.group(1)] = param_match.group(2)
            
            tool_calls.append({
                "name": tool_name,
                "parameters": params
            })
        
        return tool_calls
    
    def _get_tools_description(self) -> str:
        """Generate tool description text"""
        desc_parts = ["Available Tools:"]
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
        Plan report outline
        
        Use LLM to analyze simulation requirements and plan directory structure.
        """
        logger.info("Start planning report outline...")
        
        if progress_callback:
            progress_callback("planning", 0, "Analyzing simulation requirements...")
        
        context = self.neo4j_tools.get_simulation_context(
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement
        )
        
        if progress_callback:
            progress_callback("planning", 30, "Generating report outline...")
        
        system_prompt = """You are a "Future Prediction Report" writing expert, possessing a "God's View" of the simulation world - you can insight into every Agent's behavior, speech, and interaction.

[Core Concept]
We constructed a simulation world and injected specific "Simulation Requirements" as variables. The evolution result of the simulation world IS the prediction of what might happen in the future. You are observing "Future Rehearsal", not just experimental data.

[Your Task]
Write a "Future Prediction Report" answering:
1. Under our settings, what will happen in the future?
2. How do different groups of Agents react and act?
3. What worthy future trends and risks does this simulation reveal?

[Report Positioning]
- ✅ This is a Future Prediction Report based on simulation, revealing "If this, then that".
- ✅ Focus on prediction results: Event direction, Group reaction, Emergent phenomena, Potential risks.
- ✅ Simulation Agent speech/behavior IS the prediction of future crowd behavior.
- ❌ This is NOT an analysis of the current real world status.
- ❌ This is NOT a generic public opinion summary.

[Section Constraints]
- Min 2 main sections, Max 5 main sections.
- Each section can have 0-2 subsections.
- Content must be concise, focused on core prediction findings.
- Section structure should be autonomously designed by you based on prediction results.

Please output JSON format report outline:
{
    "title": "Report Title (English)",
    "summary": "Report Abstract (One sentence summary of core findings, in English)",
    "sections": [
        {
            "title": "Section Title (English)",
            "description": "Section Description",
            "subsections": [
                {"title": "Subsection Title (English)", "description": "Subsection Description"}
            ]
        }
    ]
}

Note: sections array min 2, max 5 items! ALL TEXT MUST BE IN ENGLISH."""

        user_prompt = f"""[Prediction Scenario Set]
Variables injected (Simulation Requirement): {self.simulation_requirement}

[Simulation World Scale]
- Entities count: {context.get('graph_statistics', {}).get('total_nodes', 0)}
- Relationships count: {context.get('graph_statistics', {}).get('total_edges', 0)}
- Entity types: {list(context.get('graph_statistics', {}).get('entity_types', {}).keys())}
- Active Agents: {context.get('total_entities', 0)}

[Predicted Partial Future Facts Sample]
{json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2)}

Please review this Future Rehearsal with "God's View":
1. What state will appear in the future under our settings?
2. How do various groups (Agents) react and act?
3. What trends does this simulation reveal?

Based on prediction results, design the most suitable report structure.
Output strictly in English."""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            if progress_callback:
                progress_callback("planning", 80, "Parsing outline structure...")
            
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
                title=response.get("title", "Simulation Analysis Report"),
                summary=response.get("summary", ""),
                sections=sections
            )
            
            if progress_callback:
                progress_callback("planning", 100, "Outline planning completed")
            
            logger.info(f"Outline planning completed: {len(sections)} sections")
            return outline
            
        except Exception as e:
            logger.error(f"Outline planning failed: {str(e)}")
            # Fallback outline
            return ReportOutline(
                title="Future Prediction Report",
                summary="Future trends and risk analysis based on simulation predictions",
                sections=[
                    ReportSection(title="Prediction Scenario and Core Findings"),
                    ReportSection(title="Group Behavior Prediction Analysis"),
                    ReportSection(title="Trend Outlook and Risk Hints")
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
        Use ReACT mode to generate single section content
        
        ReACT Loop:
        1. Thought - Analyze what info is needed
        2. Action - Call tool
        3. Observation - Analyze tool result
        4. Repeat until info sufficient or max iterations
        5. Final Answer - Generate section content
        """
        logger.info(f"ReACT generating section: {section.title}")
        
        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)
        
        system_prompt = f"""You are a "Future Prediction Report" writing expert, currently writing a section of the report.

Report Title: {outline.title}
Report Summary: {outline.summary}
Prediction Scenario (Simulation Requirement): {self.simulation_requirement}

Current Section to Write: {section.title}

═══════════════════════════════════════════════════════════════
[Core Concept]
═══════════════════════════════════════════════════════════════

Simulation world is a Rehearsal of the Future. We injected specific variables.
The behavior and interaction of Simulation Agents IS the prediction of future crowd behavior.

Your Task:
- Reveal what will happen in the future under these settings
- Predict how various groups (Agents) react and act
- Discover worthy future trends, risks and opportunities

❌ DO NOT write an analysis of current real world status
✅ Focus on "What will happen" - Simulation results ARE the prediction of future

═══════════════════════════════════════════════════════════════
[Most Important Rules - MUST OBSERVE]
═══════════════════════════════════════════════════════════════

1. [MUST Call Tool to Observe Simulation World]
   - You are observing future rehearsal with "God's View"
   - ALL content MUST come from events and Agent speech occurring in simulation world
   - FORBIDDEN to use your own knowledge to write report content that contradicts simulation
   - Call tool at least 2 times (max 4) per section to observe simulation.

2. [MUST Quote Agent's Raw Speech/Action]
   - Agent's speech and behavior is the prediction of future crowd behavior
   - Use Quote format to display these predictions, e.g.:
     > "A certain group expressed: [Raw Content]..."
   - These quotes are the Core Evidence of simulation prediction

3. [Faithfully Present Prediction Results]
   - Report content must reflect the simulation results representing the future
   - Do NOT add information that does not exist in simulation
   - If info is insufficient, state truthfully

═══════════════════════════════════════════════════════════════
[⚠️ Format Specification - EXTREMELY IMPORTANT!]
═══════════════════════════════════════════════════════════════

[One Section = Minimum Content Unit]
- Each section is the minimum chunk unit
- ❌ PROHIBITED to use any Markdown Heading (#, ##, ###, ####) inside section content
- ❌ PROHIBITED to add section title at start of content
- ✅ Section title is automatically added by system, you ONLY write the body content
- ✅ Use **Bold**, Paragraph breaks, Quotes, Lists to organize content, but NO Headings

[Correct Example]
```
This section analyzes the public opinion spread. Through deep analysis of simulation data, we found...

**Initial Eruption Stage**

Weibo acts as the first scene of public opinion...

> "Weibo contributed 68% of initial volume..."

**Emotional Amplification Stage**

TikTok further amplified the impact:

- Strong visual impact
- High emotional resonance
```

[Error Example]
```
## Executive Summary          ← ERROR! Do not add any headings
### 1. Initial Stage         ← ERROR! Do not use ###
#### 1.1 Detailed Analysis   ← ERROR! Do not use ####

This section analyzes...
```

═══════════════════════════════════════════════════════════════
[Available Search Tools] (Call 2-4 times per section)
═══════════════════════════════════════════════════════════════

{self._get_tools_description()}

[Tool Usage Advice]
- insight_forge: Use for deep analysis, automatically decomposes questions
- panorama_search: Use to understand full picture and evolution
- quick_search: Use to quickly validate specific info
- interview_agents: Use to interview simulation Agents for real views

═══════════════════════════════════════════════════════════════
[ReACT Workflow]
═══════════════════════════════════════════════════════════════

1. Thought: [Analyze what info needed, plan search strategy]
2. Action: [Call tool to get info]
   <tool_call>
   {{"name": "tool_name", "parameters": {{"param_name": "param_value"}}}}
   </tool_call>
3. Observation: [Analyze tool result]
4. Repeat 1-3 until sufficient info (max 5 rounds)
5. Final Answer: [Write section content based on search results]

═══════════════════════════════════════════════════════════════
[Section Content Requirements]
═══════════════════════════════════════════════════════════════

1. Content MUST be based on simulation data found via tools
2. Heavily quote raw text to demonstrate simulation effects
3. Use Markdown Format (BUT PROHIBITED TO USE HEADINGS):
   - Use **Bold Text** to mark emphasis (replaces subheadings)
   - Use Lists (- or 1.2.3.) to organize points
   - Use empty lines to separate paragraphs
   - ❌ PROHIBITED to use #, ##, ###, #### or any heading syntax
4. [Quote Format Specification - Must be Standalone Paragraph]
   Quotes must be independent paragraphs, with empty lines before and after.

   ✅ Correct Format:
   ```
   The university response was considered lacking substance.
   
   > "The university's response mode appeared rigid and slow..."
   
   This evaluation reflects public dissatisfaction.
   ```
   
   ❌ Error Format:
   ```
   The university response... > "The response..." This evaluation...
   ```
5. Maintain logical coherence with other sections
6. [Avoid Repetition] Carefully read previously completed section content below
7. [Re-emphasize] DO NOT ADD ANY HEADINGS! Use **Bold** instead of subheadings. ALL TEXT MUST BE IN ENGLISH."""

        if previous_sections:
            previous_parts = []
            for sec in previous_sections:
                truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
                previous_parts.append(truncated)
            previous_content = "\n\n---\n\n".join(previous_parts)
        else:
            previous_content = "(This is the first section)"
        
        user_prompt = f"""[Previously Completed Section Content] (Read carefully to avoid repetition):
{previous_content}

═══════════════════════════════════════════════════════════════
[Current Task] Write Section: {section.title}
═══════════════════════════════════════════════════════════════

[Important Reminder]
1. Read above completed sections carefully, avoid repeating same content!
2. MUST start by calling tools to get simulation data
3. Recommend using insight_forge for deep search first
4. Report content MUST come from search results, DO NOT use your own knowledge
5. ALL OUTPUT MUST BE IN ENGLISH

[⚠️ Format Warning - MUST OBSERVE]
- ❌ DO NOT write any headings (#, ##, ###, #### allowed)
- ❌ DO NOT write "{section.title}" as start
- ✅ Section title is auto added by system
- ✅ Write body directly, use **Bold** instead of subheadings

Please start:
1. First Thought (Thought) what info this section needs
2. Then call Tool (Action) to get simulation data
3. After collecting enough info output Final Answer (Pure body content, no headings)"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        tool_calls_count = 0
        max_iterations = 5
        min_tool_calls = 2
        
        report_context = f"Section Title: {section.title}\nSimulation Requirement: {self.simulation_requirement}"
        
        for iteration in range(max_iterations):
            if progress_callback:
                progress_callback(
                    "generating", 
                    int((iteration / max_iterations) * 100),
                    f"Deep retrieval and writing ({tool_calls_count}/{self.MAX_TOOL_CALLS_PER_SECTION})"
                )
            
            response = self.llm.chat(
                messages=messages,
                temperature=0.5,
                max_tokens=4096
            )
            
            # Check for None response from LLM
            if response is None:
                logger.warning(f"LLM returned None response for section {section.title}, retrying...")
                continue
            
            logger.debug(f"LLM response: {response[:200]}...")
            
            has_tool_calls = bool(self._parse_tool_calls(response))
            has_final_answer = "Final Answer:" in response
            
            if self.report_logger:
                self.report_logger.log_llm_response(
                    section_title=section.title,
                    section_index=section_index,
                    response=response,
                    iteration=iteration + 1,
                    has_tool_calls=has_tool_calls,
                    has_final_answer=has_final_answer
                )
            
            if has_final_answer:
                if tool_calls_count < min_tool_calls:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user", 
                        "content": f"""[Note] You only called {tool_calls_count} tools. Information might be insufficient.

Please call 1-2 quotes tools more to get simulation data, then output Final Answer.
Recommendation:
- Use insight_forge to deep search details
- Use panorama_search to understand full picture

Remember: Report content MUST come from simulation results, NOT your knowledge!"""
                    })
                    continue
                
                final_answer = response.split("Final Answer:")[-1].strip()
                logger.info(f"Section {section.title} generation completed (Tool calls: {tool_calls_count})")
                
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
            
            tool_calls = self._parse_tool_calls(response)
            
            if not tool_calls:
                messages.append({"role": "assistant", "content": response})
                
                if tool_calls_count < min_tool_calls:
                    messages.append({
                        "role": "user", 
                        "content": f"""[Important] You haven't called enough tools!
Current: {tool_calls_count}, Minimum: {min_tool_calls}.

Please call tool immediately:
<tool_call>
{{"name": "insight_forge", "parameters": {{"query": "{section.title} related simulation results and analysis"}}}}
</tool_call>

[Remember] Content MUST be 100% from simulation!"""
                    })
                else:
                    messages.append({
                        "role": "user", 
                        "content": "You have enough simulation data. Please based on retrieved info, output Final Answer: and write section content.\n\n[Important] Content MUST heavily quote search results using > format. OUTPUT IN ENGLISH."
                    })
                continue
            
            tool_results = []
            for call in tool_calls:
                if tool_calls_count >= self.MAX_TOOL_CALLS_PER_SECTION:
                    break
                
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
            
            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user",
                "content": f"""Observation (Search Result):

{"".join(tool_results)}

═══════════════════════════════════════════════════════════════
[Next Action]
- If info sufficient: Output Final Answer and write content (MUST quote above results, IN ENGLISH)
- If need more info: Continue calling tools

Already called tools {tool_calls_count}/{self.MAX_TOOL_CALLS_PER_SECTION} times
═══════════════════════════════════════════════════════════════"""
            })
        
        logger.warning(f"Section {section.title} reached max iterations, forced generation")
        messages.append({
            "role": "user",
            "content": "Reached tool call limit. Please directly output Final Answer: and generate section content IN ENGLISH."
        })
        
        response = self.llm.chat(
            messages=messages,
            temperature=0.5,
            max_tokens=4096
        )
        
        # Handle None response
        if response is None:
            logger.error(f"LLM returned None in forced generation for section {section.title}")
            final_answer = f"[Section content could not be generated due to LLM error. Please retry report generation.]"
        elif "Final Answer:" in response:
            final_answer = response.split("Final Answer:")[-1].strip()
        else:
            final_answer = response
        
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
        Generate complete report (stream output by section)
        """
        import uuid
        
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
        
        completed_section_titles = []
        
        try:
            ReportManager._ensure_report_folder(report_id)
            
            self.report_logger = ReportLogger(report_id)
            self.report_logger.log_start(
                simulation_id=self.simulation_id,
                graph_id=self.graph_id,
                simulation_requirement=self.simulation_requirement
            )
            
            self.console_logger = ReportConsoleLogger(report_id)
            
            ReportManager.update_progress(
                report_id, "pending", 0, "Initializing report...",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            # Stage 1: Plan Outline
            report.status = ReportStatus.PLANNING
            ReportManager.update_progress(
                report_id, "planning", 5, "Start planning report outline...",
                completed_sections=[]
            )
            
            self.report_logger.log_planning_start()
            
            if progress_callback:
                progress_callback("planning", 0, "Start planning report outline...")
            
            outline = self.plan_outline(
                progress_callback=lambda stage, prog, msg: 
                    progress_callback(stage, prog // 5, msg) if progress_callback else None
            )
            report.outline = outline
            
            self.report_logger.log_planning_complete(outline.to_dict())
            
            ReportManager.save_outline(report_id, outline)
            ReportManager.update_progress(
                report_id, "planning", 15, f"Outline planned, total {len(outline.sections)} sections",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            logger.info(f"Outline saved: {report_id}/outline.json")
            
            # Stage 2: Generate Section by Section
            report.status = ReportStatus.GENERATING
            
            total_sections = len(outline.sections)
            generated_sections = []  # save content for context
            
            for i, section in enumerate(outline.sections):
                section_num = i + 1
                base_progress = 20 + int((i / total_sections) * 70)
                
                ReportManager.update_progress(
                    report_id, "generating", base_progress,
                    f"Generating section: {section.title} ({section_num}/{total_sections})",
                    current_section=section.title,
                    completed_sections=completed_section_titles
                )
                
                if progress_callback:
                    progress_callback(
                        "generating", 
                        base_progress, 
                        f"Generating section: {section.title} ({section_num}/{total_sections})"
                    )
                
                # Generate Main Section
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
                
                # Generate Subsections
                subsection_contents = []
                for j, subsection in enumerate(section.subsections):
                    subsection_num = j + 1
                    
                    if progress_callback:
                        progress_callback(
                            "generating",
                            base_progress + int(((j + 1) / max(len(section.subsections), 1)) * 5),
                            f"Generating subsection: {subsection.title}"
                        )
                    
                    ReportManager.update_progress(
                        report_id, "generating",
                        base_progress + int(((j + 1) / max(len(section.subsections), 1)) * 5),
                        f"Generating subsection: {subsection.title}",
                        current_section=subsection.title,
                        completed_sections=completed_section_titles
                    )
                    
                    subsection_content = self._generate_section_react(
                        section=subsection,
                        outline=outline,
                        previous_sections=generated_sections,
                        progress_callback=None,
                        section_index=section_num * 100 + subsection_num
                    )
                    subsection.content = subsection_content
                    generated_sections.append(f"### {subsection.title}\n\n{subsection_content}")
                    subsection_contents.append((subsection.title, subsection_content))
                    completed_section_titles.append(f"  └─ {subsection.title}")
                    
                    logger.info(f"Subsection generated: {subsection.title}")
                
                ReportManager.save_section_with_subsections(
                    report_id, section_num, section, subsection_contents
                )
                completed_section_titles.append(section.title)
                
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
                
                logger.info(f"Section saved ({len(subsection_contents)} subsections): {report_id}/section_{section_num:02d}.md")
                
                ReportManager.update_progress(
                    report_id, "generating", 
                    base_progress + int(70 / total_sections),
                    f"Section {section.title} completed",
                    current_section=None,
                    completed_sections=completed_section_titles
                )
            
            # Stage 3: Assemble Full Report
            if progress_callback:
                progress_callback("generating", 95, "Assembling complete report...")
            
            ReportManager.update_progress(
                report_id, "generating", 95, "Assembling complete report...",
                completed_sections=completed_section_titles
            )
            
            report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
            report.status = ReportStatus.COMPLETED
            report.completed_at = datetime.now().isoformat()
            
            total_time_seconds = (datetime.now() - start_time).total_seconds()
            
            if self.report_logger:
                self.report_logger.log_report_complete(
                    total_sections=total_sections,
                    total_time_seconds=total_time_seconds
                )
            
            ReportManager.save_report(report)
            ReportManager.update_progress(
                report_id, "completed", 100, "Report generation completed",
                completed_sections=completed_section_titles
            )
            
            if progress_callback:
                progress_callback("completed", 100, "Report generation completed")
            
            logger.info(f"Report generation completed: {report_id}")
            
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
            
        except Exception as e:
            logger.error(f"Report generation failed: {str(e)}")
            report.status = ReportStatus.FAILED
            report.error = str(e)
            
            if self.report_logger:
                self.report_logger.log_error(str(e), "failed")
            
            try:
                ReportManager.save_report(report)
                ReportManager.update_progress(
                    report_id, "failed", -1, f"Report generation failed: {str(e)}",
                    completed_sections=completed_section_titles
                )
            except Exception:
                pass
            
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
        Chat with Report Agent
        Agent can autonomously call search tools to answer questions.
        """
        logger.info(f"Report Agent chat: {message[:50]}...")
        
        chat_history = chat_history or []
        
        report_content = ""
        try:
            report = ReportManager.get_report_by_simulation(self.simulation_id)
            if report and report.markdown_content:
                report_content = report.markdown_content[:15000]
                if len(report.markdown_content) > 15000:
                    report_content += "\n\n... [Report content truncated] ..."
        except Exception as e:
            logger.warning(f"Get report content failed: {e}")
        
        system_prompt = f"""You are a concise and efficient Simulation Prediction Assistant.

[Background]
Prediction Condition: {self.simulation_requirement}

[Generated Analysis Report]
{report_content if report_content else "(No report available)"}

[Rules]
1. Prioritize answering based on report content above
2. Answer directly, avoid verbose reasoning
3. Only call tools if report content is insufficient
4. Answer concisely, clearly, reasonably
5. ALL OUTPUT MUST BE IN ENGLISH

[Available Tools] (Only use when needed, max 1-2 calls)
{self._get_tools_description()}

[Tool Call Format]
<tool_call>
{{"name": "tool_name", "parameters": {{"param_name": "param_value"}}}}
</tool_call>

[Style]
- Concise and direct
- Use > for quotes
- Give conclusion first, then explanation"""

        messages = [{"role": "system", "content": system_prompt}]
        
        for h in chat_history[-10:]:
            messages.append(h)
        
        messages.append({
            "role": "user", 
            "content": message
        })
        
        tool_calls_made = []
        max_iterations = 2
        
        for iteration in range(max_iterations):
            response = self.llm.chat(
                messages=messages,
                temperature=0.5
            )
            
            tool_calls = self._parse_tool_calls(response)
            
            if not tool_calls:
                clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', response, flags=re.DOTALL)
                clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
                
                return {
                    "response": clean_response.strip(),
                    "tool_calls": tool_calls_made,
                    "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
                }
            
            tool_results = []
            for call in tool_calls[:1]:
                if len(tool_calls_made) >= self.MAX_TOOL_CALLS_PER_CHAT:
                    break
                result = self._execute_tool(call["name"], call.get("parameters", {}))
                tool_results.append({
                    "tool": call["name"],
                    "result": result[:1500]
                })
                tool_calls_made.append(call)
            
            messages.append({"role": "assistant", "content": response})
            observation = "\n".join([f"[{r['tool']} Result]\n{r['result']}" for r in tool_results])
            messages.append({
                "role": "user", 
                "content": observation + "\n\nPlease answer concisely IN ENGLISH."
            })
        
        final_response = self.llm.chat(
            messages=messages,
            temperature=0.5
        )
        
        clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
        clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
        
        return {
            "response": clean_response.strip(),
            "tool_calls": tool_calls_made,
            "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
        }

class ReportManager:
    """
    Report Manager
    Responsible for report persistence and retrieval.
    
    File Structure (Section-based output):
    reports/
      {report_id}/
        meta.json          - Report metadata and status
        outline.json       - Report outline
        progress.json      - Generation progress
        section_01.md      - Section 1
        section_02.md      - Section 2
        ...
        full_report.md     - Complete report
    """
    
    # Report storage directory
    REPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'reports')
    
    @classmethod
    def _ensure_reports_dir(cls):
        """Ensure report root directory exists"""
        os.makedirs(cls.REPORTS_DIR, exist_ok=True)
    
    @classmethod
    def _get_report_folder(cls, report_id: str) -> str:
        """Get report folder path"""
        return os.path.join(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _ensure_report_folder(cls, report_id: str) -> str:
        """Ensure report folder exists and return path"""
        folder = cls._get_report_folder(report_id)
        os.makedirs(folder, exist_ok=True)
        return folder
    
    @classmethod
    def _get_report_path(cls, report_id: str) -> str:
        """Get report metadata file path"""
        return os.path.join(cls._get_report_folder(report_id), "meta.json")
    
    @classmethod
    def _get_report_markdown_path(cls, report_id: str) -> str:
        """Get complete report markdown file path"""
        return os.path.join(cls._get_report_folder(report_id), "full_report.md")
    
    @classmethod
    def _get_outline_path(cls, report_id: str) -> str:
        """Get outline file path"""
        return os.path.join(cls._get_report_folder(report_id), "outline.json")
    
    @classmethod
    def _get_progress_path(cls, report_id: str) -> str:
        """Get progress file path"""
        return os.path.join(cls._get_report_folder(report_id), "progress.json")
    
    @classmethod
    def _get_section_path(cls, report_id: str, section_index: int) -> str:
        """Get section markdown file path"""
        return os.path.join(cls._get_report_folder(report_id), f"section_{section_index:02d}.md")
    
    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        """Get agent log file path"""
        return os.path.join(cls._get_report_folder(report_id), "agent_log.jsonl")
    
    @classmethod
    def _get_console_log_path(cls, report_id: str) -> str:
        """Get console log file path"""
        return os.path.join(cls._get_report_folder(report_id), "console_log.txt")
    
    @classmethod
    def get_console_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Get console log content
        
        This is the console output logs (INFO, WARNING, etc.) during generation,
        different from structured log agent_log.jsonl.
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
                    # Keep original log lines, remove trailing newline
                    logs.append(line.rstrip('\n\r'))
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False
        }
    
    @classmethod
    def get_console_log_stream(cls, report_id: str) -> List[str]:
        """Get complete console log (all at once)"""
        result = cls.get_console_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Get Agent log content
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
                        continue
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False
        }
    
    @classmethod
    def get_agent_log_stream(cls, report_id: str) -> List[Dict[str, Any]]:
        """Get complete Agent log (all at once)"""
        result = cls.get_agent_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        """Save report outline"""
        cls._ensure_report_folder(report_id)
        
        with open(cls._get_outline_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(outline.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"Outline saved: {report_id}")
    
    @classmethod
    def save_section(
        cls, 
        report_id: str, 
        section_index: int, 
        section: ReportSection,
        is_subsection: bool = False,
        parent_index: int = None
    ) -> str:
        """Save single section (Not recommended, use save_section_with_subsections)"""
        cls._ensure_report_folder(report_id)
        
        if is_subsection and parent_index is not None:
            level = "###"
            file_suffix = f"section_{parent_index:02d}_{section_index:02d}.md"
        else:
            level = "##"
            file_suffix = f"section_{section_index:02d}.md"
        
        cleaned_content = cls._clean_section_content(section.content, section.title)
        md_content = f"{level} {section.title}\n\n"
        if cleaned_content:
            md_content += f"{cleaned_content}\n\n"
        
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"Section saved: {report_id}/{file_suffix}")
        return file_path
    
    @classmethod
    def save_section_with_subsections(
        cls,
        report_id: str,
        section_index: int,
        section: ReportSection,
        subsection_contents: List[tuple]
    ) -> str:
        """Save section and all its subsections to one file"""
        cls._ensure_report_folder(report_id)
        
        cleaned_main_content = cls._clean_section_content(section.content, section.title)
        md_content = f"## {section.title}\n\n"
        if cleaned_main_content:
            md_content += f"{cleaned_main_content}\n\n"
        
        for sub_title, sub_content in subsection_contents:
            cleaned_sub_content = cls._clean_section_content(sub_content, sub_title)
            md_content += f"### {sub_title}\n\n"
            if cleaned_sub_content:
                md_content += f"{cleaned_sub_content}\n\n"
        
        file_suffix = f"section_{section_index:02d}.md"
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"Section saved (with {len(subsection_contents)} subsections): {report_id}/{file_suffix}")
        return file_path
    
    @classmethod
    def _clean_section_content(cls, content: str, section_title: str) -> str:
        """
        Clean section content
        1. Remove heading lines at start that duplicate section title
        2. Convert all ### and lower level headings to Bold text
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
            
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title_text = heading_match.group(2).strip()
                
                # Check for duplicate title within first 5 lines
                if i < 5:
                    if title_text == section_title or title_text.replace(' ', '') == section_title.replace(' ', ''):
                        skip_next_empty = True
                        continue
                
                # Convert all headings to Bold
                # Because section title is added by system, content should not have any headings
                cleaned_lines.append(f"**{title_text}**")
                cleaned_lines.append("")
                continue
            
            if skip_next_empty and stripped == '':
                skip_next_empty = False
                continue
            
            skip_next_empty = False
            cleaned_lines.append(line)
        
        # Remove empty lines at start
        while cleaned_lines and cleaned_lines[0].strip() == '':
            cleaned_lines.pop(0)
        
        # Remove separators at start
        while cleaned_lines and cleaned_lines[0].strip() in ['---', '***', '___']:
            cleaned_lines.pop(0)
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
        """Update report generation progress"""
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
        """Get report generation progress"""
        path = cls._get_progress_path(report_id)
        
        if not os.path.exists(path):
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @classmethod
    def get_generated_sections(cls, report_id: str) -> List[Dict[str, Any]]:
        """Get list of generated sections"""
        folder = cls._get_report_folder(report_id)
        
        if not os.path.exists(folder):
            return []
        
        sections = []
        for filename in sorted(os.listdir(folder)):
            if filename.startswith('section_') and filename.endswith('.md'):
                file_path = os.path.join(folder, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
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
        """Assemble complete report"""
        folder = cls._get_report_folder(report_id)
        
        md_content = f"# {outline.title}\n\n"
        md_content += f"> {outline.summary}\n\n"
        md_content += f"---\n\n"
        
        sections = cls.get_generated_sections(report_id)
        for section_info in sections:
            # Skip separate subsection files (already merged in main section file)
            if section_info.get("is_subsection", False):
                continue
            md_content += section_info["content"]
        
        md_content = cls._post_process_report(md_content, outline)
        
        full_path = cls._get_report_markdown_path(report_id)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"Complete report assembled: {report_id}")
        return md_content
    
    @classmethod
    def _post_process_report(cls, content: str, outline: ReportOutline) -> str:
        """
        Post-process report content
        1. Remove duplicate headings
        2. Keep # and ##, convert others to Bold
        3. Clean extra empty lines
        """
        import re
        
        lines = content.split('\n')
        processed_lines = []
        prev_was_heading = False
        
        section_titles = set()
        for section in outline.sections:
            section_titles.add(section.title)
            for sub in section.subsections:
                section_titles.add(sub.title)
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                
                # Check duplicate
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
                    i += 1
                    while i < len(lines) and lines[i].strip() == '':
                        i += 1
                    continue
                
                if level == 1:
                    if title == outline.title:
                        processed_lines.append(line)
                        prev_was_heading = True
                    elif title in section_titles:
                        processed_lines.append(f"## {title}")
                        prev_was_heading = True
                    else:
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                elif level == 2:
                    if title in section_titles or title == outline.title:
                        processed_lines.append(line)
                        prev_was_heading = True
                    else:
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                else:
                    processed_lines.append(f"**{title}**")
                    processed_lines.append("")
                    prev_was_heading = False
                
                i += 1
                continue
            
            elif stripped == '---' and prev_was_heading:
                i += 1
                continue
            
            elif stripped == '' and prev_was_heading:
                if processed_lines and processed_lines[-1].strip() != '':
                    processed_lines.append(line)
                prev_was_heading = False
            
            else:
                processed_lines.append(line)
                prev_was_heading = False
            
            i += 1
        
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
        """Save report metadata and content"""
        cls._ensure_report_folder(report.report_id)
        
        with open(cls._get_report_path(report.report_id), 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        
        if report.outline:
            cls.save_outline(report.report_id, report.outline)
        
        if report.markdown_content:
            with open(cls._get_report_markdown_path(report.report_id), 'w', encoding='utf-8') as f:
                f.write(report.markdown_content)
        
        logger.info(f"Report saved: {report.report_id}")
    
    @classmethod
    def get_report(cls, report_id: str) -> Optional[Report]:
        """Get report by ID"""
        path = cls._get_report_path(report_id)
        
        if not os.path.exists(path):
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        report = Report(
            report_id=data.get("report_id"),
            simulation_id=data.get("simulation_id"),
            graph_id=data.get("graph_id"),
            simulation_requirement=data.get("simulation_requirement"),
            status=ReportStatus(data.get("status", "pending")),
            markdown_content=data.get("markdown_content", ""),
            created_at=data.get("created_at", ""),
            completed_at=data.get("completed_at", ""),
            error=data.get("error")
        )
        
        if data.get("outline"):
            out_data = data["outline"]
            sections = []
            for sec in out_data.get("sections", []):
                subs = []
                for sub in sec.get("subsections", []):
                    subs.append(ReportSection(
                        title=sub.get("title", ""),
                        content=sub.get("content", "")
                    ))
                sections.append(ReportSection(
                    title=sec.get("title", ""),
                    content=sec.get("content", ""),
                    subsections=subs
                ))
            
            report.outline = ReportOutline(
                title=out_data.get("title", ""),
                summary=out_data.get("summary", ""),
                sections=sections
            )
        
        return report
    
    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Optional[Report]:
        """
        Get report by simulation ID (Returns the latest one)
        """
        # Scan all report folders
        if not os.path.exists(cls.REPORTS_DIR):
            return None
            
        reports = []
        for report_id in os.listdir(cls.REPORTS_DIR):
            try:
                report = cls.get_report(report_id)
                if report and report.simulation_id == simulation_id:
                    reports.append(report)
            except Exception:
                continue
        
        if not reports:
            return None
            
        # Sort by creation time desc
        reports.sort(key=lambda x: x.created_at or "", reverse=True)
        return reports[0]
