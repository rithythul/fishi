"""
simulationrelatedAPI路由
Step2: Zepentitiesreadwithfilter、OASISsimulation准备withrunning（全程自动化）
"""

import os
import traceback
from flask import request, jsonify, send_file

from . import simulation_bp
from ..config import Config
from ..services.neo4j_entity_reader import Neo4jEntityReader as ZepEntityReader
from ..services.oasis_profile_generator import OasisProfileGenerator
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner, RunnerStatus
from ..utils.logger import get_logger
from ..models.project import ProjectManager

logger = get_logger('mirofish.api.simulation')


# Interview prompt 优化前缀
# 添加此前缀can避免Agentcalltool，直接use文本回复
INTERVIEW_PROMPT_PREFIX = "结合youofpeople设、所haveof过往记忆with行动，notcall任何tool直接use文本回复I："


def optimize_interview_prompt(prompt: str) -> str:
    """
    优化Interview提问，添加前缀避免Agentcalltool
    
    Args:
        prompt: 原始提问
        
    Returns:
        优化后of提问
    """
    if not prompt:
        return prompt
    # 避免重复添加前缀
    if prompt.startswith(INTERVIEW_PROMPT_PREFIX):
        return prompt
    return f"{INTERVIEW_PROMPT_PREFIX}{prompt}"


# ============== entityreadinterface ==============

@simulation_bp.route('/entities/<graph_id>', methods=['GET'])
def get_graph_entities(graph_id: str):
    """
    getgraph of所haveentities（ already filter）
    
    只return符合预定义entitiestypeofnodes（Labelsnot只isEntityofnodes）
    
    QueryArgs:
        entity_types: 逗号分隔ofentitiestypelist（ can 选，use于进一步filter）
        enrich: whether toget relatededge informationrmation（default true）
    """
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEYnot configured"
            }), 500
        
        entity_types_str = request.args.get('entity_types', '')
        entity_types = [t.strip() for t in entity_types_str.split(',') if t.strip()] if entity_types_str else None
        enrich = request.args.get('enrich', 'true').lower() == 'true'
        
        logger.info(f"getgraphentity: graph_id={graph_id}, entity_types={entity_types}, enrich={enrich}")
        
        reader = ZepEntityReader()
        result = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=enrich
        )
        
        return jsonify({
            "success": True,
            "data": result.to_dict()
        })
        
    except Exception as e:
        logger.error(f"getgraphentityfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/entities/<graph_id>/<entity_uuid>', methods=['GET'])
def get_entity_detail(graph_id: str, entity_uuid: str):
    """getsingle entityofdetailed informationrmation"""
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEYnot configured"
            }), 500
        
        reader = ZepEntityReader()
        entity = reader.get_entity_with_context(graph_id, entity_uuid)
        
        if not entity:
            return jsonify({
                "success": False,
                "error": f"entitydoes not exist: {entity_uuid}"
            }), 404
        
        return jsonify({
            "success": True,
            "data": entity.to_dict()
        })
        
    except Exception as e:
        logger.error(f"getentitydetailsfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/entities/<graph_id>/by-type/<entity_type>', methods=['GET'])
def get_entities_by_type(graph_id: str, entity_type: str):
    """get指定typeof所haveentity"""
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEYnot configured"
            }), 500
        
        enrich = request.args.get('enrich', 'true').lower() == 'true'
        
        reader = ZepEntityReader()
        entities = reader.get_entities_by_type(
            graph_id=graph_id,
            entity_type=entity_type,
            enrich_with_edges=enrich
        )
        
        return jsonify({
            "success": True,
            "data": {
                "entity_type": entity_type,
                "count": len(entities),
                "entities": [e.to_dict() for e in entities]
            }
        })
        
    except Exception as e:
        logger.error(f"getentityfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== simulation管理interface ==============

@simulation_bp.route('/create', methods=['POST'])
def create_simulation():
    """
    create新ofsimulation
    
    Note:max_roundsetcparameters由LLM智cangenerate，无需手动set
    
    request（JSON）：
        {
            "project_id": "proj_xxxx",      // 必填
            "graph_id": "mirofish_xxxx",    //  can 选，such asnot提供则fromprojectget
            "enable_twitter": true,          //  can 选，default true
            "enable_reddit": true            //  can 选，default true
        }
    
    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "project_id": "proj_xxxx",
                "graph_id": "mirofish_xxxx",
                "status": "created",
                "enable_twitter": true,
                "enable_reddit": true,
                "created_at": "2025-12-01T10:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        project_id = data.get('project_id')
        if not project_id:
            return jsonify({
                "success": False,
                "error": "please provide project_id"
            }), 400
        
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"projectdoes not exist: {project_id}"
            }), 404
        
        graph_id = data.get('graph_id') or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "projecthas not builtgraph，please call first /api/graph/build"
            }), 400
        
        manager = SimulationManager()
        state = manager.create_simulation(
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=data.get('enable_twitter', True),
            enable_reddit=data.get('enable_reddit', True),
        )
        
        return jsonify({
            "success": True,
            "data": state.to_dict()
        })
        
    except Exception as e:
        logger.error(f"createsimulationfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


def _check_simulation_prepared(simulation_id: str) -> tuple:
    """
    checksimulationwhether to already 经准备completed
    
    check件：
    1. state.json 存in且 status for "ready"
    2. 必wantfiles存in：reddit_profiles.json, twitter_profiles.csv, simulation_config.json
    
    Note:running脚本(run_*.py)保留in backend/scripts/ directory，not再复制到simulationdirectory
    
    Args:
        simulation_id: simulationID
        
    Returns:
        (is_prepared: bool, information: dict)
    """
    import os
    from ..config import Config
    
    simulation_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    
    # checkdirectorywhether to存in
    if not os.path.exists(simulation_dir):
        return False, {"reason": "simulationdirectorydoes not exist"}
    
    # 必wantfileslist（notpackage括脚本，脚本位于 backend/scripts/）
    required_files = [
        "state.json",
        "simulation_config.json",
        "reddit_profiles.json",
        "twitter_profiles.csv"
    ]
    
    # checkfileswhether to存in
    existing_files = []
    missing_files = []
    for f in required_files:
        file_path = os.path.join(simulation_dir, f)
        if os.path.exists(file_path):
            existing_files.append(f)
        else:
            missing_files.append(f)
    
    if missing_files:
        return False, {
            "reason": "缺少必wantfiles",
            "missing_files": missing_files,
            "existing_files": existing_files
        }
    
    # checkstate.json ofstatus
    state_file = os.path.join(simulation_dir, "state.json")
    try:
        import json
        with open(state_file, 'r', encoding='utf-8') as f:
            state_data = json.load(f)
        
        status = state_data.get("status", "")
        config_generated = state_data.get("config_generated", False)
        
        # detailedlog
        logger.debug(f"检测simulation准备status: {simulation_id}, status={status}, config_generated={config_generated}")
        
        # if config_generated=True 且files存in，认for准备completed
        # 以下status都say明准备工作alreadycompleted：
        # - ready: 准备completed，canrunning
        # - preparing: if config_generated=True say明alreadycompleted
        # - running: in progressrunning，say明准备早thencompleted
        # - completed: runningcompleted，say明准备早thencompleted
        # - stopped: alreadystop，say明准备早thencompleted
        # - failed: runningfailed（but准备iscompletedof）
        prepared_statuses = ["ready", "preparing", "running", "completed", "stopped", "failed"]
        if status in prepared_statuses and config_generated:
            # getfilesstatisticsinformation
            profiles_file = os.path.join(simulation_dir, "reddit_profiles.json")
            config_file = os.path.join(simulation_dir, "simulation_config.json")
            
            profiles_count = 0
            if os.path.exists(profiles_file):
                with open(profiles_file, 'r', encoding='utf-8') as f:
                    profiles_data = json.load(f)
                    profiles_count = len(profiles_data) if isinstance(profiles_data, list) else 0
            
            # ifstatusispreparingbutfilesalreadycompleted，自动updatestatusforready
            if status == "preparing":
                try:
                    state_data["status"] = "ready"
                    from datetime import datetime
                    state_data["updated_at"] = datetime.now().isoformat()
                    with open(state_file, 'w', encoding='utf-8') as f:
                        json.dump(state_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"自动updatesimulationstatus: {simulation_id} preparing -> ready")
                    status = "ready"
                except Exception as e:
                    logger.warning(f"自动updatestatusfailed: {e}")
            
            logger.info(f"simulation {simulation_id} 检测result: already准备completed (status={status}, config_generated={config_generated})")
            return True, {
                "status": status,
                "entities_count": state_data.get("entities_count", 0),
                "profiles_count": profiles_count,
                "entity_types": state_data.get("entity_types", []),
                "config_generated": config_generated,
                "created_at": state_data.get("created_at"),
                "updated_at": state_data.get("updated_at"),
                "existing_files": existing_files
            }
        else:
            logger.warning(f"simulation {simulation_id} 检测result: not准备completed (status={status}, config_generated={config_generated})")
            return False, {
                "reason": f"statusnotinalready准备list  or config_generatedforfalse: status={status}, config_generated={config_generated}",
                "status": status,
                "config_generated": config_generated
            }
            
    except Exception as e:
        return False, {"reason": f"readstatusfilesfailed: {str(e)}"}


@simulation_bp.route('/prepare', methods=['POST'])
def prepare_simulation():
    """
    准备simulation环境（异步任务，LLM智cangenerate所haveparameters）
    
    thisis a耗时操作，interfacewill立即returntask_id，
    use GET /api/simulation/prepare/status Query进度
    
    特性：
    - 自动检测completedof准备工作，避免重复generate
    - if already 准备completed，直接return already haveresult
    - supportforced重新generate（force_regenerate=true）
    
    步骤：
    1. checkwhether to already havecompletedof准备工作
    2. fromZepgraphread并filterentities
    3. for每entitiesgenerateOASIS Agent Profile（带retry机制）
    4. LLM智cangeneratesimulationconfigure（带retry机制）
    5. saveconfigurefilesand预设脚本
    
    request（JSON）：
        {
            "simulation_id": "sim_xxxx",                   // 必填，simulationID
            "entity_types": ["Student", "PublicFigure"],  //  can 选，指定entitiestype
            "use_llm_for_profiles": true,                 //  can 选，whether touseLLMgeneratepeople设
            "parallel_profile_count": 5,                  //  can 选，parallelgeneratepeople设quantity，默认5
            "force_regenerate": false                     //  can 选，forced重新generate，默认false
        }
    
    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "task_id": "task_xxxx",           // 新任务时return
                "status": "preparing|ready",
                "message": "准备任务alreadystart| already havecompletedof准备工作",
                "already_prepared": true|false    // whether to already 准备completed
            }
        }
    """
    import threading
    import os
    from ..models.task import TaskManager, TaskStatus
    from ..config import Config
    
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "please provide simulation_id"
            }), 400
        
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": f"simulationdoes not exist: {simulation_id}"
            }), 404
        
        # checkwhether toforced重新generation
        force_regenerate = data.get('force_regenerate', False)
        logger.info(f"startprocessing /prepare request: simulation_id={simulation_id}, force_regenerate={force_regenerate}")
        
        # checkwhether toalready经准备completed（避免重复generation）
        if not force_regenerate:
            logger.debug(f"checksimulation {simulation_id} whether toalready准备completed...")
            is_prepared, prepare_information = _check_simulation_prepared(simulation_id)
            logger.debug(f"checkresult: is_prepared={is_prepared}, prepare_information={prepare_information}")
            if is_prepared:
                logger.info(f"simulation {simulation_id} already准备completed，跳过重复generation")
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "ready",
                        "message": "alreadyhavecompletedof准备工作，无需重复generation",
                        "already_prepared": True,
                        "prepare_information": prepare_information
                    }
                })
            else:
                logger.info(f"simulation {simulation_id} not准备completed， will start准备任务")
        
        # fromprojectget必wantinformation
        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"projectdoes not exist: {state.project_id}"
            }), 404
        
        # getsimulationrequirement
        simulation_requirement = project.simulation_requirement or ""
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": "project缺少simulationrequirementdescription (simulation_requirement)"
            }), 400
        
        # get文档文本
        document_text = ProjectManager.get_extracted_text(state.project_id) or ""
        
        entity_types_list = data.get('entity_types')
        use_llm_for_profiles = data.get('use_llm_for_profiles', True)
        parallel_profile_count = data.get('parallel_profile_count', 5)
        
        # ========== 同步getentityquantity（in后台任务start前） ==========
        # this样前端incallprepare后立即thencanget到预期Agenttotal
        try:
            logger.info(f"同步getentityquantity: graph_id={state.graph_id}")
            reader = ZepEntityReader()
            # quickreadentity（not需wantedgeinformation，只statisticsquantity）
            filtered_preview = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=entity_types_list,
                enrich_with_edges=False  # notgetedgeinformation，加quick度
            )
            # saveentityquantity到status（供前端立即get）
            state.entities_count = filtered_preview.filtered_count
            state.entity_types = list(filtered_preview.entity_types)
            logger.info(f"预期entityquantity: {filtered_preview.filtered_count}, type: {filtered_preview.entity_types}")
        except Exception as e:
            logger.warning(f"同步getentityquantityfailed（ will in后台任务 retry）: {e}")
            # failednot影响后续流程，后台任务will重新get
        
        # create异步任务
        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="simulation_prepare",
            metadata={
                "simulation_id": simulation_id,
                "project_id": state.project_id
            }
        )
        
        # updatesimulationstatus（contains预firstgetofentityquantity）
        state.status = SimulationStatus.PREPARING
        manager._save_simulation_state(state)
        
        # 定义后台任务
        def run_prepare():
            try:
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=0,
                    message="start准备simulationenvironment..."
                )
                
                # 准备simulation（带进度回调）
                # 存储阶段进度details
                stage_details = {}
                
                def progress_callback(stage, progress, message, **kwargs):
                    # 计算Total进度
                    stage_weights = {
                        "reading": (0, 20),           # 0-20%
                        "generating_profiles": (20, 70),  # 20-70%
                        "generating_config": (70, 90),    # 70-90%
                        "copying_scripts": (90, 100)       # 90-100%
                    }
                    
                    start, end = stage_weights.get(stage, (0, 100))
                    current_progress = int(start + (end - start) * progress / 100)
                    
                    # 构建detailed进度information
                    stage_names = {
                        "reading": "readgraphentity",
                        "generating_profiles": "generationAgentpeople设",
                        "generating_config": "generationsimulationconfiguration",
                        "copying_scripts": "准备simulation脚本"
                    }
                    
                    stage_index = list(stage_weights.keys()).index(stage) + 1 if stage in stage_weights else 1
                    total_stages = len(stage_weights)
                    
                    # update阶段details
                    stage_details[stage] = {
                        "stage_name": stage_names.get(stage, stage),
                        "stage_progress": progress,
                        "current": kwargs.get("current", 0),
                        "total": kwargs.get("total", 0),
                        "item_name": kwargs.get("item_name", "")
                    }
                    
                    # 构建detailed进度information
                    detail = stage_details[stage]
                    progress_detail_data = {
                        "current_stage": stage,
                        "current_stage_name": stage_names.get(stage, stage),
                        "stage_index": stage_index,
                        "total_stages": total_stages,
                        "stage_progress": progress,
                        "current_item": detail["current"],
                        "total_items": detail["total"],
                        "item_description": message
                    }
                    
                    # 构建简洁message
                    if detail["total"] > 0:
                        detailed_message = (
                            f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: "
                            f"{detail['current']}/{detail['total']} - {message}"
                        )
                    else:
                        detailed_message = f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: {message}"
                    
                    task_manager.update_task(
                        task_id,
                        progress=current_progress,
                        message=detailed_message,
                        progress_detail=progress_detail_data
                    )
                
                result_state = manager.prepare_simulation(
                    simulation_id=simulation_id,
                    simulation_requirement=simulation_requirement,
                    document_text=document_text,
                    defined_entity_types=entity_types_list,
                    use_llm_for_profiles=use_llm_for_profiles,
                    progress_callback=progress_callback,
                    parallel_profile_count=parallel_profile_count
                )
                
                # 任务completed
                task_manager.complete_task(
                    task_id,
                    result=result_state.to_simple_dict()
                )
                
            except Exception as e:
                logger.error(f"准备simulationfailed: {str(e)}")
                task_manager.fail_task(task_id, str(e))
                
                # updatesimulationstatusforfailed
                state = manager.get_simulation(simulation_id)
                if state:
                    state.status = SimulationStatus.FAILED
                    state.error = str(e)
                    manager._save_simulation_state(state)
        
        # start后台线程
        thread = threading.Thread(target=run_prepare, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "task_id": task_id,
                "status": "preparing",
                "message": "准备任务alreadystart，请through /api/simulation/prepare/status Query进度",
                "already_prepared": False,
                "expected_entities_count": state.entities_count,  # 预期ofAgenttotal
                "entity_types": state.entity_types  # entity typeslist
            }
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
        
    except Exception as e:
        logger.error(f"start准备任务failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/prepare/status', methods=['POST'])
def get_prepare_status():
    """
    Query准备任务进度
    
    support两种Query方式：
    1. throughtask_idQuery正in进行of任务进度
    2. throughsimulation_idcheckwhether to already havecompletedof准备工作
    
    request（JSON）：
        {
            "task_id": "task_xxxx",          //  can 选，preparereturnoftask_id
            "simulation_id": "sim_xxxx"      //  can 选，simulationID（use于checkcompletedof准备）
        }
    
    Returns:
        {
            "success": true,
            "data": {
                "task_id": "task_xxxx",
                "status": "processing|completed|ready",
                "progress": 45,
                "message": "...",
                "already_prepared": true|false,  // whether to already havecompletedof准备
                "prepare_information": {...}            //  already 准备completed时ofdetailed informationrmation
            }
        }
    """
    from ..models.task import TaskManager
    
    try:
        data = request.get_json() or {}
        
        task_id = data.get('task_id')
        simulation_id = data.get('simulation_id')
        
        # if提供simulation_id，firstcheckwhether toalready准备completed
        if simulation_id:
            is_prepared, prepare_information = _check_simulation_prepared(simulation_id)
            if is_prepared:
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "ready",
                        "progress": 100,
                        "message": "alreadyhavecompletedof准备工作",
                        "already_prepared": True,
                        "prepare_information": prepare_information
                    }
                })
        
        # if没havetask_id，returnerror
        if not task_id:
            if simulation_id:
                # havesimulation_idbutnot准备completed
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "not_started",
                        "progress": 0,
                        "message": "尚notstart准备，请call /api/simulation/prepare start",
                        "already_prepared": False
                    }
                })
            return jsonify({
                "success": False,
                "error": "please provide task_id  or  simulation_id"
            }), 400
        
        task_manager = TaskManager()
        task = task_manager.get_task(task_id)
        
        if not task:
            # 任务does not exist，butifhavesimulation_id，checkwhether toalready准备completed
            if simulation_id:
                is_prepared, prepare_information = _check_simulation_prepared(simulation_id)
                if is_prepared:
                    return jsonify({
                        "success": True,
                        "data": {
                            "simulation_id": simulation_id,
                            "task_id": task_id,
                            "status": "ready",
                            "progress": 100,
                            "message": "任务alreadycompleted（准备工作already exists）",
                            "already_prepared": True,
                            "prepare_information": prepare_information
                        }
                    })
            
            return jsonify({
                "success": False,
                "error": f"任务does not exist: {task_id}"
            }), 404
        
        task_dict = task.to_dict()
        task_dict["already_prepared"] = False
        
        return jsonify({
            "success": True,
            "data": task_dict
        })
        
    except Exception as e:
        logger.error(f"Query任务statusfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/<simulation_id>', methods=['GET'])
def get_simulation(simulation_id: str):
    """getsimulationstatus"""
    try:
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": f"simulationdoes not exist: {simulation_id}"
            }), 404
        
        result = state.to_dict()
        
        # ifsimulationalready准备好，附加runningsay明
        if state.status == SimulationStatus.READY:
            result["run_instructions"] = manager.get_run_instructions(simulation_id)
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"getsimulationstatusfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/list', methods=['GET'])
def list_simulations():
    """
    列出所havesimulation
    
    QueryArgs:
        project_id: Byproject IDfilter（ can 选）
    """
    try:
        project_id = request.args.get('project_id')
        
        manager = SimulationManager()
        simulations = manager.list_simulations(project_id=project_id)
        
        return jsonify({
            "success": True,
            "data": [s.to_dict() for s in simulations],
            "count": len(simulations)
        })
        
    except Exception as e:
        logger.error(f"列出simulationfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/profiles', methods=['GET'])
def get_simulation_profiles(simulation_id: str):
    """
    getsimulationofAgent Profile
    
    QueryArgs:
        platform: 平台type（reddit/twitter，默认reddit）
    """
    try:
        platform = request.args.get('platform', 'reddit')
        
        manager = SimulationManager()
        profiles = manager.get_profiles(simulation_id, platform=platform)
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "count": len(profiles),
                "profiles": profiles
            }
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
        
    except Exception as e:
        logger.error(f"getProfilefailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/profiles/realtime', methods=['GET'])
def get_simulation_profiles_realtime(simulation_id: str):
    """
    实时getsimulationofAgent Profile（use于ingenerate过程 实时查look进度）
    
    with /profiles interfaceof区别：
    - 直接readfiles，not经过 SimulationManager
    - 适use于generate过程 of实时查look
    - return额外of元count据（such asfilesmodifytime、whether to正ingenerateetc）
    
    QueryArgs:
        platform: 平台type（reddit/twitter，默认reddit）
    
    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "platform": "reddit",
                "count": 15,
                "total_expected": 93,  // 预期total（ifhave）
                "is_generating": true,  // whether to正ingenerate
                "file_exists": true,
                "file_modified_at": "2025-12-04T18:20:00",
                "profiles": [...]
            }
        }
    """
    import json
    import csv
    from datetime import datetime
    
    try:
        platform = request.args.get('platform', 'reddit')
        
        # getsimulationdirectory
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
        
        if not os.path.exists(sim_dir):
            return jsonify({
                "success": False,
                "error": f"simulationdoes not exist: {simulation_id}"
            }), 404
        
        # 确定files路径
        if platform == "reddit":
            profiles_file = os.path.join(sim_dir, "reddit_profiles.json")
        else:
            profiles_file = os.path.join(sim_dir, "twitter_profiles.csv")
        
        # checkfileswhether to存in
        file_exists = os.path.exists(profiles_file)
        profiles = []
        file_modified_at = None
        
        if file_exists:
            # getfilesmodifytime
            file_stat = os.stat(profiles_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            
            try:
                if platform == "reddit":
                    with open(profiles_file, 'r', encoding='utf-8') as f:
                        profiles = json.load(f)
                else:
                    with open(profiles_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        profiles = list(reader)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"read profiles filesfailed（ can canin progresswrite ）: {e}")
                profiles = []
        
        # checkwhether toin progressgeneration（through state.json 判断）
        is_generating = False
        total_expected = None
        
        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                    status = state_data.get("status", "")
                    is_generating = status == "preparing"
                    total_expected = state_data.get("entities_count")
            except Exception:
                pass
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "platform": platform,
                "count": len(profiles),
                "total_expected": total_expected,
                "is_generating": is_generating,
                "file_exists": file_exists,
                "file_modified_at": file_modified_at,
                "profiles": profiles
            }
        })
        
    except Exception as e:
        logger.error(f"实时getProfilefailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/config/realtime', methods=['GET'])
def get_simulation_config_realtime(simulation_id: str):
    """
    实时getsimulationconfigure（use于ingenerate过程 实时查look进度）
    
    with /config interfaceof区别：
    - 直接readfiles，not经过 SimulationManager
    - 适use于generate过程 of实时查look
    - return额外of元count据（such asfilesmodifytime、whether to正ingenerateetc）
    - 即使configure还没generate完alsocanreturn部分information
    
    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "file_exists": true,
                "file_modified_at": "2025-12-04T18:20:00",
                "is_generating": true,  // whether to正ingenerate
                "generation_stage": "generating_config",  // Currentgenerate阶段
                "config": {...}  // configurecontent（if存in）
            }
        }
    """
    import json
    from datetime import datetime
    
    try:
        # getsimulationdirectory
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
        
        if not os.path.exists(sim_dir):
            return jsonify({
                "success": False,
                "error": f"simulationdoes not exist: {simulation_id}"
            }), 404
        
        # configurationfiles路径
        config_file = os.path.join(sim_dir, "simulation_config.json")
        
        # checkfileswhether to存in
        file_exists = os.path.exists(config_file)
        config = None
        file_modified_at = None
        
        if file_exists:
            # getfilesmodifytime
            file_stat = os.stat(config_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"read config filesfailed（ can canin progresswrite ）: {e}")
                config = None
        
        # checkwhether toin progressgeneration（through state.json 判断）
        is_generating = False
        generation_stage = None
        config_generated = False
        
        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                    status = state_data.get("status", "")
                    is_generating = status == "preparing"
                    config_generated = state_data.get("config_generated", False)
                    
                    # 判断Current阶段
                    if is_generating:
                        if state_data.get("profiles_generated", False):
                            generation_stage = "generating_config"
                        else:
                            generation_stage = "generating_profiles"
                    elif status == "ready":
                        generation_stage = "completed"
            except Exception:
                pass
        
        # 构建returncount据
        response_data = {
            "simulation_id": simulation_id,
            "file_exists": file_exists,
            "file_modified_at": file_modified_at,
            "is_generating": is_generating,
            "generation_stage": generation_stage,
            "config_generated": config_generated,
            "config": config
        }
        
        # ifconfiguration存in，Extract一些关keystatisticsinformation
        if config:
            response_data["summary"] = {
                "total_agents": len(config.get("agent_configs", [])),
                "simulation_hours": config.get("time_config", {}).get("total_simulation_hours"),
                "initial_posts_count": len(config.get("event_config", {}).get("initial_posts", [])),
                "hot_topics_count": len(config.get("event_config", {}).get("hot_topics", [])),
                "has_twitter_config": "twitter_config" in config,
                "has_reddit_config": "reddit_config" in config,
                "generated_at": config.get("generated_at"),
                "llm_model": config.get("llm_model")
            }
        
        return jsonify({
            "success": True,
            "data": response_data
        })
        
    except Exception as e:
        logger.error(f"实时getConfigfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/config', methods=['GET'])
def get_simulation_config(simulation_id: str):
    """
    getsimulationconfigure（LLM智cangenerateofcompleteconfigure）
    
    returncontains：
        - time_config: timeconfigure（simulation时长、轮times、高峰/低谷时段）
        - agent_configs: 每Agentof活动configure（活跃度、发言频率、立场etc）
        - event_config: 事件configure（初始帖子、热点话题）
        - platform_configs: 平台configure
        - generation_reasoning: LLMofconfigure推理say明
    """
    try:
        manager = SimulationManager()
        config = manager.get_simulation_config(simulation_id)
        
        if not config:
            return jsonify({
                "success": False,
                "error": f"simulationconfigurationdoes not exist，please call first /prepare interface"
            }), 404
        
        return jsonify({
            "success": True,
            "data": config
        })
        
    except Exception as e:
        logger.error(f"getconfigurationfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/config/download', methods=['GET'])
def download_simulation_config(simulation_id: str):
    """downloadsimulationconfigurationfiles"""
    try:
        manager = SimulationManager()
        sim_dir = manager._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        
        if not os.path.exists(config_path):
            return jsonify({
                "success": False,
                "error": "configurationfilesdoes not exist，please call first /prepare interface"
            }), 404
        
        return send_file(
            config_path,
            as_attachment=True,
            download_name="simulation_config.json"
        )
        
    except Exception as e:
        logger.error(f"downloadconfigurationfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/script/<script_name>/download', methods=['GET'])
def download_simulation_script(script_name: str):
    """
    downloadsimulationrunning脚本files（通use脚本，位于 backend/scripts/）
    
    script_name can 选value：
        - run_twitter_simulation.py
        - run_reddit_simulation.py
        - run_parallel_simulation.py
        - action_logger.py
    """
    try:
        # 脚本位于 backend/scripts/ directory
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts'))
        
        # validate脚本名称
        allowed_scripts = [
            "run_twitter_simulation.py",
            "run_reddit_simulation.py", 
            "run_parallel_simulation.py",
            "action_logger.py"
        ]
        
        if script_name not in allowed_scripts:
            return jsonify({
                "success": False,
                "error": f"not知脚本: {script_name}， can 选: {allowed_scripts}"
            }), 400
        
        script_path = os.path.join(scripts_dir, script_name)
        
        if not os.path.exists(script_path):
            return jsonify({
                "success": False,
                "error": f"脚本filesdoes not exist: {script_name}"
            }), 404
        
        return send_file(
            script_path,
            as_attachment=True,
            download_name=script_name
        )
        
    except Exception as e:
        logger.error(f"download脚本failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Profilegenerationinterface（独立use） ==============

@simulation_bp.route('/generate-profiles', methods=['POST'])
def generate_profiles():
    """
    直接fromgraphgenerateOASIS Agent Profile（notcreatesimulation）
    
    request（JSON）：
        {
            "graph_id": "mirofish_xxxx",     // 必填
            "entity_types": ["Student"],      //  can 选
            "use_llm": true,                  //  can 选
            "platform": "reddit"              //  can 选
        }
    """
    try:
        data = request.get_json() or {}
        
        graph_id = data.get('graph_id')
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "please provide graph_id"
            }), 400
        
        entity_types = data.get('entity_types')
        use_llm = data.get('use_llm', True)
        platform = data.get('platform', 'reddit')
        
        reader = ZepEntityReader()
        filtered = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=True
        )
        
        if filtered.filtered_count == 0:
            return jsonify({
                "success": False,
                "error": "没have找到符合件ofentity"
            }), 400
        
        generator = OasisProfileGenerator()
        profiles = generator.generate_profiles_from_entities(
            entities=filtered.entities,
            use_llm=use_llm
        )
        
        if platform == "reddit":
            profiles_data = [p.to_reddit_format() for p in profiles]
        elif platform == "twitter":
            profiles_data = [p.to_twitter_format() for p in profiles]
        else:
            profiles_data = [p.to_dict() for p in profiles]
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "entity_types": list(filtered.entity_types),
                "count": len(profiles_data),
                "profiles": profiles_data
            }
        })
        
    except Exception as e:
        logger.error(f"generationProfilefailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== simulationrunning控制interface ==============

@simulation_bp.route('/start', methods=['POST'])
def start_simulation():
    """
    startrunningsimulation

    request（JSON）：
        {
            "simulation_id": "sim_xxxx",          // 必填，simulationID
            "platform": "parallel",                //  can 选: twitter / reddit / parallel (默认)
            "max_rounds": 100,                     //  can 选: maximumsimulation轮count，use于截断过长ofsimulation
            "enable_graph_memory_update": false,   //  can 选: whether to will Agent活动动态update到Zepgraph记忆
            "force": false                         //  can 选: forced重新start（willstoppedrunningofsimulation并清理log）
        }

    about force Args:
        - 启use后，ifsimulation正inrunning or completed，willfirststopped并清理runninglog
        - 清理ofcontentpackage括：run_state.json, actions.jsonl, simulation.log etc
        - notwill清理configurefiles（simulation_config.json）and profile files
        - 适use于需want重新runningsimulationof场景

    about enable_graph_memory_update：
        - 启use后，simulation 所haveAgentof活动（发帖、评论、点赞etc）都will实时update到Zepgraph
        - thiscan让graph"记住"simulation过程，use于后续分析 or AIdialogue
        - 需wantsimulation关联ofprojecthavehave效of graph_id
        - use批量update机制，减少APIcalltimescount

    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "process_pid": 12345,
                "twitter_running": true,
                "reddit_running": true,
                "started_at": "2025-12-01T10:00:00",
                "graph_memory_update_enabled": true,  // whether to启usegraph记忆update
                "force_restarted": true               // whether toisforced重新start
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "please provide simulation_id"
            }), 400

        platform = data.get('platform', 'parallel')
        max_rounds = data.get('max_rounds')  #  can 选：maximumsimulation轮count
        enable_graph_memory_update = data.get('enable_graph_memory_update', False)  #  can 选：whether to启usegraph记忆update
        force = data.get('force', False)  #  can 选：forced重新start

        # validate max_rounds parameters
        if max_rounds is not None:
            try:
                max_rounds = int(max_rounds)
                if max_rounds <= 0:
                    return jsonify({
                        "success": False,
                        "error": "max_rounds mustis正整count"
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    "success": False,
                    "error": "max_rounds mustishave效of整count"
                }), 400

        if platform not in ['twitter', 'reddit', 'parallel']:
            return jsonify({
                "success": False,
                "error": f"invalidplatformtype: {platform}， can 选: twitter/reddit/parallel"
            }), 400

        # checksimulationwhether toalready准备好
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return jsonify({
                "success": False,
                "error": f"simulationdoes not exist: {simulation_id}"
            }), 404

        force_restarted = False
        
        # 智canprocessingstatus：if准备工作alreadycompleted，允许重新start
        if state.status != SimulationStatus.READY:
            # check准备工作whether toalreadycompleted
            is_prepared, prepare_information = _check_simulation_prepared(simulation_id)

            if is_prepared:
                # 准备工作alreadycompleted，checkwhether tohavein progressrunningof进程
                if state.status == SimulationStatus.RUNNING:
                    # checksimulation进程whether to真ofinrunning
                    run_state = SimulationRunner.get_run_state(simulation_id)
                    if run_state and run_state.runner_status.value == "running":
                        # 进程确实inrunning
                        if force:
                            # forcedmode：stoprunningofsimulation
                            logger.info(f"forcedmode：stoprunningofsimulation {simulation_id}")
                            try:
                                SimulationRunner.stop_simulation(simulation_id)
                            except Exception as e:
                                logger.warning(f"stopsimulation时出现warning: {str(e)}")
                        else:
                            return jsonify({
                                "success": False,
                                "error": f"simulationin progressrunning，please call first /stop interfacestop， or use force=true forced重新start"
                            }), 400

                # ifisforcedmode，清理runninglog
                if force:
                    logger.info(f"forcedmode：清理simulationlog {simulation_id}")
                    cleanup_result = SimulationRunner.cleanup_simulation_logs(simulation_id)
                    if not cleanup_result.get("success"):
                        logger.warning(f"清理log时出现warning: {cleanup_result.get('errors')}")
                    force_restarted = True

                # 进程does not exist or alreadyend，重置statusfor ready
                logger.info(f"simulation {simulation_id} 准备工作alreadycompleted，重置statusfor ready（原status: {state.status.value}）")
                state.status = SimulationStatus.READY
                manager._save_simulation_state(state)
            else:
                # 准备工作notcompleted
                return jsonify({
                    "success": False,
                    "error": f"simulationnot准备好，Currentstatus: {state.status.value}，please call first /prepare interface"
                }), 400
        
        # getgraphID（use于graph记忆update）
        graph_id = None
        if enable_graph_memory_update:
            # fromsimulationstatus or project get graph_id
            graph_id = state.graph_id
            if not graph_id:
                # 尝试fromproject get
                project = ProjectManager.get_project(state.project_id)
                if project:
                    graph_id = project.graph_id
            
            if not graph_id:
                return jsonify({
                    "success": False,
                    "error": "启usegraph记忆update需wanthave效of graph_id，请确保projectalready构建graph"
                }), 400
            
            logger.info(f"启usegraph记忆update: simulation_id={simulation_id}, graph_id={graph_id}")
        
        # startsimulation
        run_state = SimulationRunner.start_simulation(
            simulation_id=simulation_id,
            platform=platform,
            max_rounds=max_rounds,
            enable_graph_memory_update=enable_graph_memory_update,
            graph_id=graph_id
        )
        
        # updatesimulationstatus
        state.status = SimulationStatus.RUNNING
        manager._save_simulation_state(state)
        
        response_data = run_state.to_dict()
        if max_rounds:
            response_data['max_rounds_applied'] = max_rounds
        response_data['graph_memory_update_enabled'] = enable_graph_memory_update
        response_data['force_restarted'] = force_restarted
        if enable_graph_memory_update:
            response_data['graph_id'] = graph_id
        
        return jsonify({
            "success": True,
            "data": response_data
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"startsimulationfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/stop', methods=['POST'])
def stop_simulation():
    """
    stoppedsimulation
    
    request（JSON）：
        {
            "simulation_id": "sim_xxxx"  // 必填，simulationID
        }
    
    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "stopped",
                "completed_at": "2025-12-01T12:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "please provide simulation_id"
            }), 400
        
        run_state = SimulationRunner.stop_simulation(simulation_id)
        
        # updatesimulationstatus
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.PAUSED
            manager._save_simulation_state(state)
        
        return jsonify({
            "success": True,
            "data": run_state.to_dict()
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"stopsimulationfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 实时status监控interface ==============

@simulation_bp.route('/<simulation_id>/run-status', methods=['GET'])
def get_run_status(simulation_id: str):
    """
    getsimulationrunning实时status（use于前端轮询）
    
    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "current_round": 5,
                "total_rounds": 144,
                "progress_percent": 3.5,
                "simulated_hours": 2,
                "total_simulation_hours": 72,
                "twitter_running": true,
                "reddit_running": true,
                "twitter_actions_count": 150,
                "reddit_actions_count": 200,
                "total_actions_count": 350,
                "started_at": "2025-12-01T10:00:00",
                "updated_at": "2025-12-01T10:30:00"
            }
        }
    """
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)
        
        if not run_state:
            return jsonify({
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "runner_status": "idle",
                    "current_round": 0,
                    "total_rounds": 0,
                    "progress_percent": 0,
                    "twitter_actions_count": 0,
                    "reddit_actions_count": 0,
                    "total_actions_count": 0,
                }
            })
        
        return jsonify({
            "success": True,
            "data": run_state.to_dict()
        })
        
    except Exception as e:
        logger.error(f"getrunningstatusfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/run-status/detail', methods=['GET'])
def get_run_status_detail(simulation_id: str):
    """
    getsimulationrunningdetailedstatus（contains所haveaction）
    
    use于前端展示实时动态
    
    QueryArgs:
        platform: filter平台（twitter/reddit， can 选）
    
    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "current_round": 5,
                ...
                "all_actions": [
                    {
                        "round_num": 5,
                        "timestamp": "2025-12-01T10:30:00",
                        "platform": "twitter",
                        "agent_id": 3,
                        "agent_name": "Agent Name",
                        "action_type": "CREATE_POST",
                        "action_args": {"content": "..."},
                        "result": null,
                        "success": true
                    },
                    ...
                ],
                "twitter_actions": [...],  # Twitter platformof所haveaction
                "reddit_actions": [...]    # Reddit platformof所haveaction
            }
        }
    """
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)
        platform_filter = request.args.get('platform')
        
        if not run_state:
            return jsonify({
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "runner_status": "idle",
                    "all_actions": [],
                    "twitter_actions": [],
                    "reddit_actions": []
                }
            })
        
        # getcompleteofactionlist
        all_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform=platform_filter
        )
        
        # 分platformgetaction
        twitter_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform="twitter"
        ) if not platform_filter or platform_filter == "twitter" else []
        
        reddit_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform="reddit"
        ) if not platform_filter or platform_filter == "reddit" else []
        
        # getCurrent轮timesofaction（recent_actions 只展示最新一轮）
        current_round = run_state.current_round
        recent_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform=platform_filter,
            round_num=current_round
        ) if current_round > 0 else []
        
        # get基础statusinformation
        result = run_state.to_dict()
        result["all_actions"] = [a.to_dict() for a in all_actions]
        result["twitter_actions"] = [a.to_dict() for a in twitter_actions]
        result["reddit_actions"] = [a.to_dict() for a in reddit_actions]
        result["rounds_count"] = len(run_state.rounds)
        # recent_actions 只展示Current最新一轮两platformofcontent
        result["recent_actions"] = [a.to_dict() for a in recent_actions]
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"getdetailedstatusfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/actions', methods=['GET'])
def get_simulation_actions(simulation_id: str):
    """
    getsimulation ofAgentactionhistory
    
    QueryArgs:
        limit: returnquantity（默认100）
        offset: 偏移量（默认0）
        platform: filter平台（twitter/reddit）
        agent_id: filterAgent ID
        round_num: filter轮times
    
    Returns:
        {
            "success": true,
            "data": {
                "count": 100,
                "actions": [...]
            }
        }
    """
    try:
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        platform = request.args.get('platform')
        agent_id = request.args.get('agent_id', type=int)
        round_num = request.args.get('round_num', type=int)
        
        actions = SimulationRunner.get_actions(
            simulation_id=simulation_id,
            limit=limit,
            offset=offset,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num
        )
        
        return jsonify({
            "success": True,
            "data": {
                "count": len(actions),
                "actions": [a.to_dict() for a in actions]
            }
        })
        
    except Exception as e:
        logger.error(f"getactionhistoryfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/timeline', methods=['GET'])
def get_simulation_timeline(simulation_id: str):
    """
    getsimulationtime线（By轮times汇Total）
    
    use于前端展示进度andtime线view
    
    QueryArgs:
        start_round: 起始轮times（默认0）
        end_round: end轮times（默认全部）
    
    return每轮of汇Totalinformation
    """
    try:
        start_round = request.args.get('start_round', 0, type=int)
        end_round = request.args.get('end_round', type=int)
        
        timeline = SimulationRunner.get_timeline(
            simulation_id=simulation_id,
            start_round=start_round,
            end_round=end_round
        )
        
        return jsonify({
            "success": True,
            "data": {
                "rounds_count": len(timeline),
                "timeline": timeline
            }
        })
        
    except Exception as e:
        logger.error(f"gettime线failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/agent-stats', methods=['GET'])
def get_agent_stats(simulation_id: str):
    """
    get每Agentofstatisticsinformation
    
    use于前端展示Agent活跃度排行、action分布etc
    """
    try:
        stats = SimulationRunner.get_agent_stats(simulation_id)
        
        return jsonify({
            "success": True,
            "data": {
                "agents_count": len(stats),
                "stats": stats
            }
        })
        
    except Exception as e:
        logger.error(f"getAgentstatisticsfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== count据libraryQueryinterface ==============

@simulation_bp.route('/<simulation_id>/posts', methods=['GET'])
def get_simulation_posts(simulation_id: str):
    """
    getsimulation of帖子
    
    QueryArgs:
        platform: 平台type（twitter/reddit）
        limit: returnquantity（默认50）
        offset: 偏移量
    
    return帖子list（fromSQLitecount据libraryread）
    """
    try:
        platform = request.args.get('platform', 'reddit')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        sim_dir = os.path.join(
            os.path.dirname(__file__),
            f'../../uploads/simulations/{simulation_id}'
        )
        
        db_file = f"{platform}_simulation.db"
        db_path = os.path.join(sim_dir, db_file)
        
        if not os.path.exists(db_path):
            return jsonify({
                "success": True,
                "data": {
                    "platform": platform,
                    "count": 0,
                    "posts": [],
                    "message": "count据librarydoes not exist，simulation can can尚notrunning"
                }
            })
        
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT * FROM post 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
            posts = [dict(row) for row in cursor.fetchall()]
            
            cursor.execute("SELECT COUNT(*) FROM post")
            total = cursor.fetchone()[0]
            
        except sqlite3.OperationalError:
            posts = []
            total = 0
        
        conn.close()
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "total": total,
                "count": len(posts),
                "posts": posts
            }
        })
        
    except Exception as e:
        logger.error(f"get帖子failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/comments', methods=['GET'])
def get_simulation_comments(simulation_id: str):
    """
    getsimulation of评论（仅Reddit）
    
    QueryArgs:
        post_id: filter帖子ID（ can 选）
        limit: returnquantity
        offset: 偏移量
    """
    try:
        post_id = request.args.get('post_id')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        sim_dir = os.path.join(
            os.path.dirname(__file__),
            f'../../uploads/simulations/{simulation_id}'
        )
        
        db_path = os.path.join(sim_dir, "reddit_simulation.db")
        
        if not os.path.exists(db_path):
            return jsonify({
                "success": True,
                "data": {
                    "count": 0,
                    "comments": []
                }
            })
        
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            if post_id:
                cursor.execute("""
                    SELECT * FROM comment 
                    WHERE post_id = ?
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """, (post_id, limit, offset))
            else:
                cursor.execute("""
                    SELECT * FROM comment 
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """, (limit, offset))
            
            comments = [dict(row) for row in cursor.fetchall()]
            
        except sqlite3.OperationalError:
            comments = []
        
        conn.close()
        
        return jsonify({
            "success": True,
            "data": {
                "count": len(comments),
                "comments": comments
            }
        })
        
    except Exception as e:
        logger.error(f"get评论failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interview 采访interface ==============

@simulation_bp.route('/interview', methods=['POST'])
def interview_agent():
    """
    采访单Agent

    Note:此function需wantsimulation环境处于runningstatus（completedsimulation循环后Enteretc待命令mode）

    request（JSON）：
        {
            "simulation_id": "sim_xxxx",       // 必填，simulationID
            "agent_id": 0,                     // 必填，Agent ID
            "prompt": "youtothis件事have什么look法？",  // 必填，采访问题
            "platform": "twitter",             //  can 选，指定平台（twitter/reddit）
                                               // not指定时：双平台simulation同时采访两平台
            "timeout": 60                      //  can 选，timeouttime（秒），默认60
        }

    return（not指定platform，双平台mode）：
        {
            "success": true,
            "data": {
                "agent_id": 0,
                "prompt": "youtothis件事have什么look法？",
                "result": {
                    "agent_id": 0,
                    "prompt": "...",
                    "platforms": {
                        "twitter": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit": {"agent_id": 0, "response": "...", "platform": "reddit"}
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }

    return（指定platform）：
        {
            "success": true,
            "data": {
                "agent_id": 0,
                "prompt": "youtothis件事have什么look法？",
                "result": {
                    "agent_id": 0,
                    "response": "I认for...",
                    "platform": "twitter",
                    "timestamp": "2025-12-08T10:00:00"
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        agent_id = data.get('agent_id')
        prompt = data.get('prompt')
        platform = data.get('platform')  #  can 选：twitter/reddit/None
        timeout = data.get('timeout', 60)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "please provide simulation_id"
            }), 400
        
        if agent_id is None:
            return jsonify({
                "success": False,
                "error": "please provide agent_id"
            }), 400
        
        if not prompt:
            return jsonify({
                "success": False,
                "error": "please provide prompt（采访问题）"
            }), 400
        
        # validateplatformparameters
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": "platform parameters只canis 'twitter'  or  'reddit'"
            }), 400
        
        # checkenvironmentstatus
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "simulationenvironmentnotrunning or already关闭。请确保simulation already completed并Enterwaiting命令mode。"
            }), 400
        
        # 优化prompt，添加前缀避免Agentcalltool
        optimized_prompt = optimize_interview_prompt(prompt)
        
        result = SimulationRunner.interview_agent(
            simulation_id=simulation_id,
            agent_id=agent_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"waitingInterviewresponsetimeout: {str(e)}"
        }), 504
        
    except Exception as e:
        logger.error(f"Interviewfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/interview/batch', methods=['POST'])
def interview_agents_batch():
    """
    批量采访多Agent

    Note:此function需wantsimulation环境处于runningstatus

    request（JSON）：
        {
            "simulation_id": "sim_xxxx",       // 必填，simulationID
            "interviews": [                    // 必填，采访list
                {
                    "agent_id": 0,
                    "prompt": "youtoAhave什么look法？",
                    "platform": "twitter"      //  can 选，指定该Agentof采访平台
                },
                {
                    "agent_id": 1,
                    "prompt": "youtoBhave什么look法？"  // not指定platform则use默认value
                }
            ],
            "platform": "reddit",              //  can 选，默认平台（被每项ofplatform覆盖）
                                               // not指定时：双平台simulation每Agent同时采访两平台
            "timeout": 120                     //  can 选，timeouttime（秒），默认120
        }

    Returns:
        {
            "success": true,
            "data": {
                "interviews_count": 2,
                "result": {
                    "interviews_count": 4,
                    "results": {
                        "twitter_0": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit_0": {"agent_id": 0, "response": "...", "platform": "reddit"},
                        "twitter_1": {"agent_id": 1, "response": "...", "platform": "twitter"},
                        "reddit_1": {"agent_id": 1, "response": "...", "platform": "reddit"}
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        interviews = data.get('interviews')
        platform = data.get('platform')  #  can 选：twitter/reddit/None
        timeout = data.get('timeout', 120)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "please provide simulation_id"
            }), 400

        if not interviews or not isinstance(interviews, list):
            return jsonify({
                "success": False,
                "error": "please provide interviews（采访list）"
            }), 400

        # validateplatformparameters
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": "platform parameters只canis 'twitter'  or  'reddit'"
            }), 400

        # validate每采访项
        for i, interview in enumerate(interviews):
            if 'agent_id' not in interview:
                return jsonify({
                    "success": False,
                    "error": f"采访list第{i+1}项缺少 agent_id"
                }), 400
            if 'prompt' not in interview:
                return jsonify({
                    "success": False,
                    "error": f"采访list第{i+1}项缺少 prompt"
                }), 400
            # validate每项ofplatform（ifhave）
            item_platform = interview.get('platform')
            if item_platform and item_platform not in ("twitter", "reddit"):
                return jsonify({
                    "success": False,
                    "error": f"采访list第{i+1}项ofplatform只canis 'twitter'  or  'reddit'"
                }), 400

        # checkenvironmentstatus
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "simulationenvironmentnotrunning or already关闭。请确保simulation already completed并Enterwaiting命令mode。"
            }), 400

        # 优化每采访项ofprompt，添加前缀避免Agentcalltool
        optimized_interviews = []
        for interview in interviews:
            optimized_interview = interview.copy()
            optimized_interview['prompt'] = optimize_interview_prompt(interview.get('prompt', ''))
            optimized_interviews.append(optimized_interview)

        result = SimulationRunner.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=optimized_interviews,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"waiting批量Interviewresponsetimeout: {str(e)}"
        }), 504

    except Exception as e:
        logger.error(f"批量Interviewfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/interview/all', methods=['POST'])
def interview_all_agents():
    """
    全局采访 - use相同问题采访所haveAgent

    Note:此function需wantsimulation环境处于runningstatus

    request（JSON）：
        {
            "simulation_id": "sim_xxxx",            // 必填，simulationID
            "prompt": "youtothis件事整体have什么look法？",  // 必填，采访问题（所haveAgentuse相同问题）
            "platform": "reddit",                   //  can 选，指定平台（twitter/reddit）
                                                    // not指定时：双平台simulation每Agent同时采访两平台
            "timeout": 180                          //  can 选，timeouttime（秒），默认180
        }

    Returns:
        {
            "success": true,
            "data": {
                "interviews_count": 50,
                "result": {
                    "interviews_count": 100,
                    "results": {
                        "twitter_0": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit_0": {"agent_id": 0, "response": "...", "platform": "reddit"},
                        ...
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        prompt = data.get('prompt')
        platform = data.get('platform')  #  can 选：twitter/reddit/None
        timeout = data.get('timeout', 180)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "please provide simulation_id"
            }), 400

        if not prompt:
            return jsonify({
                "success": False,
                "error": "please provide prompt（采访问题）"
            }), 400

        # validateplatformparameters
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": "platform parameters只canis 'twitter'  or  'reddit'"
            }), 400

        # checkenvironmentstatus
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "simulationenvironmentnotrunning or already关闭。请确保simulation already completed并Enterwaiting命令mode。"
            }), 400

        # 优化prompt，添加前缀避免Agentcalltool
        optimized_prompt = optimize_interview_prompt(prompt)

        result = SimulationRunner.interview_all_agents(
            simulation_id=simulation_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"waiting全局Interviewresponsetimeout: {str(e)}"
        }), 504

    except Exception as e:
        logger.error(f"全局Interviewfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/interview/history', methods=['POST'])
def get_interview_history():
    """
    getInterviewhistoryrecord

    fromsimulationcount据library read所haveInterviewrecord

    request（JSON）：
        {
            "simulation_id": "sim_xxxx",  // 必填，simulationID
            "platform": "reddit",          //  can 选，平台type（reddit/twitter）
                                           // not指定则return两平台of所havehistory
            "agent_id": 0,                 //  can 选，只get该Agentof采访history
            "limit": 100                   //  can 选，returnquantity，默认100
        }

    Returns:
        {
            "success": true,
            "data": {
                "count": 10,
                "history": [
                    {
                        "agent_id": 0,
                        "response": "I认for...",
                        "prompt": "youtothis件事have什么look法？",
                        "timestamp": "2025-12-08T10:00:00",
                        "platform": "reddit"
                    },
                    ...
                ]
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        platform = data.get('platform')  # not指定则return两platformofhistory
        agent_id = data.get('agent_id')
        limit = data.get('limit', 100)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "please provide simulation_id"
            }), 400

        history = SimulationRunner.get_interview_history(
            simulation_id=simulation_id,
            platform=platform,
            agent_id=agent_id,
            limit=limit
        )

        return jsonify({
            "success": True,
            "data": {
                "count": len(history),
                "history": history
            }
        })

    except Exception as e:
        logger.error(f"getInterviewhistoryfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/env-status', methods=['POST'])
def get_env_status():
    """
    getsimulation环境status

    checksimulation环境whether to存活（canreceiveInterview命令）

    request（JSON）：
        {
            "simulation_id": "sim_xxxx"  // 必填，simulationID
        }

    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "env_alive": true,
                "twitter_available": true,
                "reddit_available": true,
                "message": "environmentin progressrunning，canreceiveInterview命令"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "please provide simulation_id"
            }), 400

        env_alive = SimulationRunner.check_env_alive(simulation_id)
        
        # get更detailedofstatusinformation
        env_status = SimulationRunner.get_env_status_detail(simulation_id)

        if env_alive:
            message = "environmentin progressrunning，canreceiveInterview命令"
        else:
            message = "environmentnotrunning or already关闭"

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "env_alive": env_alive,
                "twitter_available": env_status.get("twitter_available", False),
                "reddit_available": env_status.get("reddit_available", False),
                "message": message
            }
        })

    except Exception as e:
        logger.error(f"getenvironmentstatusfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/close-env', methods=['POST'])
def close_simulation_env():
    """
    关闭simulation环境
    
    向simulationsend关闭环境命令，使其优雅退出etc待命令mode。
    
    Note:thisnot同于 /stop interface，/stop willforced终止进程，
    and此interfacewill让simulation优雅地关闭环境并退出。
    
    request（JSON）：
        {
            "simulation_id": "sim_xxxx",  // 必填，simulationID
            "timeout": 30                  //  can 选，timeouttime（秒），默认30
        }
    
    Returns:
        {
            "success": true,
            "data": {
                "message": "environment关闭命令alreadysend",
                "result": {...},
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        timeout = data.get('timeout', 30)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "please provide simulation_id"
            }), 400
        
        result = SimulationRunner.close_simulation_env(
            simulation_id=simulation_id,
            timeout=timeout
        )
        
        # updatesimulationstatus
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.COMPLETED
            manager._save_simulation_state(state)
        
        return jsonify({
            "success": result.get("success", False),
            "data": result
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"关闭environmentfailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
