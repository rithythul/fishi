"""
simulationconfigure智cangenerate器
useLLMaccording tosimulationrequirement、文档content、图谱information自动generate细致ofsimulationparameters
implement全程自动化，无需people工setparameters

use分步generate策略，避免一times性generate过长content导致failed：
1. generatetimeconfigure
2. generate事件configure
3. 分批generateAgentconfigure
4. generate平台configure
"""

import json
import math
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime

from openai import OpenAI

from ..config import Config
from ..utils.logger import get_logger
from .neo4j_entity_reader import EntityNode, Neo4jEntityReader as ZepEntityReader

logger = get_logger('fishi.simulation_config')

#  国作息timeconfiguration（北京time）
CHINA_TIMEZONE_CONFIG = {
    # 深夜时段（几乎无people活动）
    "dead_hours": [0, 1, 2, 3, 4, 5],
    # 早间时段（逐渐醒come）
    "morning_hours": [6, 7, 8],
    # 工作时段
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    # 晚间高峰（最活跃）
    "peak_hours": [19, 20, 21, 22],
    # 夜间时段（活跃度下降）
    "night_hours": [23],
    # 活跃度系count
    "activity_multipliers": {
        "dead": 0.05,      # 凌晨几乎无people
        "morning": 0.4,    # 早间逐渐活跃
        "work": 0.7,       # 工作时段 etc
        "peak": 1.5,       # 晚间高峰
        "night": 0.5       # 深夜下降
    }
}


@dataclass
class AgentActivityConfig:
    """单Agentof活动configuration"""
    agent_id: int
    entity_uuid: str
    entity_name: str
    entity_type: str
    
    # 活跃度configuration (0.0-1.0)
    activity_level: float = 0.5  # 整体活跃度
    
    # 发言频率（每小时预期发言timescount）
    posts_per_hour: float = 1.0
    comments_per_hour: float = 2.0
    
    # 活跃time段（24小时制，0-23）
    active_hours: List[int] = field(default_factory=lambda: list(range(8, 23)))
    
    # response速度（to热点事件of反应延迟，单位：simulation分钟）
    response_delay_min: int = 5
    response_delay_max: int = 60
    
    # 情感倾向 (-1.0到1.0，负面到正面)
    sentiment_bias: float = 0.0
    
    # 立场（to特定话题of态度）
    stance: str = "neutral"  # supportive, opposing, neutral, observer
    
    # 影响力权重（决定其发言被其heAgentlook到of概率）
    influence_weight: float = 1.0


@dataclass  
class TimeSimulationConfig:
    """timesimulationconfiguration（基于 国people作息习惯）"""
    # simulationTotal时长（simulation小时count）
    total_simulation_hours: int = 72  # 默认simulation72小时（3天）
    
    # 每轮representsoftime（simulation分钟）- 默认60分钟（1小时），加快time流速
    minutes_per_round: int = 60
    
    # 每小时激活ofAgentquantity范围
    agents_per_hour_min: int = 5
    agents_per_hour_max: int = 20
    
    # 高峰时段（晚间19-22点， 国people最活跃oftime）
    peak_hours: List[int] = field(default_factory=lambda: [19, 20, 21, 22])
    peak_activity_multiplier: float = 1.5
    
    # 低谷时段（凌晨0-5点，几乎无people活动）
    off_peak_hours: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    off_peak_activity_multiplier: float = 0.05  # 凌晨活跃度极低
    
    # 早间时段
    morning_hours: List[int] = field(default_factory=lambda: [6, 7, 8])
    morning_activity_multiplier: float = 0.4
    
    # 工作时段
    work_hours: List[int] = field(default_factory=lambda: [9, 10, 11, 12, 13, 14, 15, 16, 17, 18])
    work_activity_multiplier: float = 0.7


@dataclass
class EventConfig:
    """事件configuration"""
    # 初始事件（simulationstart时of触发事件）
    initial_posts: List[Dict[str, Any]] = field(default_factory=list)
    
    # 定时事件（in特定time触发of事件）
    scheduled_events: List[Dict[str, Any]] = field(default_factory=list)
    
    # 热点话题关key词
    hot_topics: List[str] = field(default_factory=list)
    
    # 舆论引导方向
    narrative_direction: str = ""


@dataclass
class PlatformConfig:
    """platform特定configuration"""
    platform: str  # twitter or reddit
    
    # 推荐算法权重
    recency_weight: float = 0.4  # time新鲜度
    popularity_weight: float = 0.3  # 热度
    relevance_weight: float = 0.3  # related性
    
    # 病毒传播阈value（reached多少互动后触发扩散）
    viral_threshold: int = 10
    
    # 回声室效应强度（相似观点聚集程度）
    echo_chamber_strength: float = 0.5


@dataclass
class SimulationParameters:
    """completeofsimulationparametersconfiguration"""
    # 基础information
    simulation_id: str
    project_id: str
    graph_id: str
    simulation_requirement: str
    
    # timeconfiguration
    time_config: TimeSimulationConfig = field(default_factory=TimeSimulationConfig)
    
    # Agentconfigurationlist
    agent_configs: List[AgentActivityConfig] = field(default_factory=list)
    
    # 事件configuration
    event_config: EventConfig = field(default_factory=EventConfig)
    
    # platformconfiguration
    twitter_config: Optional[PlatformConfig] = None
    reddit_config: Optional[PlatformConfig] = None
    
    # LLMconfiguration
    llm_model: str = ""
    llm_base_url: str = ""
    
    # generation元count据
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    generation_reasoning: str = ""  # LLMof推理say明
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertfordictionary"""
        time_dict = asdict(self.time_config)
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "time_config": time_dict,
            "agent_configs": [asdict(a) for a in self.agent_configs],
            "event_config": asdict(self.event_config),
            "twitter_config": asdict(self.twitter_config) if self.twitter_config else None,
            "reddit_config": asdict(self.reddit_config) if self.reddit_config else None,
            "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "generated_at": self.generated_at,
            "generation_reasoning": self.generation_reasoning,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """ConvertforJSONstring"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class SimulationConfigGenerator:
    """
    simulationconfigure智cangenerate器
    
    useLLM分析simulationrequirement、文档content、图谱entitiesinformation，
    自动generate最佳ofsimulationparametersconfigure
    
    use分步generate策略：
    1. generatetimeconfigureand事件configure（轻量级）
    2. 分批generateAgentconfigure（每批10-20）
    3. generate平台configure
    """
    
    # 上下文maximumcharacterscount
    MAX_CONTEXT_LENGTH = 50000
    # 每批generationofAgentquantity
    AGENTS_PER_BATCH = 15
    
    # 各步骤of上下文截断length（characterscount）
    TIME_CONFIG_CONTEXT_LENGTH = 10000   # timeconfiguration
    EVENT_CONFIG_CONTEXT_LENGTH = 8000   # 事件configuration
    ENTITY_SUMMARY_LENGTH = 300          # entity摘want
    AGENT_SUMMARY_LENGTH = 300           # Agentconfiguration ofentity摘want
    ENTITIES_PER_TYPE_DISPLAY = 20       # 每classentity显示quantity
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model_name = model_name or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY not configured")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    def generate_config(
        self,
        simulation_id: str,
        project_id: str,
        graph_id: str,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode],
        enable_twitter: bool = True,
        enable_reddit: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> SimulationParameters:
        """
        智cangeneratecompleteofsimulationconfigure（分步generate）
        
        Args:
            simulation_id: simulationID
            project_id: itemsID
            graph_id: 图谱ID
            simulation_requirement: simulationrequirementdescription
            document_text: 原始文档content
            entities: filter后ofentitieslist
            enable_twitter: whether to启useTwitter
            enable_reddit: whether to启useReddit
            progress_callback: 进度回调function(current_step, total_steps, message)
            
        Returns:
            SimulationParameters: completeofsimulationparameters
        """
        logger.info(f"start智cangenerationsimulationconfiguration: simulation_id={simulation_id}, entitycount={len(entities)}")
        
        # 计算Total步骤count
        num_batches = math.ceil(len(entities) / self.AGENTS_PER_BATCH)
        total_steps = 3 + num_batches  # timeconfiguration + 事件configure + N批Agent + platformconfigure
        current_step = 0
        
        def report_progress(step: int, message: str):
            nonlocal current_step
            current_step = step
            if progress_callback:
                progress_callback(step, total_steps, message)
            logger.info(f"[{step}/{total_steps}] {message}")
        
        # 1. 构建基础上下文information
        context = self._build_context(
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            entities=entities
        )
        
        reasoning_parts = []
        
        # ========== 步骤1: generationtimeconfiguration ==========
        report_progress(1, "generationtimeconfiguration...")
        num_entities = len(entities)
        time_config_result = self._generate_time_config(context, num_entities)
        time_config = self._parse_time_config(time_config_result, num_entities)
        reasoning_parts.append(f"timeconfiguration: {time_config_result.get('reasoning', 'success')}")
        
        # ========== 步骤2: generation事件configuration ==========
        report_progress(2, "generation事件configurationand热点话题...")
        event_config_result = self._generate_event_config(context, simulation_requirement, entities)
        event_config = self._parse_event_config(event_config_result)
        reasoning_parts.append(f"事件configuration: {event_config_result.get('reasoning', 'success')}")
        
        # ========== 步骤3-N: 分批generationAgentconfiguration ==========
        all_agent_configs = []
        for batch_idx in range(num_batches):
            start_idx = batch_idx * self.AGENTS_PER_BATCH
            end_idx = min(start_idx + self.AGENTS_PER_BATCH, len(entities))
            batch_entities = entities[start_idx:end_idx]
            
            report_progress(
                3 + batch_idx,
                f"generationAgentconfiguration ({start_idx + 1}-{end_idx}/{len(entities)})..."
            )
            
            batch_configs = self._generate_agent_configs_batch(
                context=context,
                entities=batch_entities,
                start_idx=start_idx,
                simulation_requirement=simulation_requirement
            )
            all_agent_configs.extend(batch_configs)
        
        reasoning_parts.append(f"Agentconfiguration: successgeneration {len(all_agent_configs)} ")
        
        # ========== for初始帖子分配发布者 Agent ==========
        logger.info("for初始帖子分配合适of发布者 Agent...")
        event_config = self._assign_initial_post_agents(event_config, all_agent_configs)
        assigned_count = len([p for p in event_config.initial_posts if p.get("poster_agent_id") is not None])
        reasoning_parts.append(f"初始帖子分配: {assigned_count} 帖子already分配发布者")
        
        # ========== 最后一步: generationplatformconfiguration ==========
        report_progress(total_steps, "generationplatformconfiguration...")
        twitter_config = None
        reddit_config = None
        
        if enable_twitter:
            twitter_config = PlatformConfig(
                platform="twitter",
                recency_weight=0.4,
                popularity_weight=0.3,
                relevance_weight=0.3,
                viral_threshold=10,
                echo_chamber_strength=0.5
            )
        
        if enable_reddit:
            reddit_config = PlatformConfig(
                platform="reddit",
                recency_weight=0.3,
                popularity_weight=0.4,
                relevance_weight=0.3,
                viral_threshold=15,
                echo_chamber_strength=0.6
            )
        
        # 构建最终parameters
        params = SimulationParameters(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            simulation_requirement=simulation_requirement,
            time_config=time_config,
            agent_configs=all_agent_configs,
            event_config=event_config,
            twitter_config=twitter_config,
            reddit_config=reddit_config,
            llm_model=self.model_name,
            llm_base_url=self.base_url,
            generation_reasoning=" | ".join(reasoning_parts)
        )
        
        logger.info(f"simulationconfigurationgeneration completed: {len(params.agent_configs)} Agentconfigure")
        
        return params
    
    def _build_context(
        self,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode]
    ) -> str:
        """BuildLLM上下文，截断到maximumlength"""
        
        # entity摘want
        entity_summary = self._summarize_entities(entities)
        
        # 构建上下文
        context_parts = [
            f"## simulationrequirement\n{simulation_requirement}",
            f"\n## entityinformation ({len(entities)})\n{entity_summary}",
        ]
        
        current_length = sum(len(p) for p in context_parts)
        remaining_length = self.MAX_CONTEXT_LENGTH - current_length - 500  # 留500characters余量
        
        if remaining_length > 0 and document_text:
            doc_text = document_text[:remaining_length]
            if len(document_text) > remaining_length:
                doc_text += "\n...(文档already截断)"
            context_parts.append(f"\n## 原始文档content\n{doc_text}")
        
        return "\n".join(context_parts)
    
    def _summarize_entities(self, entities: List[EntityNode]) -> str:
        """generationentity摘want"""
        lines = []
        
        # Bytype分组
        by_type: Dict[str, List[EntityNode]] = {}
        for e in entities:
            t = e.get_entity_type() or "Unknown"
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(e)
        
        for entity_type, type_entities in by_type.items():
            lines.append(f"\n### {entity_type} ({len(type_entities)})")
            # useconfigurationof显示quantityand摘wantlength
            display_count = self.ENTITIES_PER_TYPE_DISPLAY
            summary_len = self.ENTITY_SUMMARY_LENGTH
            for e in type_entities[:display_count]:
                summary_preview = (e.summary[:summary_len] + "...") if len(e.summary) > summary_len else e.summary
                lines.append(f"- {e.name}: {summary_preview}")
            if len(type_entities) > display_count:
                lines.append(f"  ... 还have {len(type_entities) - display_count} ")
        
        return "\n".join(lines)
    
    def _call_llm_with_retry(self, prompt: str, system_prompt: str) -> Dict[str, Any]:
        """带retryofLLMcall，containsJSONFIXME逻辑"""
        import re
        
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1)  # 每timesretry降低温度
                    # notsetmax_tokens，让LLM自由发挥
                )
                
                content = response.choices[0].message.content
                finish_reason = response.choices[0].finish_reason
                
                # checkwhether to被截断
                if finish_reason == 'length':
                    logger.warning(f"LLMoutput truncated (attempt {attempt+1})")
                    content = self._fix_truncated_json(content)
                
                # 尝试parseJSON
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSONparsefailed (attempt {attempt+1}): {str(e)[:80]}")
                    
                    # attempting to fixJSON
                    fixed = self._try_fix_config_json(content)
                    if fixed:
                        return fixed
                    
                    last_error = e
                    
            except Exception as e:
                logger.warning(f"LLMcallfailed (attempt {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(2 * (attempt + 1))
        
        raise last_error or Exception("LLMcallfailed")
    
    def _fix_truncated_json(self, content: str) -> str:
        """FIXME被截断ofJSON"""
        content = content.strip()
        
        # 计算not闭合of括号
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        
        # checkwhether tohavenot闭合ofstring
        if content and content[-1] not in '",}]':
            content += '"'
        
        # 闭合括号
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
    
    def _try_fix_config_json(self, content: str) -> Optional[Dict[str, Any]]:
        """attempting to fixconfigurationJSON"""
        import re
        
        # FIXME被截断of情况
        content = self._fix_truncated_json(content)
        
        # ExtractJSON部分
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()
            
            # 移除string of换行符
            def fix_string(match):
                s = match.group(0)
                s = s.replace('\n', ' ').replace('\r', ' ')
                s = re.sub(r'\s+', ' ', s)
                return s
            
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string, json_str)
            
            try:
                return json.loads(json_str)
            except:
                # 尝试移除所have控制characters
                json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                json_str = re.sub(r'\s+', ' ', json_str)
                try:
                    return json.loads(json_str)
                except:
                    pass
        
        return None
    
    def _generate_time_config(self, context: str, num_entities: int) -> Dict[str, Any]:
        """generationtimeconfiguration"""
        # useconfigurationof上下文截断length
        context_truncated = context[:self.TIME_CONFIG_CONTEXT_LENGTH]
        
        # 计算maximum允许value（80%ofagentcount）
        max_agents_allowed = max(1, int(num_entities * 0.9))
        
        prompt = f"""基于以下simulationrequirement，generatetimesimulationconfigure。

{context_truncated}

## 任务
请generatetimeconfigureJSON。

### 基本原则（仅供参考，需according to具体事件and参withgroup灵活Adjust）：
- usergroupfor 国people，需符合北京time作息习惯
- 凌晨0-5点几乎无people活动（活跃度系count0.05）
- 早上6-8点逐渐活跃（活跃度系count0.4）
- 工作time9-18点 etc活跃（活跃度系count0.7）
- 晚间19-22点is高峰期（活跃度系count1.5）
- 23点后活跃度下降（活跃度系count0.5）
- 一般规律：凌晨低活跃、早间渐增、工作时段 etc、晚间高峰
- **重want**：以下examplevalue仅供参考，you需wantaccording to事件性质、参withgroup特点comeAdjust具体时段
  - for example：学生group高峰 can canis21-23点；媒体全天活跃；官方机构只in工作time
  - for example：突发热点 can can导致深夜alsohave讨论，off_peak_hours  can 适当缩短

### returnJSONformat（notwantmarkdown）

Example:
{{
    "total_simulation_hours": 72,
    "minutes_per_round": 60,
    "agents_per_hour_min": 5,
    "agents_per_hour_max": 50,
    "peak_hours": [19, 20, 21, 22],
    "off_peak_hours": [0, 1, 2, 3, 4, 5],
    "morning_hours": [6, 7, 8],
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    "reasoning": "针to该事件oftimeconfigurationsay明"
}}

字段Description:
- total_simulation_hours (int): simulationTotal时长，24-168小时，突发事件短、持续话题长
- minutes_per_round (int): 每轮时长，30-120分钟，建议60分钟
- agents_per_hour_min (int): 每小时最少激活Agentcount（取value范围: 1-{max_agents_allowed}）
- agents_per_hour_max (int): 每小时最多激活Agentcount（取value范围: 1-{max_agents_allowed}）
- peak_hours (intarray): 高峰时段，according to事件参withgroupAdjust
- off_peak_hours (intarray): 低谷时段，通常深夜凌晨
- morning_hours (intarray): 早间时段
- work_hours (intarray): 工作时段
- reasoning (string): 简wantsay明for什么this样configure"""

        system_prompt = "youis社交媒体simulation专家。return纯JSONformat，timeconfiguration需符合 国people作息习惯。"
        
        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"timeconfigurationLLMgenerationfailed: {e}, use默认configure")
            return self._get_default_time_config(num_entities)
    
    def _get_default_time_config(self, num_entities: int) -> Dict[str, Any]:
        """get默认timeconfiguration（ 国people作息）"""
        return {
            "total_simulation_hours": 72,
            "minutes_per_round": 60,  # 每轮1小时，加快time流速
            "agents_per_hour_min": max(1, num_entities // 15),
            "agents_per_hour_max": max(5, num_entities // 5),
            "peak_hours": [19, 20, 21, 22],
            "off_peak_hours": [0, 1, 2, 3, 4, 5],
            "morning_hours": [6, 7, 8],
            "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
            "reasoning": "use默认 国people作息configuration（每轮1小时）"
        }
    
    def _parse_time_config(self, result: Dict[str, Any], num_entities: int) -> TimeSimulationConfig:
        """Parsetimeconfigurationresult，并validateagents_per_hourvaluenot超过Totalagentcount"""
        # get原始value
        agents_per_hour_min = result.get("agents_per_hour_min", max(1, num_entities // 15))
        agents_per_hour_max = result.get("agents_per_hour_max", max(5, num_entities // 5))
        
        # validate并修正：确保not超过Totalagentcount
        if agents_per_hour_min > num_entities:
            logger.warning(f"agents_per_hour_min ({agents_per_hour_min}) 超过TotalAgentcount ({num_entities})，already修正")
            agents_per_hour_min = max(1, num_entities // 10)
        
        if agents_per_hour_max > num_entities:
            logger.warning(f"agents_per_hour_max ({agents_per_hour_max}) 超过TotalAgentcount ({num_entities})，already修正")
            agents_per_hour_max = max(agents_per_hour_min + 1, num_entities // 2)
        
        # 确保 min < max
        if agents_per_hour_min >= agents_per_hour_max:
            agents_per_hour_min = max(1, agents_per_hour_max // 2)
            logger.warning(f"agents_per_hour_min >= max，already修正for {agents_per_hour_min}")
        
        return TimeSimulationConfig(
            total_simulation_hours=result.get("total_simulation_hours", 72),
            minutes_per_round=result.get("minutes_per_round", 60),  # 默认每轮1小时
            agents_per_hour_min=agents_per_hour_min,
            agents_per_hour_max=agents_per_hour_max,
            peak_hours=result.get("peak_hours", [19, 20, 21, 22]),
            off_peak_hours=result.get("off_peak_hours", [0, 1, 2, 3, 4, 5]),
            off_peak_activity_multiplier=0.05,  # 凌晨几乎无people
            morning_hours=result.get("morning_hours", [6, 7, 8]),
            morning_activity_multiplier=0.4,
            work_hours=result.get("work_hours", list(range(9, 19))),
            work_activity_multiplier=0.7,
            peak_activity_multiplier=1.5
        )
    
    def _generate_event_config(
        self, 
        context: str, 
        simulation_requirement: str,
        entities: List[EntityNode]
    ) -> Dict[str, Any]:
        """generation事件configuration"""
        
        # get can useofentity typeslist，供 LLM 参考
        entity_types_available = list(set(
            e.get_entity_type() or "Unknown" for e in entities
        ))
        
        # for每种type列出represents性entity名称
        type_examples = {}
        for e in entities:
            etype = e.get_entity_type() or "Unknown"
            if etype not in type_examples:
                type_examples[etype] = []
            if len(type_examples[etype]) < 3:
                type_examples[etype].append(e.name)
        
        type_information = "\n".join([
            f"- {t}: {', '.join(examples)}" 
            for t, examples in type_examples.items()
        ])
        
        # useconfigurationof上下文截断length
        context_truncated = context[:self.EVENT_CONFIG_CONTEXT_LENGTH]
        
        prompt = f"""基于以下simulationrequirement，generate事件configure。

simulationrequirement: {simulation_requirement}

{context_truncated}

##  can useentity typesandexample
{type_information}

## 任务
请generate事件configureJSON：
- Extract热点话题关key词
- description舆论发展方向
- 设计初始帖子content，**每帖子must指定 poster_type（发布者type）**

**重want**: poster_type mustfrom上面of" can useentity types" 选择，this样初始帖子才can分配give合适of Agent 发布。
for example：官方声明应由 Official/University type发布，新闻由 MediaOutlet 发布，学生观点由 Student 发布。

returnJSONformat（notwantmarkdown）：
{{
    "hot_topics": ["关key词1", "关key词2", ...],
    "narrative_direction": "<舆论发展方向description>",
    "initial_posts": [
        {{"content": "帖子content", "poster_type": "entity types（mustfrom can usetype 选择）"}},
        ...
    ],
    "reasoning": "<简wantsay明>"
}}"""

        system_prompt = "youis舆论分析专家。return纯JSONformat。Note poster_type must精确匹配 can useentity types。"
        
        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"事件configurationLLMgenerationfailed: {e}, use默认configure")
            return {
                "hot_topics": [],
                "narrative_direction": "",
                "initial_posts": [],
                "reasoning": "use默认configuration"
            }
    
    def _parse_event_config(self, result: Dict[str, Any]) -> EventConfig:
        """Parse事件configurationresult"""
        return EventConfig(
            initial_posts=result.get("initial_posts", []),
            scheduled_events=[],
            hot_topics=result.get("hot_topics", []),
            narrative_direction=result.get("narrative_direction", "")
        )
    
    def _assign_initial_post_agents(
        self,
        event_config: EventConfig,
        agent_configs: List[AgentActivityConfig]
    ) -> EventConfig:
        """
        for初始帖子分配合适of发布者 Agent
        
        according to每帖子of poster_type 匹配最合适of agent_id
        """
        if not event_config.initial_posts:
            return event_config
        
        # Byentity types建立 agent index
        agents_by_type: Dict[str, List[AgentActivityConfig]] = {}
        for agent in agent_configs:
            etype = agent.entity_type.lower()
            if etype not in agents_by_type:
                agents_by_type[etype] = []
            agents_by_type[etype].append(agent)
        
        # type映射表（processing LLM  can can输出ofnot同format）
        type_aliases = {
            "official": ["official", "university", "governmentagency", "government"],
            "university": ["university", "official"],
            "mediaoutlet": ["mediaoutlet", "media"],
            "student": ["student", "person"],
            "professor": ["professor", "expert", "teacher"],
            "alumni": ["alumni", "person"],
            "organization": ["organization", "ngo", "company", "group"],
            "person": ["person", "student", "alumni"],
        }
        
        # record每种typealreadyuseof agent index，避免重复use同一 agent
        used_indices: Dict[str, int] = {}
        
        updated_posts = []
        for post in event_config.initial_posts:
            poster_type = post.get("poster_type", "").lower()
            content = post.get("content", "")
            
            # 尝试找到匹配of agent
            matched_agent_id = None
            
            # 1. 直接匹配
            if poster_type in agents_by_type:
                agents = agents_by_type[poster_type]
                idx = used_indices.get(poster_type, 0) % len(agents)
                matched_agent_id = agents[idx].agent_id
                used_indices[poster_type] = idx + 1
            else:
                # 2. use别名匹配
                for alias_key, aliases in type_aliases.items():
                    if poster_type in aliases or alias_key == poster_type:
                        for alias in aliases:
                            if alias in agents_by_type:
                                agents = agents_by_type[alias]
                                idx = used_indices.get(alias, 0) % len(agents)
                                matched_agent_id = agents[idx].agent_id
                                used_indices[alias] = idx + 1
                                break
                    if matched_agent_id is not None:
                        break
            
            # 3. if仍not找到，use影响力最高of agent
            if matched_agent_id is None:
                logger.warning(f"not找到type '{poster_type}' of匹配 Agent，use影响力最高of Agent")
                if agent_configs:
                    # By影响力sort，选择影响力最高of
                    sorted_agents = sorted(agent_configs, key=lambda a: a.influence_weight, reverse=True)
                    matched_agent_id = sorted_agents[0].agent_id
                else:
                    matched_agent_id = 0
            
            updated_posts.append({
                "content": content,
                "poster_type": post.get("poster_type", "Unknown"),
                "poster_agent_id": matched_agent_id
            })
            
            logger.info(f"初始帖子分配: poster_type='{poster_type}' -> agent_id={matched_agent_id}")
        
        event_config.initial_posts = updated_posts
        return event_config
    
    def _generate_agent_configs_batch(
        self,
        context: str,
        entities: List[EntityNode],
        start_idx: int,
        simulation_requirement: str
    ) -> List[AgentActivityConfig]:
        """分批generationAgentconfiguration"""
        
        # 构建entityinformation（useconfigurationof摘wantlength）
        entity_list = []
        summary_len = self.AGENT_SUMMARY_LENGTH
        for i, e in enumerate(entities):
            entity_list.append({
                "agent_id": start_idx + i,
                "entity_name": e.name,
                "entity_type": e.get_entity_type() or "Unknown",
                "summary": e.summary[:summary_len] if e.summary else ""
            })
        
        prompt = f"""基于以下information，for每entitiesgenerate社交媒体活动configure。

simulationrequirement: {simulation_requirement}

## entitylist
```json
{json.dumps(entity_list, ensure_ascii=False, indent=2)}
```

## 任务
for每entitiesgenerate活动configure，Note:
- **time符合 国people作息**：凌晨0-5点几乎not活动，晚间19-22点最活跃
- **官方机构**（University/GovernmentAgency）：活跃度低(0.1-0.3)，工作time(9-17)活动，response慢(60-240分钟)，影响力高(2.5-3.0)
- **媒体**（MediaOutlet）：活跃度 (0.4-0.6)，全天活动(8-23)，response快(5-30分钟)，影响力高(2.0-2.5)
- **people**（Student/Person/Alumni）：活跃度高(0.6-0.9)，主want晚间活动(18-23)，response快(1-15分钟)，影响力低(0.8-1.2)
- **公众people物/专家**：活跃度 (0.4-0.6)，影响力 高(1.5-2.0)

returnJSONformat（notwantmarkdown）：
{{
    "agent_configs": [
        {{
            "agent_id": <mustwith输入一致>,
            "activity_level": <0.0-1.0>,
            "posts_per_hour": <发帖频率>,
            "comments_per_hour": <评论频率>,
            "active_hours": [<活跃小时list，考虑 国people作息>],
            "response_delay_min": <minimumresponse延迟分钟>,
            "response_delay_max": <maximumresponse延迟分钟>,
            "sentiment_bias": <-1.0到1.0>,
            "stance": "<supportive/opposing/neutral/observer>",
            "influence_weight": <影响力权重>
        }},
        ...
    ]
}}"""

        system_prompt = "youis社交媒体行for分析专家。return纯JSON，configuration需符合 国people作息习惯。"
        
        try:
            result = self._call_llm_with_retry(prompt, system_prompt)
            llm_configs = {cfg["agent_id"]: cfg for cfg in result.get("agent_configs", [])}
        except Exception as e:
            logger.warning(f"Agentconfiguration批timesLLMgenerationfailed: {e}, using rule-based generation")
            llm_configs = {}
        
        # 构建AgentActivityConfigobject
        configs = []
        for i, entity in enumerate(entities):
            agent_id = start_idx + i
            cfg = llm_configs.get(agent_id, {})
            
            # ifLLM没havegeneration，using rule-based generation
            if not cfg:
                cfg = self._generate_agent_config_by_rule(entity)
            
            config = AgentActivityConfig(
                agent_id=agent_id,
                entity_uuid=entity.uuid,
                entity_name=entity.name,
                entity_type=entity.get_entity_type() or "Unknown",
                activity_level=cfg.get("activity_level", 0.5),
                posts_per_hour=cfg.get("posts_per_hour", 0.5),
                comments_per_hour=cfg.get("comments_per_hour", 1.0),
                active_hours=cfg.get("active_hours", list(range(9, 23))),
                response_delay_min=cfg.get("response_delay_min", 5),
                response_delay_max=cfg.get("response_delay_max", 60),
                sentiment_bias=cfg.get("sentiment_bias", 0.0),
                stance=cfg.get("stance", "neutral"),
                influence_weight=cfg.get("influence_weight", 1.0)
            )
            configs.append(config)
        
        return configs
    
    def _generate_agent_config_by_rule(self, entity: EntityNode) -> Dict[str, Any]:
        """基于规则generation单Agentconfiguration（ 国people作息）"""
        entity_type = (entity.get_entity_type() or "Unknown").lower()
        
        if entity_type in ["university", "governmentagency", "ngo"]:
            # 官方机构：工作time活动，低频率，高影响力
            return {
                "activity_level": 0.2,
                "posts_per_hour": 0.1,
                "comments_per_hour": 0.05,
                "active_hours": list(range(9, 18)),  # 9:00-17:59
                "response_delay_min": 60,
                "response_delay_max": 240,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 3.0
            }
        elif entity_type in ["mediaoutlet"]:
            # 媒体：全天活动， etc频率，高影响力
            return {
                "activity_level": 0.5,
                "posts_per_hour": 0.8,
                "comments_per_hour": 0.3,
                "active_hours": list(range(7, 24)),  # 7:00-23:59
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "observer",
                "influence_weight": 2.5
            }
        elif entity_type in ["professor", "expert", "official"]:
            # 专家/教授：工作+晚间活动， etc频率
            return {
                "activity_level": 0.4,
                "posts_per_hour": 0.3,
                "comments_per_hour": 0.5,
                "active_hours": list(range(8, 22)),  # 8:00-21:59
                "response_delay_min": 15,
                "response_delay_max": 90,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 2.0
            }
        elif entity_type in ["student"]:
            # 学生：晚间for主，高频率
            return {
                "activity_level": 0.8,
                "posts_per_hour": 0.6,
                "comments_per_hour": 1.5,
                "active_hours": [8, 9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # 上午+晚间
                "response_delay_min": 1,
                "response_delay_max": 15,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 0.8
            }
        elif entity_type in ["alumni"]:
            # 校友：晚间for主
            return {
                "activity_level": 0.6,
                "posts_per_hour": 0.4,
                "comments_per_hour": 0.8,
                "active_hours": [12, 13, 19, 20, 21, 22, 23],  # 午休+晚间
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }
        else:
            # 普通people：晚间高峰
            return {
                "activity_level": 0.7,
                "posts_per_hour": 0.5,
                "comments_per_hour": 1.2,
                "active_hours": [9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # 白天+晚间
                "response_delay_min": 2,
                "response_delay_max": 20,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }
    

