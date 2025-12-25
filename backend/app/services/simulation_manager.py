"""
OASISsimulation管理器
管理TwitterandReddit双平台parallelsimulation
use预设脚本 + LLM智cangenerateconfigureparameters
"""

import os
import json
import shutil
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.logger import get_logger
from .neo4j_entity_reader import Neo4jEntityReader as ZepEntityReader, FilteredEntities
from .oasis_profile_generator import OasisProfileGenerator, OasisAgentProfile
from .simulation_config_generator import SimulationConfigGenerator, SimulationParameters

logger = get_logger('fishi.simulation')


class SimulationStatus(str, Enum):
    """simulationstatus"""
    CREATED = "created"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"      # simulation被手动stop
    COMPLETED = "completed"  # simulation自然completed
    FAILED = "failed"


class PlatformType(str, Enum):
    """platformtype"""
    TWITTER = "twitter"
    REDDIT = "reddit"


@dataclass
class SimulationState:
    """simulationstatus"""
    simulation_id: str
    project_id: str
    graph_id: str
    
    # platform启usestatus
    enable_twitter: bool = True
    enable_reddit: bool = True
    
    # status
    status: SimulationStatus = SimulationStatus.CREATED
    
    # 准备阶段count据
    entities_count: int = 0
    profiles_count: int = 0
    entity_types: List[str] = field(default_factory=list)
    
    # configurationgenerationinformation
    config_generated: bool = False
    config_reasoning: str = ""
    
    # running时count据
    current_round: int = 0
    twitter_status: str = "not_started"
    reddit_status: str = "not_started"
    
    # timestamp
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # errorinformation
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """completestatusdictionary（内部use）"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "enable_twitter": self.enable_twitter,
            "enable_reddit": self.enable_reddit,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_generated": self.config_generated,
            "config_reasoning": self.config_reasoning,
            "current_round": self.current_round,
            "twitter_status": self.twitter_status,
            "reddit_status": self.reddit_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }
    
    def to_simple_dict(self) -> Dict[str, Any]:
        """简化statusdictionary（APIreturnuse）"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_generated": self.config_generated,
            "error": self.error,
        }


class SimulationManager:
    """
    simulation管理器
    
    核心Features:
    1. fromZep图谱readentities并filter
    2. generateOASIS Agent Profile
    3. useLLM智cangeneratesimulationconfigureparameters
    4. 准备预设脚本所需of所havefile
    """
    
    # simulationcount据存储directory
    SIMULATION_DATA_DIR = os.path.join(
        os.path.dirname(__file__), 
        '../../uploads/simulations'
    )
    
    def __init__(self):
        # 确保directory存in
        os.makedirs(self.SIMULATION_DATA_DIR, exist_ok=True)
        
        # 内存 ofsimulationstatus缓存
        self._simulations: Dict[str, SimulationState] = {}
    
    def _get_simulation_dir(self, simulation_id: str) -> str:
        """getsimulationcount据directory"""
        sim_dir = os.path.join(self.SIMULATION_DATA_DIR, simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        return sim_dir
    
    def _save_simulation_state(self, state: SimulationState):
        """savesimulationstatusto file"""
        sim_dir = self._get_simulation_dir(state.simulation_id)
        state_file = os.path.join(sim_dir, "state.json")
        
        state.updated_at = datetime.now().isoformat()
        
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)
        
        self._simulations[state.simulation_id] = state
    
    def _load_simulation_state(self, simulation_id: str) -> Optional[SimulationState]:
        """fromfileloadsimulationstatus"""
        if simulation_id in self._simulations:
            return self._simulations[simulation_id]
        
        sim_dir = self._get_simulation_dir(simulation_id)
        state_file = os.path.join(sim_dir, "state.json")
        
        if not os.path.exists(state_file):
            return None
        
        with open(state_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        state = SimulationState(
            simulation_id=simulation_id,
            project_id=data.get("project_id", ""),
            graph_id=data.get("graph_id", ""),
            enable_twitter=data.get("enable_twitter", True),
            enable_reddit=data.get("enable_reddit", True),
            status=SimulationStatus(data.get("status", "created")),
            entities_count=data.get("entities_count", 0),
            profiles_count=data.get("profiles_count", 0),
            entity_types=data.get("entity_types", []),
            config_generated=data.get("config_generated", False),
            config_reasoning=data.get("config_reasoning", ""),
            current_round=data.get("current_round", 0),
            twitter_status=data.get("twitter_status", "not_started"),
            reddit_status=data.get("reddit_status", "not_started"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            error=data.get("error"),
        )
        
        self._simulations[simulation_id] = state
        return state
    
    def create_simulation(
        self,
        project_id: str,
        graph_id: str,
        enable_twitter: bool = True,
        enable_reddit: bool = True,
    ) -> SimulationState:
        """
        create新ofsimulation
        
        Args:
            project_id: itemsID
            graph_id: Zep图谱ID
            enable_twitter: whether to启useTwittersimulation
            enable_reddit: whether to启useRedditsimulation
            
        Returns:
            SimulationState
        """
        import uuid
        simulation_id = f"sim_{uuid.uuid4().hex[:12]}"
        
        state = SimulationState(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=enable_twitter,
            enable_reddit=enable_reddit,
            status=SimulationStatus.CREATED,
        )
        
        self._save_simulation_state(state)
        logger.info(f"createsimulation: {simulation_id}, project={project_id}, graph={graph_id}")
        
        return state
    
    def prepare_simulation(
        self,
        simulation_id: str,
        simulation_requirement: str,
        document_text: str,
        defined_entity_types: Optional[List[str]] = None,
        use_llm_for_profiles: bool = True,
        progress_callback: Optional[callable] = None,
        parallel_profile_count: int = 3
    ) -> SimulationState:
        """
        准备simulation环境（全程自动化）
        
        步骤：
        1. fromZep图谱read并filterentities
        2. for每entitiesgenerateOASIS Agent Profile（ can 选LLM增强，supportparallel）
        3. useLLM智cangeneratesimulationconfigureparameters（time、活跃度、发言频率etc）
        4. saveconfigurefileandProfilefile
        5. 复制预设脚本到simulationdirectory
        
        Args:
            simulation_id: simulationID
            simulation_requirement: simulationrequirementdescription（use于LLMgenerateconfigure）
            document_text: 原始文档content（use于LLM理解背景）
            defined_entity_types: 预定义ofentitiestype（ can 选）
            use_llm_for_profiles: whether touseLLMgeneratedetailedpeople设
            progress_callback: 进度回调function (stage, progress, message)
            parallel_profile_count: parallelgeneratepeople设ofquantity，默认3
            
        Returns:
            SimulationState
        """
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"simulationnot存in: {simulation_id}")
        
        try:
            state.status = SimulationStatus.PREPARING
            self._save_simulation_state(state)
            
            sim_dir = self._get_simulation_dir(simulation_id)
            
            # ========== 阶段1: read并filterentity ==========
            if progress_callback:
                progress_callback("reading", 0, "in progress连接Zepgraph...")
            
            reader = ZepEntityReader()
            
            if progress_callback:
                progress_callback("reading", 30, "in progressreadnodecount据...")
            
            filtered = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=defined_entity_types,
                enrich_with_edges=True
            )
            
            state.entities_count = filtered.filtered_count
            state.entity_types = list(filtered.entity_types)
            
            if progress_callback:
                progress_callback(
                    "reading", 100, 
                    f"completed, total {filtered.filtered_count} entity",
                    current=filtered.filtered_count,
                    total=filtered.filtered_count
                )
            
            if filtered.filtered_count == 0:
                state.status = SimulationStatus.FAILED
                state.error = "没have找到符合件ofentity，请checkgraphwhether to正确构建"
                self._save_simulation_state(state)
                return state
            
            # ========== 阶段2: generationAgent Profile ==========
            total_entities = len(filtered.entities)
            
            if progress_callback:
                progress_callback(
                    "generating_profiles", 0, 
                    "start generation...",
                    current=0,
                    total=total_entities
                )
            
            # 传入graph_id以启useZepretrievalfunction，get更丰富of上下文
            generator = OasisProfileGenerator(graph_id=state.graph_id)
            
            def profile_progress(current, total, msg):
                if progress_callback:
                    progress_callback(
                        "generating_profiles", 
                        int(current / total * 100), 
                        msg,
                        current=current,
                        total=total,
                        item_name=msg
                    )
            
            # set实时saveoffile路径（优firstuse Reddit JSON format）
            realtime_output_path = None
            realtime_platform = "reddit"
            if state.enable_reddit:
                realtime_output_path = os.path.join(sim_dir, "reddit_profiles.json")
                realtime_platform = "reddit"
            elif state.enable_twitter:
                realtime_output_path = os.path.join(sim_dir, "twitter_profiles.csv")
                realtime_platform = "twitter"
            
            profiles = generator.generate_profiles_from_entities(
                entities=filtered.entities,
                use_llm=use_llm_for_profiles,
                progress_callback=profile_progress,
                graph_id=state.graph_id,  # 传入graph_iduse于Zepretrieval
                parallel_count=parallel_profile_count,  # parallelgenerationquantity
                realtime_output_path=realtime_output_path,  # 实时save路径
                output_platform=realtime_platform  # 输出format
            )
            
            state.profiles_count = len(profiles)
            
            # saveProfilefile（Note：TwitteruseCSVformat，ReddituseJSONformat）
            # Reddit already经ingeneration过程 实时save，this里再save一times确保complete性
            if progress_callback:
                progress_callback(
                    "generating_profiles", 95, 
                    "saveProfilefile...",
                    current=total_entities,
                    total=total_entities
                )
            
            if state.enable_reddit:
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "reddit_profiles.json"),
                    platform="reddit"
                )
            
            if state.enable_twitter:
                # TwitteruseCSVformat！thisisOASISofwant求
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "twitter_profiles.csv"),
                    platform="twitter"
                )
            
            if progress_callback:
                progress_callback(
                    "generating_profiles", 100, 
                    f"completed, total {len(profiles)} Profile",
                    current=len(profiles),
                    total=len(profiles)
                )
            
            # ========== 阶段3: LLM智cangenerationsimulationconfiguration ==========
            if progress_callback:
                progress_callback(
                    "generating_config", 0, 
                    "in progress分析simulationrequirement...",
                    current=0,
                    total=3
                )
            
            config_generator = SimulationConfigGenerator()
            
            if progress_callback:
                progress_callback(
                    "generating_config", 30, 
                    "in progresscallLLMgenerationconfiguration...",
                    current=1,
                    total=3
                )
            
            sim_params = config_generator.generate_config(
                simulation_id=simulation_id,
                project_id=state.project_id,
                graph_id=state.graph_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                entities=filtered.entities,
                enable_twitter=state.enable_twitter,
                enable_reddit=state.enable_reddit
            )
            
            if progress_callback:
                progress_callback(
                    "generating_config", 70, 
                    "in progresssaveconfigurationfile...",
                    current=2,
                    total=3
                )
            
            # saveconfigurationfile
            config_path = os.path.join(sim_dir, "simulation_config.json")
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(sim_params.to_json())
            
            state.config_generated = True
            state.config_reasoning = sim_params.generation_reasoning
            
            if progress_callback:
                progress_callback(
                    "generating_config", 100, 
                    "configurationgeneration completed",
                    current=3,
                    total=3
                )
            
            # Note：running脚本保留in backend/scripts/ directory，not再复制到simulationdirectory
            # startsimulation时，simulation_runner willfrom scripts/ directoryrunning脚本
            
            # updatestatus
            state.status = SimulationStatus.READY
            self._save_simulation_state(state)
            
            logger.info(f"simulation准备completed: {simulation_id}, "
                       f"entities={state.entities_count}, profiles={state.profiles_count}")
            
            return state
            
        except Exception as e:
            logger.error(f"simulation准备failed: {simulation_id}, error={str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            state.status = SimulationStatus.FAILED
            state.error = str(e)
            self._save_simulation_state(state)
            raise
    
    def get_simulation(self, simulation_id: str) -> Optional[SimulationState]:
        """getsimulationstatus"""
        return self._load_simulation_state(simulation_id)
    
    def list_simulations(self, project_id: Optional[str] = None) -> List[SimulationState]:
        """列出所havesimulation"""
        simulations = []
        
        if os.path.exists(self.SIMULATION_DATA_DIR):
            for sim_id in os.listdir(self.SIMULATION_DATA_DIR):
                state = self._load_simulation_state(sim_id)
                if state:
                    if project_id is None or state.project_id == project_id:
                        simulations.append(state)
        
        return simulations
    
    def get_profiles(self, simulation_id: str, platform: str = "reddit") -> List[Dict[str, Any]]:
        """getsimulationofAgent Profile"""
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"simulationnot存in: {simulation_id}")
        
        sim_dir = self._get_simulation_dir(simulation_id)
        profile_path = os.path.join(sim_dir, f"{platform}_profiles.json")
        
        if not os.path.exists(profile_path):
            return []
        
        with open(profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_simulation_config(self, simulation_id: str) -> Optional[Dict[str, Any]]:
        """getsimulationconfiguration"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        
        if not os.path.exists(config_path):
            return None
        
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_run_instructions(self, simulation_id: str) -> Dict[str, str]:
        """getrunningsay明"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts'))
        
        return {
            "simulation_dir": sim_dir,
            "scripts_dir": scripts_dir,
            "config_file": config_path,
            "commands": {
                "twitter": f"python {scripts_dir}/run_twitter_simulation.py --config {config_path}",
                "reddit": f"python {scripts_dir}/run_reddit_simulation.py --config {config_path}",
                "parallel": f"python {scripts_dir}/run_parallel_simulation.py --config {config_path}",
            },
            "instructions": (
                f"1. 激活condaenvironment: conda activate MiroFish\n"
                f"2. runningsimulation (脚本位于 {scripts_dir}):\n"
                f"   - 单独runningTwitter: python {scripts_dir}/run_twitter_simulation.py --config {config_path}\n"
                f"   - 单独runningReddit: python {scripts_dir}/run_reddit_simulation.py --config {config_path}\n"
                f"   - parallelrunning双platform: python {scripts_dir}/run_parallel_simulation.py --config {config_path}"
            )
        }
