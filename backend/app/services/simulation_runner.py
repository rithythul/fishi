"""
OASISsimulationrunning器
in后台runningsimulation并record每Agentofaction，support实时status监控
"""

import os
import sys
import json
import time
import asyncio
import threading
import subprocess
import signal
import atexit
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from queue import Queue

from ..config import Config
from ..utils.logger import get_logger
from .neo4j_graph_memory_updater import Neo4jGraphMemoryManager as ZepGraphMemoryManager
from .simulation_ipc import SimulationIPCClient, CommandType, IPCResponse

logger = get_logger('fishi.simulation_runner')

# 标记whether toalready registered清理function
_cleanup_registered = False


class RunnerStatus(str, Enum):
    """Run器status"""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentAction:
    """Agentactionrecord"""
    round_num: int
    timestamp: str
    platform: str  # twitter / reddit
    agent_id: int
    agent_name: str
    action_type: str  # CREATE_POST, LIKE_POST, etc.
    action_args: Dict[str, Any] = field(default_factory=dict)
    result: Optional[str] = None
    success: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_num": self.round_num,
            "timestamp": self.timestamp,
            "platform": self.platform,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "action_type": self.action_type,
            "action_args": self.action_args,
            "result": self.result,
            "success": self.success,
        }


@dataclass
class RoundSummary:
    """每轮摘want"""
    round_num: int
    start_time: str
    end_time: Optional[str] = None
    simulated_hour: int = 0
    twitter_actions: int = 0
    reddit_actions: int = 0
    active_agents: List[int] = field(default_factory=list)
    actions: List[AgentAction] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_num": self.round_num,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "simulated_hour": self.simulated_hour,
            "twitter_actions": self.twitter_actions,
            "reddit_actions": self.reddit_actions,
            "active_agents": self.active_agents,
            "actions_count": len(self.actions),
            "actions": [a.to_dict() for a in self.actions],
        }


@dataclass
class SimulationRunState:
    """simulationrunningstatus（实时）"""
    simulation_id: str
    runner_status: RunnerStatus = RunnerStatus.IDLE
    
    # 进度information
    current_round: int = 0
    total_rounds: int = 0
    simulated_hours: int = 0
    total_simulation_hours: int = 0
    
    # 各platform独立轮timesandsimulationtime（use于双平台parallel显示）
    twitter_current_round: int = 0
    reddit_current_round: int = 0
    twitter_simulated_hours: int = 0
    reddit_simulated_hours: int = 0
    
    # platformstatus
    twitter_running: bool = False
    reddit_running: bool = False
    twitter_actions_count: int = 0
    reddit_actions_count: int = 0
    
    # platformcompletedstatus（through检测 actions.jsonl  of simulation_end 事件）
    twitter_completed: bool = False
    reddit_completed: bool = False
    
    # 每轮摘want
    rounds: List[RoundSummary] = field(default_factory=list)
    
    # 最近action（use于前端实时展示）
    recent_actions: List[AgentAction] = field(default_factory=list)
    max_recent_actions: int = 50
    
    # timestamp
    started_at: Optional[str] = None
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    
    # errorinformation
    error: Optional[str] = None
    
    # 进程ID（use于stop）
    process_pid: Optional[int] = None
    
    def add_action(self, action: AgentAction):
        """添加action到最近actionlist"""
        self.recent_actions.insert(0, action)
        if len(self.recent_actions) > self.max_recent_actions:
            self.recent_actions = self.recent_actions[:self.max_recent_actions]
        
        if action.platform == "twitter":
            self.twitter_actions_count += 1
        else:
            self.reddit_actions_count += 1
        
        self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "runner_status": self.runner_status.value,
            "current_round": self.current_round,
            "total_rounds": self.total_rounds,
            "simulated_hours": self.simulated_hours,
            "total_simulation_hours": self.total_simulation_hours,
            "progress_percent": round(self.current_round / max(self.total_rounds, 1) * 100, 1),
            # 各platform独立轮timesandtime
            "twitter_current_round": self.twitter_current_round,
            "reddit_current_round": self.reddit_current_round,
            "twitter_simulated_hours": self.twitter_simulated_hours,
            "reddit_simulated_hours": self.reddit_simulated_hours,
            "twitter_running": self.twitter_running,
            "reddit_running": self.reddit_running,
            "twitter_completed": self.twitter_completed,
            "reddit_completed": self.reddit_completed,
            "twitter_actions_count": self.twitter_actions_count,
            "reddit_actions_count": self.reddit_actions_count,
            "total_actions_count": self.twitter_actions_count + self.reddit_actions_count,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "process_pid": self.process_pid,
        }
    
    def to_detail_dict(self) -> Dict[str, Any]:
        """contains最近actionofdetailed informationrmation"""
        result = self.to_dict()
        result["recent_actions"] = [a.to_dict() for a in self.recent_actions]
        result["rounds_count"] = len(self.rounds)
        return result


class SimulationRunner:
    """
    simulationrunning器
    
    负责：
    1. in后台进程 runningOASISsimulation
    2. parserunninglog，record每Agentofaction
    3. 提供实时statusQueryinterface
    4. supportpaused/stopped/恢复操作
    """
    
    # runningstatus存储directory
    RUN_STATE_DIR = os.path.join(
        os.path.dirname(__file__),
        '../../uploads/simulations'
    )
    
    # 脚本directory
    SCRIPTS_DIR = os.path.join(
        os.path.dirname(__file__),
        '../../scripts'
    )
    
    # 内存 ofrunningstatus
    _run_states: Dict[str, SimulationRunState] = {}
    _processes: Dict[str, subprocess.Popen] = {}
    _action_queues: Dict[str, Queue] = {}
    _monitor_threads: Dict[str, threading.Thread] = {}
    _stdout_files: Dict[str, Any] = {}  # 存储 stdout file句柄
    _stderr_files: Dict[str, Any] = {}  # 存储 stderr file句柄
    
    # graph记忆updateconfiguration
    _graph_memory_enabled: Dict[str, bool] = {}  # simulation_id -> enabled
    
    @classmethod
    def get_run_state(cls, simulation_id: str) -> Optional[SimulationRunState]:
        """getrunningstatus"""
        if simulation_id in cls._run_states:
            return cls._run_states[simulation_id]
        
        # 尝试fromfileload
        state = cls._load_run_state(simulation_id)
        if state:
            cls._run_states[simulation_id] = state
        return state
    
    @classmethod
    def _load_run_state(cls, simulation_id: str) -> Optional[SimulationRunState]:
        """fromfileloadrunningstatus"""
        state_file = os.path.join(cls.RUN_STATE_DIR, simulation_id, "run_state.json")
        if not os.path.exists(state_file):
            return None
        
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            state = SimulationRunState(
                simulation_id=simulation_id,
                runner_status=RunnerStatus(data.get("runner_status", "idle")),
                current_round=data.get("current_round", 0),
                total_rounds=data.get("total_rounds", 0),
                simulated_hours=data.get("simulated_hours", 0),
                total_simulation_hours=data.get("total_simulation_hours", 0),
                # 各platform独立轮timesandtime
                twitter_current_round=data.get("twitter_current_round", 0),
                reddit_current_round=data.get("reddit_current_round", 0),
                twitter_simulated_hours=data.get("twitter_simulated_hours", 0),
                reddit_simulated_hours=data.get("reddit_simulated_hours", 0),
                twitter_running=data.get("twitter_running", False),
                reddit_running=data.get("reddit_running", False),
                twitter_completed=data.get("twitter_completed", False),
                reddit_completed=data.get("reddit_completed", False),
                twitter_actions_count=data.get("twitter_actions_count", 0),
                reddit_actions_count=data.get("reddit_actions_count", 0),
                started_at=data.get("started_at"),
                updated_at=data.get("updated_at", datetime.now().isoformat()),
                completed_at=data.get("completed_at"),
                error=data.get("error"),
                process_pid=data.get("process_pid"),
            )
            
            # load最近action
            actions_data = data.get("recent_actions", [])
            for a in actions_data:
                state.recent_actions.append(AgentAction(
                    round_num=a.get("round_num", 0),
                    timestamp=a.get("timestamp", ""),
                    platform=a.get("platform", ""),
                    agent_id=a.get("agent_id", 0),
                    agent_name=a.get("agent_name", ""),
                    action_type=a.get("action_type", ""),
                    action_args=a.get("action_args", {}),
                    result=a.get("result"),
                    success=a.get("success", True),
                ))
            
            return state
        except Exception as e:
            logger.error(f"loadrunningstatusfailed: {str(e)}")
            return None
    
    @classmethod
    def _save_run_state(cls, state: SimulationRunState):
        """saverunningstatusto file"""
        sim_dir = os.path.join(cls.RUN_STATE_DIR, state.simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        state_file = os.path.join(sim_dir, "run_state.json")
        
        data = state.to_detail_dict()
        
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        cls._run_states[state.simulation_id] = state
    
    @classmethod
    def start_simulation(
        cls,
        simulation_id: str,
        platform: str = "parallel",  # twitter / reddit / parallel
        max_rounds: int = None,  # maximumsimulation轮count（ can 选，use于截断过长ofsimulation）
        enable_graph_memory_update: bool = False,  # whether to will 活动update到Zepgraph
        graph_id: str = None  # ZepgraphID（启use图谱update时必需）
    ) -> SimulationRunState:
        """
        启动simulation
        
        Args:
            simulation_id: simulationID
            platform: running平台 (twitter/reddit/parallel)
            max_rounds: maximumsimulation轮count（ can 选，use于截断过长ofsimulation）
            enable_graph_memory_update: whether to will Agent活动动态update到Zep图谱
            graph_id: Zep图谱ID（启use图谱update时必需）
            
        Returns:
            SimulationRunState
        """
        # checkwhether toalreadyinrunning
        existing = cls.get_run_state(simulation_id)
        if existing and existing.runner_status in [RunnerStatus.RUNNING, RunnerStatus.STARTING]:
            raise ValueError(f"simulationalreadyinrunning: {simulation_id}")
        
        # loadsimulationconfiguration
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        
        if not os.path.exists(config_path):
            raise ValueError(f"simulationconfigurationnot存in，please call first /prepare interface")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # initializationrunningstatus
        time_config = config.get("time_config", {})
        total_hours = time_config.get("total_simulation_hours", 72)
        minutes_per_round = time_config.get("minutes_per_round", 30)
        total_rounds = int(total_hours * 60 / minutes_per_round)
        
        # if指定maximum轮count，则截断
        if max_rounds is not None and max_rounds > 0:
            original_rounds = total_rounds
            total_rounds = min(total_rounds, max_rounds)
            if total_rounds < original_rounds:
                logger.info(f"轮countalready截断: {original_rounds} -> {total_rounds} (max_rounds={max_rounds})")
        
        state = SimulationRunState(
            simulation_id=simulation_id,
            runner_status=RunnerStatus.STARTING,
            total_rounds=total_rounds,
            total_simulation_hours=total_hours,
            started_at=datetime.now().isoformat(),
        )
        
        cls._save_run_state(state)
        
        # if启usegraph记忆update，createupdate器
        if enable_graph_memory_update:
            if not graph_id:
                raise ValueError("启usegraph记忆update时must提供 graph_id")
            
            try:
                ZepGraphMemoryManager.create_updater(simulation_id, graph_id)
                cls._graph_memory_enabled[simulation_id] = True
                logger.info(f"already启usegraph记忆update: simulation_id={simulation_id}, graph_id={graph_id}")
            except Exception as e:
                logger.error(f"Create graph记忆update器failed: {e}")
                cls._graph_memory_enabled[simulation_id] = False
        else:
            cls._graph_memory_enabled[simulation_id] = False
        
        # 确定running哪脚本（脚本位于 backend/scripts/ directory）
        if platform == "twitter":
            script_name = "run_twitter_simulation.py"
            state.twitter_running = True
        elif platform == "reddit":
            script_name = "run_reddit_simulation.py"
            state.reddit_running = True
        else:
            script_name = "run_parallel_simulation.py"
            state.twitter_running = True
            state.reddit_running = True
        
        script_path = os.path.join(cls.SCRIPTS_DIR, script_name)
        
        if not os.path.exists(script_path):
            raise ValueError(f"脚本not存in: {script_path}")
        
        # createaction队列
        action_queue = Queue()
        cls._action_queues[simulation_id] = action_queue
        
        # startsimulation进程
        try:
            # 构建running命令，usecomplete路径
            # 新oflogstructure：
            #   twitter/actions.jsonl - Twitter actionlog
            #   reddit/actions.jsonl  - Reddit actionlog
            #   simulation.log        - 主进程log
            
            cmd = [
                sys.executable,  # Python解释器
                script_path,
                "--config", config_path,  # usecompleteconfigurationfile路径
            ]
            
            # if指定maximum轮count，添加到命令行parameters
            if max_rounds is not None and max_rounds > 0:
                cmd.extend(["--max-rounds", str(max_rounds)])
            
            # create主logfile，避免 stdout/stderr 管道缓冲区满导致进程阻塞
            main_log_path = os.path.join(sim_dir, "simulation.log")
            main_log_file = open(main_log_path, 'w', encoding='utf-8')
            
            # set工作directoryforsimulationdirectory（count据libraryetcfilewillgenerationin此）
            # use start_new_session=True create新of进程组，确保canthrough os.killpg 终止所have子进程
            process = subprocess.Popen(
                cmd,
                cwd=sim_dir,
                stdout=main_log_file,
                stderr=subprocess.STDOUT,  # stderr alsowrite同一file
                text=True,
                bufsize=1,
                start_new_session=True,  # create新进程组，确保service器关闭时can终止所haverelated进程
            )
            
            # savefile句柄以便后续关闭
            cls._stdout_files[simulation_id] = main_log_file
            cls._stderr_files[simulation_id] = None  # not再需want单独of stderr
            
            state.process_pid = process.pid
            state.runner_status = RunnerStatus.RUNNING
            cls._processes[simulation_id] = process
            cls._save_run_state(state)
            
            # start监控线程
            monitor_thread = threading.Thread(
                target=cls._monitor_simulation,
                args=(simulation_id,),
                daemon=True
            )
            monitor_thread.start()
            cls._monitor_threads[simulation_id] = monitor_thread
            
            logger.info(f"simulationstartsuccess: {simulation_id}, pid={process.pid}, platform={platform}")
            
        except Exception as e:
            state.runner_status = RunnerStatus.FAILED
            state.error = str(e)
            cls._save_run_state(state)
            raise
        
        return state
    
    @classmethod
    def _monitor_simulation(cls, simulation_id: str):
        """监控simulation进程，parseactionlog"""
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        
        # 新oflogstructure：分platformofactionlog
        twitter_actions_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
        reddit_actions_log = os.path.join(sim_dir, "reddit", "actions.jsonl")
        
        process = cls._processes.get(simulation_id)
        state = cls.get_run_state(simulation_id)
        
        if not process or not state:
            return
        
        twitter_position = 0
        reddit_position = 0
        
        try:
            while process.poll() is None:  # 进程仍inrunning
                # read Twitter actionlog
                if os.path.exists(twitter_actions_log):
                    twitter_position = cls._read_action_log(
                        twitter_actions_log, twitter_position, state, "twitter"
                    )
                
                # read Reddit actionlog
                if os.path.exists(reddit_actions_log):
                    reddit_position = cls._read_action_log(
                        reddit_actions_log, reddit_position, state, "reddit"
                    )
                
                # updatestatus
                cls._save_run_state(state)
                time.sleep(2)
            
            # 进程end后，最后read一timeslog
            if os.path.exists(twitter_actions_log):
                cls._read_action_log(twitter_actions_log, twitter_position, state, "twitter")
            if os.path.exists(reddit_actions_log):
                cls._read_action_log(reddit_actions_log, reddit_position, state, "reddit")
            
            # 进程end
            exit_code = process.returncode
            
            if exit_code == 0:
                state.runner_status = RunnerStatus.COMPLETED
                state.completed_at = datetime.now().isoformat()
                logger.info(f"simulationcompleted: {simulation_id}")
            else:
                state.runner_status = RunnerStatus.FAILED
                # from主logfilereaderrorinformation
                main_log_path = os.path.join(sim_dir, "simulation.log")
                error_information = ""
                try:
                    if os.path.exists(main_log_path):
                        with open(main_log_path, 'r', encoding='utf-8') as f:
                            error_information = f.read()[-2000:]  # 取最后2000characters
                except Exception:
                    pass
                state.error = f"进程退出码: {exit_code}, error: {error_information}"
                logger.error(f"simulationfailed: {simulation_id}, error={state.error}")
            
            state.twitter_running = False
            state.reddit_running = False
            cls._save_run_state(state)
            
        except Exception as e:
            logger.error(f"监控线程异常: {simulation_id}, error={str(e)}")
            state.runner_status = RunnerStatus.FAILED
            state.error = str(e)
            cls._save_run_state(state)
        
        finally:
            # stopgraph记忆update器
            if cls._graph_memory_enabled.get(simulation_id, False):
                try:
                    ZepGraphMemoryManager.stop_updater(simulation_id)
                    logger.info(f"alreadystopgraph记忆update: simulation_id={simulation_id}")
                except Exception as e:
                    logger.error(f"stopgraph记忆update器failed: {e}")
                cls._graph_memory_enabled.pop(simulation_id, None)
            
            # 清理进程资源
            cls._processes.pop(simulation_id, None)
            cls._action_queues.pop(simulation_id, None)
            
            # 关闭logfile句柄
            if simulation_id in cls._stdout_files:
                try:
                    cls._stdout_files[simulation_id].close()
                except Exception:
                    pass
                cls._stdout_files.pop(simulation_id, None)
            if simulation_id in cls._stderr_files and cls._stderr_files[simulation_id]:
                try:
                    cls._stderr_files[simulation_id].close()
                except Exception:
                    pass
                cls._stderr_files.pop(simulation_id, None)
    
    @classmethod
    def _read_action_log(
        cls, 
        log_path: str, 
        position: int, 
        state: SimulationRunState,
        platform: str
    ) -> int:
        """
        readactionlogfile
        
        Args:
            log_path: logfile路径
            position: 上timesreadposition
            state: runningstatusobject
            platform: 平台名称 (twitter/reddit)
            
        Returns:
            新ofreadposition
        """
        # checkwhether to启usegraph记忆update
        graph_memory_enabled = cls._graph_memory_enabled.get(state.simulation_id, False)
        graph_updater = None
        if graph_memory_enabled:
            graph_updater = ZepGraphMemoryManager.get_updater(state.simulation_id)
        
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                f.seek(position)
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            action_data = json.loads(line)
                            
                            # processing事件typeof目
                            if "event_type" in action_data:
                                event_type = action_data.get("event_type")
                                
                                # 检测 simulation_end 事件，标记platformalreadycompleted
                                if event_type == "simulation_end":
                                    if platform == "twitter":
                                        state.twitter_completed = True
                                        state.twitter_running = False
                                        logger.info(f"Twitter simulationalreadycompleted: {state.simulation_id}, total_rounds={action_data.get('total_rounds')}, total_actions={action_data.get('total_actions')}")
                                    elif platform == "reddit":
                                        state.reddit_completed = True
                                        state.reddit_running = False
                                        logger.info(f"Reddit simulationalreadycompleted: {state.simulation_id}, total_rounds={action_data.get('total_rounds')}, total_actions={action_data.get('total_actions')}")
                                    
                                    # checkwhether to所have启useofplatform都alreadycompleted
                                    # if只running一platform，只checkthat平台
                                    # ifrunning两platform，需want两都completed
                                    all_completed = cls._check_all_platforms_completed(state)
                                    if all_completed:
                                        state.runner_status = RunnerStatus.COMPLETED
                                        state.completed_at = datetime.now().isoformat()
                                        logger.info(f"所haveplatformsimulationalreadycompleted: {state.simulation_id}")
                                
                                # update轮timesinformation（from round_end 事件）
                                elif event_type == "round_end":
                                    round_num = action_data.get("round", 0)
                                    simulated_hours = action_data.get("simulated_hours", 0)
                                    
                                    # update各platform独立of轮timesandtime
                                    if platform == "twitter":
                                        if round_num > state.twitter_current_round:
                                            state.twitter_current_round = round_num
                                        state.twitter_simulated_hours = simulated_hours
                                    elif platform == "reddit":
                                        if round_num > state.reddit_current_round:
                                            state.reddit_current_round = round_num
                                        state.reddit_simulated_hours = simulated_hours
                                    
                                    # Total体轮times取两platformofmaximumvalue
                                    if round_num > state.current_round:
                                        state.current_round = round_num
                                    # Total体time取两platformofmaximumvalue
                                    state.simulated_hours = max(state.twitter_simulated_hours, state.reddit_simulated_hours)
                                
                                continue
                            
                            action = AgentAction(
                                round_num=action_data.get("round", 0),
                                timestamp=action_data.get("timestamp", datetime.now().isoformat()),
                                platform=platform,
                                agent_id=action_data.get("agent_id", 0),
                                agent_name=action_data.get("agent_name", ""),
                                action_type=action_data.get("action_type", ""),
                                action_args=action_data.get("action_args", {}),
                                result=action_data.get("result"),
                                success=action_data.get("success", True),
                            )
                            state.add_action(action)
                            
                            # update轮times
                            if action.round_num and action.round_num > state.current_round:
                                state.current_round = action.round_num
                            
                            # if启usegraph记忆update， will 活动send到Zep
                            if graph_updater:
                                graph_updater.add_activity_from_dict(action_data, platform)
                            
                        except json.JSONDecodeError:
                            pass
                return f.tell()
        except Exception as e:
            logger.warning(f"readactionlogfailed: {log_path}, error={e}")
            return position
    
    @classmethod
    def _check_all_platforms_completed(cls, state: SimulationRunState) -> bool:
        """
        check所have启useof平台whether to都 already completedsimulation
        
        throughcheckto应of actions.jsonl filewhether to存income判断平台whether to被启use
        
        Returns:
            True if所have启useof平台都 already completed
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, state.simulation_id)
        twitter_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
        reddit_log = os.path.join(sim_dir, "reddit", "actions.jsonl")
        
        # check哪些platform被启use（throughfilewhether to存in判断）
        twitter_enabled = os.path.exists(twitter_log)
        reddit_enabled = os.path.exists(reddit_log)
        
        # ifplatform被启usebutnotcompleted，则return False
        if twitter_enabled and not state.twitter_completed:
            return False
        if reddit_enabled and not state.reddit_completed:
            return False
        
        # 至少have一platform被启use且alreadycompleted
        return twitter_enabled or reddit_enabled
    
    @classmethod
    def stop_simulation(cls, simulation_id: str) -> SimulationRunState:
        """stopsimulation"""
        state = cls.get_run_state(simulation_id)
        if not state:
            raise ValueError(f"simulationnot存in: {simulation_id}")
        
        if state.runner_status not in [RunnerStatus.RUNNING, RunnerStatus.PAUSED]:
            raise ValueError(f"simulationnotinrunning: {simulation_id}, status={state.runner_status}")
        
        state.runner_status = RunnerStatus.STOPPING
        cls._save_run_state(state)
        
        # 终止进程
        process = cls._processes.get(simulation_id)
        if process and process.poll() is None:
            try:
                # use进程组 ID 终止整进程组（package括所have子进程）
                # due touse start_new_session=True，进程组 ID etc于主进程 PID
                pgid = os.getpgid(process.pid)
                logger.info(f"终止进程组: simulation={simulation_id}, pgid={pgid}")
                
                # firstsend SIGTERM give整进程组
                os.killpg(pgid, signal.SIGTERM)
                
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    # if 10 秒后还没end，forcedsend SIGKILL
                    logger.warning(f"进程组notresponse SIGTERM，forced终止: {simulation_id}")
                    os.killpg(pgid, signal.SIGKILL)
                    process.wait(timeout=5)
                    
            except ProcessLookupError:
                # 进程already经not存in
                pass
            except Exception as e:
                logger.error(f"终止进程组failed: {simulation_id}, error={e}")
                # 回退到直接终止进程
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except Exception:
                    process.kill()
        
        state.runner_status = RunnerStatus.STOPPED
        state.twitter_running = False
        state.reddit_running = False
        state.completed_at = datetime.now().isoformat()
        cls._save_run_state(state)
        
        # stopgraph记忆update器
        if cls._graph_memory_enabled.get(simulation_id, False):
            try:
                ZepGraphMemoryManager.stop_updater(simulation_id)
                logger.info(f"alreadystopgraph记忆update: simulation_id={simulation_id}")
            except Exception as e:
                logger.error(f"stopgraph记忆update器failed: {e}")
            cls._graph_memory_enabled.pop(simulation_id, None)
        
        logger.info(f"simulationalreadystop: {simulation_id}")
        return state
    
    @classmethod
    def _read_actions_from_file(
        cls,
        file_path: str,
        default_platform: Optional[str] = None,
        platform_filter: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None
    ) -> List[AgentAction]:
        """
        from单actionfile readaction
        
        Args:
            file_path: actionlogfile路径
            default_platform: 默认平台（当actionrecord 没have platform 字段时use）
            platform_filter: filter平台
            agent_id: filter Agent ID
            round_num: filter轮times
        """
        if not os.path.exists(file_path):
            return []
        
        actions = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    
                    # 跳过非actionrecord（such as simulation_start, round_start, round_end etc事件）
                    if "event_type" in data:
                        continue
                    
                    # 跳过没have agent_id ofrecord（非 Agent action）
                    if "agent_id" not in data:
                        continue
                    
                    # getplatform：优firstuserecord of platform，否则use默认平台
                    record_platform = data.get("platform") or default_platform or ""
                    
                    # filter
                    if platform_filter and record_platform != platform_filter:
                        continue
                    if agent_id is not None and data.get("agent_id") != agent_id:
                        continue
                    if round_num is not None and data.get("round") != round_num:
                        continue
                    
                    actions.append(AgentAction(
                        round_num=data.get("round", 0),
                        timestamp=data.get("timestamp", ""),
                        platform=record_platform,
                        agent_id=data.get("agent_id", 0),
                        agent_name=data.get("agent_name", ""),
                        action_type=data.get("action_type", ""),
                        action_args=data.get("action_args", {}),
                        result=data.get("result"),
                        success=data.get("success", True),
                    ))
                    
                except json.JSONDecodeError:
                    continue
        
        return actions
    
    @classmethod
    def get_all_actions(
        cls,
        simulation_id: str,
        platform: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None
    ) -> List[AgentAction]:
        """
        get所have平台ofcompleteactionhistory（无分页限制）
        
        Args:
            simulation_id: simulationID
            platform: filter平台（twitter/reddit）
            agent_id: filterAgent
            round_num: filter轮times
            
        Returns:
            completeofactionlist（Bytimestampsort，新ofin前）
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        actions = []
        
        # read Twitter actionfile（according tofile路径自动set platform for twitter）
        twitter_actions_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
        if not platform or platform == "twitter":
            actions.extend(cls._read_actions_from_file(
                twitter_actions_log,
                default_platform="twitter",  # 自动填充 platform 字段
                platform_filter=platform,
                agent_id=agent_id, 
                round_num=round_num
            ))
        
        # read Reddit actionfile（according tofile路径自动set platform for reddit）
        reddit_actions_log = os.path.join(sim_dir, "reddit", "actions.jsonl")
        if not platform or platform == "reddit":
            actions.extend(cls._read_actions_from_file(
                reddit_actions_log,
                default_platform="reddit",  # 自动填充 platform 字段
                platform_filter=platform,
                agent_id=agent_id,
                round_num=round_num
            ))
        
        # if分platformfilenot存in，尝试read旧of单一fileFormat
        if not actions:
            actions_log = os.path.join(sim_dir, "actions.jsonl")
            actions = cls._read_actions_from_file(
                actions_log,
                default_platform=None,  # 旧Formatfile shouldhave platform 字段
                platform_filter=platform,
                agent_id=agent_id,
                round_num=round_num
            )
        
        # Bytimestampsort（新ofin前）
        actions.sort(key=lambda x: x.timestamp, reverse=True)
        
        return actions
    
    @classmethod
    def get_actions(
        cls,
        simulation_id: str,
        limit: int = 100,
        offset: int = 0,
        platform: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None
    ) -> List[AgentAction]:
        """
        getactionhistory（带分页）
        
        Args:
            simulation_id: simulationID
            limit: returnquantity限制
            offset: 偏移量
            platform: filter平台
            agent_id: filterAgent
            round_num: filter轮times
            
        Returns:
            actionlist
        """
        actions = cls.get_all_actions(
            simulation_id=simulation_id,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num
        )
        
        # 分页
        return actions[offset:offset + limit]
    
    @classmethod
    def get_timeline(
        cls,
        simulation_id: str,
        start_round: int = 0,
        end_round: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        getsimulationtime线（By轮times汇Total）
        
        Args:
            simulation_id: simulationID
            start_round: 起始轮times
            end_round: end轮times
            
        Returns:
            每轮of汇Totalinformation
        """
        actions = cls.get_actions(simulation_id, limit=10000)
        
        # By轮times分组
        rounds: Dict[int, Dict[str, Any]] = {}
        
        for action in actions:
            round_num = action.round_num
            
            if round_num < start_round:
                continue
            if end_round is not None and round_num > end_round:
                continue
            
            if round_num not in rounds:
                rounds[round_num] = {
                    "round_num": round_num,
                    "twitter_actions": 0,
                    "reddit_actions": 0,
                    "active_agents": set(),
                    "action_types": {},
                    "first_action_time": action.timestamp,
                    "last_action_time": action.timestamp,
                }
            
            r = rounds[round_num]
            
            if action.platform == "twitter":
                r["twitter_actions"] += 1
            else:
                r["reddit_actions"] += 1
            
            r["active_agents"].add(action.agent_id)
            r["action_types"][action.action_type] = r["action_types"].get(action.action_type, 0) + 1
            r["last_action_time"] = action.timestamp
        
        # convertforlist
        result = []
        for round_num in sorted(rounds.keys()):
            r = rounds[round_num]
            result.append({
                "round_num": round_num,
                "twitter_actions": r["twitter_actions"],
                "reddit_actions": r["reddit_actions"],
                "total_actions": r["twitter_actions"] + r["reddit_actions"],
                "active_agents_count": len(r["active_agents"]),
                "active_agents": list(r["active_agents"]),
                "action_types": r["action_types"],
                "first_action_time": r["first_action_time"],
                "last_action_time": r["last_action_time"],
            })
        
        return result
    
    @classmethod
    def get_agent_stats(cls, simulation_id: str) -> List[Dict[str, Any]]:
        """
        get每Agentofstatisticsinformation
        
        Returns:
            Agentstatisticslist
        """
        actions = cls.get_actions(simulation_id, limit=10000)
        
        agent_stats: Dict[int, Dict[str, Any]] = {}
        
        for action in actions:
            agent_id = action.agent_id
            
            if agent_id not in agent_stats:
                agent_stats[agent_id] = {
                    "agent_id": agent_id,
                    "agent_name": action.agent_name,
                    "total_actions": 0,
                    "twitter_actions": 0,
                    "reddit_actions": 0,
                    "action_types": {},
                    "first_action_time": action.timestamp,
                    "last_action_time": action.timestamp,
                }
            
            stats = agent_stats[agent_id]
            stats["total_actions"] += 1
            
            if action.platform == "twitter":
                stats["twitter_actions"] += 1
            else:
                stats["reddit_actions"] += 1
            
            stats["action_types"][action.action_type] = stats["action_types"].get(action.action_type, 0) + 1
            stats["last_action_time"] = action.timestamp
        
        # ByTotalactioncountsort
        result = sorted(agent_stats.values(), key=lambda x: x["total_actions"], reverse=True)
        
        return result
    
    @classmethod
    def cleanup_simulation_logs(cls, simulation_id: str) -> Dict[str, Any]:
        """
        清理simulationofrunninglog（use于forced重新startsimulation）
        
        willdelete以下file：
        - run_state.json
        - twitter/actions.jsonl
        - reddit/actions.jsonl
        - simulation.log
        - stdout.log / stderr.log
        - twitter_simulation.db（simulationcount据library）
        - reddit_simulation.db（simulationcount据library）
        - env_status.json（环境status）
        
        Note:notwilldeleteconfigurefile（simulation_config.json）and profile file
        
        Args:
            simulation_id: simulationID
            
        Returns:
            清理resultinformation
        """
        import shutil
        
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        
        if not os.path.exists(sim_dir):
            return {"success": True, "message": "simulationdirectorynot存in，无需清理"}
        
        cleaned_files = []
        errors = []
        
        # wantdeleteoffilelist（package括count据libraryfile）
        files_to_delete = [
            "run_state.json",
            "simulation.log",
            "stdout.log",
            "stderr.log",
            "twitter_simulation.db",  # Twitter platformcount据library
            "reddit_simulation.db",   # Reddit platformcount据library
            "env_status.json",        # environmentstatusfile
        ]
        
        # wantdeleteofdirectorylist（containsactionlog）
        dirs_to_clean = ["twitter", "reddit"]
        
        # deletefile
        for filename in files_to_delete:
            file_path = os.path.join(sim_dir, filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    cleaned_files.append(filename)
                except Exception as e:
                    errors.append(f"delete {filename} failed: {str(e)}")
        
        # 清理platformdirectory ofactionlog
        for dir_name in dirs_to_clean:
            dir_path = os.path.join(sim_dir, dir_name)
            if os.path.exists(dir_path):
                actions_file = os.path.join(dir_path, "actions.jsonl")
                if os.path.exists(actions_file):
                    try:
                        os.remove(actions_file)
                        cleaned_files.append(f"{dir_name}/actions.jsonl")
                    except Exception as e:
                        errors.append(f"delete {dir_name}/actions.jsonl failed: {str(e)}")
        
        # 清理内存 ofrunningstatus
        if simulation_id in cls._run_states:
            del cls._run_states[simulation_id]
        
        logger.info(f"清理simulationlogcompleted: {simulation_id}, deletefile: {cleaned_files}")
        
        return {
            "success": len(errors) == 0,
            "cleaned_files": cleaned_files,
            "errors": errors if errors else None
        }
    
    # 防止重复清理of标志
    _cleanup_done = False
    
    @classmethod
    def cleanup_all_simulations(cls):
        """
        清理所haverunning ofsimulation进程
        
        inservice器关闭时call，确保所have子进程被终止
        """
        # 防止重复清理
        if cls._cleanup_done:
            return
        cls._cleanup_done = True
        
        # checkwhether tohavecontent需want清理（避免空进程of进程打印无uselog）
        has_processes = bool(cls._processes)
        has_updaters = bool(cls._graph_memory_enabled)
        
        if not has_processes and not has_updaters:
            return  # 没have需want清理ofcontent，静默return
        
        logger.info("in progress清理所havesimulation进程...")
        
        # 首firststop所havegraph记忆update器（stop_all 内部will打印log）
        try:
            ZepGraphMemoryManager.stop_all()
        except Exception as e:
            logger.error(f"stopgraph记忆update器failed: {e}")
        cls._graph_memory_enabled.clear()
        
        # 复制dictionary以避免in迭代时modify
        processes = list(cls._processes.items())
        
        for simulation_id, process in processes:
            try:
                if process.poll() is None:  # 进程仍inrunning
                    logger.info(f"终止simulation进程: {simulation_id}, pid={process.pid}")
                    
                    try:
                        # use进程组终止（package括所have子进程）
                        pgid = os.getpgid(process.pid)
                        os.killpg(pgid, signal.SIGTERM)
                        
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            logger.warning(f"进程组notresponse SIGTERM，forced终止: {simulation_id}")
                            os.killpg(pgid, signal.SIGKILL)
                            process.wait(timeout=5)
                            
                    except (ProcessLookupError, OSError):
                        # 进程 can canalready经not存in，尝试直接终止
                        try:
                            process.terminate()
                            process.wait(timeout=3)
                        except Exception:
                            process.kill()
                    
                    # update run_state.json
                    state = cls.get_run_state(simulation_id)
                    if state:
                        state.runner_status = RunnerStatus.STOPPED
                        state.twitter_running = False
                        state.reddit_running = False
                        state.completed_at = datetime.now().isoformat()
                        state.error = "service器关闭，simulation被终止"
                        cls._save_run_state(state)
                    
                    # 同时update state.json， will status设for stopped
                    try:
                        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
                        state_file = os.path.join(sim_dir, "state.json")
                        logger.info(f"尝试update state.json: {state_file}")
                        if os.path.exists(state_file):
                            with open(state_file, 'r', encoding='utf-8') as f:
                                state_data = json.load(f)
                            state_data['status'] = 'stopped'
                            state_data['updated_at'] = datetime.now().isoformat()
                            with open(state_file, 'w', encoding='utf-8') as f:
                                json.dump(state_data, f, indent=2, ensure_ascii=False)
                            logger.info(f"alreadyupdate state.json statusfor stopped: {simulation_id}")
                        else:
                            logger.warning(f"state.json not存in: {state_file}")
                    except Exception as state_err:
                        logger.warning(f"update state.json failed: {simulation_id}, error={state_err}")
                        
            except Exception as e:
                logger.error(f"清理进程failed: {simulation_id}, error={e}")
        
        # 清理file句柄
        for simulation_id, file_handle in list(cls._stdout_files.items()):
            try:
                if file_handle:
                    file_handle.close()
            except Exception:
                pass
        cls._stdout_files.clear()
        
        for simulation_id, file_handle in list(cls._stderr_files.items()):
            try:
                if file_handle:
                    file_handle.close()
            except Exception:
                pass
        cls._stderr_files.clear()
        
        # 清理内存 ofstatus
        cls._processes.clear()
        cls._action_queues.clear()
        
        logger.info("simulation进程清理completed")
    
    @classmethod
    def register_cleanup(cls):
        """
        注册清理function
        
        in Flask 应use启动时call，确保service器关闭时清理所havesimulation进程
        """
        global _cleanup_registered
        
        if _cleanup_registered:
            return
        
        # Flask debug mode下，只in reloader 子进程 注册清理（实际running应useof进程）
        # WERKZEUG_RUN_MAIN=true expressis reloader 子进程
        # ifnotis debug mode，则没havethisenvironmentvariable，also需want注册
        is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
        is_debug_mode = os.environ.get('FLASK_DEBUG') == '1' or os.environ.get('WERKZEUG_RUN_MAIN') is not None
        
        # in debug mode下，只in reloader 子进程 注册；非 debug mode下始终注册
        if is_debug_mode and not is_reloader_process:
            _cleanup_registered = True  # 标记already registered，防止子进程再attempts
            return
        
        # save原haveof信号processing器
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)
        
        def cleanup_handler(signum=None, frame=None):
            """信号processing器：first清理simulation进程，再call原process器"""
            # 只haveinhave进程需want清理时才打印log
            if cls._processes or cls._graph_memory_enabled:
                logger.info(f"收到信号 {signum}，start清理...")
            cls.cleanup_all_simulations()
            
            # call原haveof信号processing器，让 Flask 正常退出
            if signum == signal.SIGINT and callable(original_sigint):
                original_sigint(signum, frame)
            elif signum == signal.SIGTERM and callable(original_sigterm):
                original_sigterm(signum, frame)
            else:
                # if原processing器not can call（such as SIG_DFL），则use默认行for
                raise KeyboardInterrupt
        
        # 注册 atexit processing器（作for备use）
        atexit.register(cls.cleanup_all_simulations)
        
        # 注册信号processing器（仅in主线程 ）
        try:
            # SIGTERM: kill 命令默认信号
            signal.signal(signal.SIGTERM, cleanup_handler)
            # SIGINT: Ctrl+C
            signal.signal(signal.SIGINT, cleanup_handler)
        except ValueError:
            # notin主线程 ，只canuse atexit
            logger.warning("无法注册信号processing器（notin主线程），仅use atexit")
        
        _cleanup_registered = True
    
    @classmethod
    def get_running_simulations(cls) -> List[str]:
        """
        get所have正inrunningofsimulationIDlist
        """
        running = []
        for sim_id, process in cls._processes.items():
            if process.poll() is None:
                running.append(sim_id)
        return running
    
    # ============== Interview function ==============
    
    @classmethod
    def check_env_alive(cls, simulation_id: str) -> bool:
        """
        checksimulation环境whether to存活（canreceiveInterview命令）

        Args:
            simulation_id: simulationID

        Returns:
            True express环境存活，False express环境 already 关闭
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            return False

        ipc_client = SimulationIPCClient(sim_dir)
        return ipc_client.check_env_alive()

    @classmethod
    def get_env_status_detail(cls, simulation_id: str) -> Dict[str, Any]:
        """
        getsimulation环境ofdetailedstatusinformation

        Args:
            simulation_id: simulationID

        Returns:
            status详情dictionary，contains status, twitter_available, reddit_available, timestamp
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        status_file = os.path.join(sim_dir, "env_status.json")
        
        default_status = {
            "status": "stopped",
            "twitter_available": False,
            "reddit_available": False,
            "timestamp": None
        }
        
        if not os.path.exists(status_file):
            return default_status
        
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                status = json.load(f)
            return {
                "status": status.get("status", "stopped"),
                "twitter_available": status.get("twitter_available", False),
                "reddit_available": status.get("reddit_available", False),
                "timestamp": status.get("timestamp")
            }
        except (json.JSONDecodeError, OSError):
            return default_status

    @classmethod
    def interview_agent(
        cls,
        simulation_id: str,
        agent_id: int,
        prompt: str,
        platform: str = None,
        timeout: float = 60.0
    ) -> Dict[str, Any]:
        """
        采访单Agent

        Args:
            simulation_id: simulationID
            agent_id: Agent ID
            prompt: 采访问题
            platform: 指定平台（ can 选）
                - "twitter": 只采访Twitter平台
                - "reddit": 只采访Reddit平台
                - None: 双平台simulation时同时采访两平台，return整合result
            timeout: timeouttime（秒）

        Returns:
            采访resultdictionary

        Raises:
            ValueError: simulationnot存in or 环境 not running
            TimeoutError: etc待responsetimeout
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"simulationnot存in: {simulation_id}")

        ipc_client = SimulationIPCClient(sim_dir)

        if not ipc_client.check_env_alive():
            raise ValueError(f"simulationenvironmentnotrunning or already关闭，无法executeInterview: {simulation_id}")

        logger.info(f"sendInterview命令: simulation_id={simulation_id}, agent_id={agent_id}, platform={platform}")

        response = ipc_client.send_interview(
            agent_id=agent_id,
            prompt=prompt,
            platform=platform,
            timeout=timeout
        )

        if response.status.value == "completed":
            return {
                "success": True,
                "agent_id": agent_id,
                "prompt": prompt,
                "result": response.result,
                "timestamp": response.timestamp
            }
        else:
            return {
                "success": False,
                "agent_id": agent_id,
                "prompt": prompt,
                "error": response.error,
                "timestamp": response.timestamp
            }
    
    @classmethod
    def interview_agents_batch(
        cls,
        simulation_id: str,
        interviews: List[Dict[str, Any]],
        platform: str = None,
        timeout: float = 120.0
    ) -> Dict[str, Any]:
        """
        批量采访多Agent

        Args:
            simulation_id: simulationID
            interviews: 采访list，每元素contains {"agent_id": int, "prompt": str, "platform": str( can 选)}
            platform: 默认平台（ can 选，will被每采访项ofplatform覆盖）
                - "twitter": 默认只采访Twitter平台
                - "reddit": 默认只采访Reddit平台
                - None: 双平台simulation时每Agent同时采访两平台
            timeout: timeouttime（秒）

        Returns:
            批量采访resultdictionary

        Raises:
            ValueError: simulationnot存in or 环境 not running
            TimeoutError: etc待responsetimeout
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"simulationnot存in: {simulation_id}")

        ipc_client = SimulationIPCClient(sim_dir)

        if not ipc_client.check_env_alive():
            raise ValueError(f"simulationenvironmentnotrunning or already关闭，无法executeInterview: {simulation_id}")

        logger.info(f"send批量Interview命令: simulation_id={simulation_id}, count={len(interviews)}, platform={platform}")

        response = ipc_client.send_batch_interview(
            interviews=interviews,
            platform=platform,
            timeout=timeout
        )

        if response.status.value == "completed":
            return {
                "success": True,
                "interviews_count": len(interviews),
                "result": response.result,
                "timestamp": response.timestamp
            }
        else:
            return {
                "success": False,
                "interviews_count": len(interviews),
                "error": response.error,
                "timestamp": response.timestamp
            }
    
    @classmethod
    def interview_all_agents(
        cls,
        simulation_id: str,
        prompt: str,
        platform: str = None,
        timeout: float = 180.0
    ) -> Dict[str, Any]:
        """
        采访所haveAgent（全局采访）

        use相同of问题采访simulation of所haveAgent

        Args:
            simulation_id: simulationID
            prompt: 采访问题（所haveAgentuse相同问题）
            platform: 指定平台（ can 选）
                - "twitter": 只采访Twitter平台
                - "reddit": 只采访Reddit平台
                - None: 双平台simulation时每Agent同时采访两平台
            timeout: timeouttime（秒）

        Returns:
            全局采访resultdictionary
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"simulationnot存in: {simulation_id}")

        # fromconfigurationfileget所haveAgentinformation
        config_path = os.path.join(sim_dir, "simulation_config.json")
        if not os.path.exists(config_path):
            raise ValueError(f"simulationconfigurationnot存in: {simulation_id}")

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        agent_configs = config.get("agent_configs", [])
        if not agent_configs:
            raise ValueError(f"simulationconfiguration 没haveAgent: {simulation_id}")

        # 构建批量采访list
        interviews = []
        for agent_config in agent_configs:
            agent_id = agent_config.get("agent_id")
            if agent_id is not None:
                interviews.append({
                    "agent_id": agent_id,
                    "prompt": prompt
                })

        logger.info(f"send全局Interview命令: simulation_id={simulation_id}, agent_count={len(interviews)}, platform={platform}")

        return cls.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=interviews,
            platform=platform,
            timeout=timeout
        )
    
    @classmethod
    def close_simulation_env(
        cls,
        simulation_id: str,
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        关闭simulation环境（andnotisstoppedsimulation进程）
        
        向simulationsend关闭环境命令，使其优雅退出etc待命令mode
        
        Args:
            simulation_id: simulationID
            timeout: timeouttime（秒）
            
        Returns:
            操作resultdictionary
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"simulationnot存in: {simulation_id}")
        
        ipc_client = SimulationIPCClient(sim_dir)
        
        if not ipc_client.check_env_alive():
            return {
                "success": True,
                "message": "environmentalready经关闭"
            }
        
        logger.info(f"send关闭environment命令: simulation_id={simulation_id}")
        
        try:
            response = ipc_client.send_close_env(timeout=timeout)
            
            return {
                "success": response.status.value == "completed",
                "message": "environment关闭命令alreadysend",
                "result": response.result,
                "timestamp": response.timestamp
            }
        except TimeoutError:
            # timeout can canis因forenvironmentin progress关闭
            return {
                "success": True,
                "message": "environment关闭命令alreadysend（waitingresponsetimeout，环境 can canin progress关闭）"
            }
    
    @classmethod
    def _get_interview_history_from_db(
        cls,
        db_path: str,
        platform_name: str,
        agent_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """from单count据librarygetInterviewhistory"""
        import sqlite3
        
        if not os.path.exists(db_path):
            return []
        
        results = []
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            if agent_id is not None:
                cursor.execute("""
                    SELECT user_id, information, created_at
                    FROM trace
                    WHERE action = 'interview' AND user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (agent_id, limit))
            else:
                cursor.execute("""
                    SELECT user_id, information, created_at
                    FROM trace
                    WHERE action = 'interview'
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))
            
            for user_id, information_json, created_at in cursor.fetchall():
                try:
                    information = json.loads(information_json) if information_json else {}
                except json.JSONDecodeError:
                    information = {"raw": information_json}
                
                results.append({
                    "agent_id": user_id,
                    "response": information.get("response", information),
                    "prompt": information.get("prompt", ""),
                    "timestamp": created_at,
                    "platform": platform_name
                })
            
            conn.close()
            
        except Exception as e:
            logger.error(f"readInterviewhistoryfailed ({platform_name}): {e}")
        
        return results

    @classmethod
    def get_interview_history(
        cls,
        simulation_id: str,
        platform: str = None,
        agent_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        getInterviewhistoryrecord（fromcount据libraryread）
        
        Args:
            simulation_id: simulationID
            platform: 平台type（reddit/twitter/None）
                - "reddit": 只getReddit平台ofhistory
                - "twitter": 只getTwitter平台ofhistory
                - None: get两平台of所havehistory
            agent_id: 指定Agent ID（ can 选，只get该Agentofhistory）
            limit: 每平台returnquantity限制
            
        Returns:
            Interviewhistoryrecordlist
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        
        results = []
        
        # 确定wantQueryofplatform
        if platform in ("reddit", "twitter"):
            platforms = [platform]
        else:
            # not指定platform时，Query两platform
            platforms = ["twitter", "reddit"]
        
        for p in platforms:
            db_path = os.path.join(sim_dir, f"{p}_simulation.db")
            platform_results = cls._get_interview_history_from_db(
                db_path=db_path,
                platform_name=p,
                agent_id=agent_id,
                limit=limit
            )
            results.extend(platform_results)
        
        # Bytime降序sort
        results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        # ifQuery多platform，限制total
        if len(platforms) > 1 and len(results) > limit:
            results = results[:limit]
        
        return results

