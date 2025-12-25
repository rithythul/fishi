"""
graphrelatedAPI路由
useproject上下文机制，service端持久化status
"""

import os
import traceback
import threading
from flask import request, jsonify

from . import graph_bp
from ..config import Config
from ..services.ontology_generator import OntologyGenerator
from ..services.graph_builder import GraphBuilderService
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.logger import get_logger
from ..models.task import TaskManager, TaskStatus
from ..models.project import ProjectManager, ProjectStatus

# getlog器
logger = get_logger('mirofish.api')


def allowed_file(filename: str) -> bool:
    """checkfiles扩展名whether to允许"""
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    return ext in Config.ALLOWED_EXTENSIONS


# ============== project管理interface ==============

@graph_bp.route('/project/<project_id>', methods=['GET'])
def get_project(project_id: str):
    """
    getprojectdetails
    """
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": f"projectdoes not exist: {project_id}"
        }), 404
    
    return jsonify({
        "success": True,
        "data": project.to_dict()
    })


@graph_bp.route('/project/list', methods=['GET'])
def list_projects():
    """
    列出所haveproject
    """
    limit = request.args.get('limit', 50, type=int)
    projects = ProjectManager.list_projects(limit=limit)
    
    return jsonify({
        "success": True,
        "data": [p.to_dict() for p in projects],
        "count": len(projects)
    })


@graph_bp.route('/project/<project_id>', methods=['DELETE'])
def delete_project(project_id: str):
    """
    deleteproject
    """
    success = ProjectManager.delete_project(project_id)
    
    if not success:
        return jsonify({
            "success": False,
            "error": f"projectdoes not exist or deletefailed: {project_id}"
        }), 404
    
    return jsonify({
        "success": True,
        "message": f"projectalreadydelete: {project_id}"
    })


@graph_bp.route('/project/<project_id>/reset', methods=['POST'])
def reset_project(project_id: str):
    """
    重置projectstatus（use于重新构建graph）
    """
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": f"projectdoes not exist: {project_id}"
        }), 404
    
    # 重置到ontologyalreadygenerationstatus
    if project.ontology:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
    else:
        project.status = ProjectStatus.CREATED
    
    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    ProjectManager.save_project(project)
    
    return jsonify({
        "success": True,
        "message": f"projectalready重置: {project_id}",
        "data": project.to_dict()
    })


# ============== interface1：uploadfiles并generationontology ==============

@graph_bp.route('/ontology/generate', methods=['POST'])
def generate_ontology():
    """
    interface1：uploadfiles，分析generateontology definition
    
    request方式：multipart/form-data
    
    Args:
        files: uploadoffiles（PDF/MD/TXT）， can 多
        simulation_requirement: simulationrequirementdescription（必填）
        project_name: project名称（ can 选）
        additional_context: 额外say明（ can 选）
        
    Returns:
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "ontology": {
                    "entity_types": [...],
                    "edge_types": [...],
                    "analysis_summary": "..."
                },
                "files": [...],
                "total_text_length": 12345
            }
        }
    """
    try:
        logger.info("=== start generationontology definition ===")
        
        # getparameters
        simulation_requirement = request.form.get('simulation_requirement', '')
        project_name = request.form.get('project_name', 'Unnamed Project')
        additional_context = request.form.get('additional_context', '')
        
        logger.debug(f"project名称: {project_name}")
        logger.debug(f"simulationrequirement: {simulation_requirement[:100]}...")
        
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": "please providesimulationrequirementdescription (simulation_requirement)"
            }), 400
        
        # getuploadoffiles
        uploaded_files = request.files.getlist('files')
        if not uploaded_files or all(not f.filename for f in uploaded_files):
            return jsonify({
                "success": False,
                "error": "请至少upload一文档files"
            }), 400
        
        # created project
        project = ProjectManager.create_project(name=project_name)
        project.simulation_requirement = simulation_requirement
        logger.info(f"created project: {project.project_id}")
        
        # savefiles并Extract文本
        document_texts = []
        all_text = ""
        
        for file in uploaded_files:
            if file and file.filename and allowed_file(file.filename):
                # savefiles到projectdirectory
                file_information = ProjectManager.save_file_to_project(
                    project.project_id, 
                    file, 
                    file.filename
                )
                project.files.append({
                    "filename": file_information["original_filename"],
                    "size": file_information["size"]
                })
                
                # Extract文本
                text = FileParser.extract_text(file_information["path"])
                text = TextProcessor.preprocess_text(text)
                document_texts.append(text)
                all_text += f"\n\n=== {file_information['original_filename']} ===\n{text}"
        
        if not document_texts:
            ProjectManager.delete_project(project.project_id)
            return jsonify({
                "success": False,
                "error": "没havesuccessprocessing任何文档，请checkfilesformat"
            }), 400
        
        # saveExtractof文本
        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project.project_id, all_text)
        logger.info(f"text extractioncompleted, total {len(all_text)} characters")
        
        # generationontology
        logger.info("calling LLM to generateontology definition...")
        generator = OntologyGenerator()
        ontology = generator.generate(
            document_texts=document_texts,
            simulation_requirement=simulation_requirement,
            additional_context=additional_context if additional_context else None
        )
        
        # saveontology到project
        entity_count = len(ontology.get("entity_types", []))
        edge_count = len(ontology.get("edge_types", []))
        logger.info(f"ontologygeneration completed: {entity_count} entity types, {edge_count} relationship types")
        
        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", [])
        }
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        ProjectManager.save_project(project)
        logger.info(f"=== ontologygeneration completed === project ID: {project.project_id}")
        
        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id,
                "project_name": project.name,
                "ontology": project.ontology,
                "analysis_summary": project.analysis_summary,
                "files": project.files,
                "total_text_length": project.total_text_length
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== interface2：构建graph ==============

@graph_bp.route('/build', methods=['POST'])
def build_graph():
    """
    interface2：according toproject_id构建graph
    
    request（JSON）：
        {
            "project_id": "proj_xxxx",  // 必填，come自interface1
            "graph_name": "graph名称",    //  can 选
            "chunk_size": 500,          //  can 选，默认500
            "chunk_overlap": 50         //  can 选，默认50
        }
        
    Returns:
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "task_id": "task_xxxx",
                "message": "graph build taskalreadystart"
            }
        }
    """
    try:
        logger.info("=== start buildinggraph ===")
        
        # Check configuration
        errors = []
        if not Config.NEO4J_URI or not Config.NEO4J_PASSWORD:
            errors.append("Neo4j connection not configured (NEO4J_URI, NEO4J_PASSWORD)")
        if errors:
            logger.error(f"Configuration error: {errors}")
            return jsonify({
                "success": False,
                "error": "Configuration error: " + "; ".join(errors)
            }), 500
        
        # parserequest
        data = request.get_json() or {}
        project_id = data.get('project_id')
        logger.debug(f"requestparameters: project_id={project_id}")
        
        if not project_id:
            return jsonify({
                "success": False,
                "error": "please provide project_id"
            }), 400
        
        # getproject
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"projectdoes not exist: {project_id}"
            }), 404
        
        # checkprojectstatus
        force = data.get('force', False)  # forced重新构建
        
        if project.status == ProjectStatus.CREATED:
            return jsonify({
                "success": False,
                "error": "project尚notgenerationontology，please call first /ontology/generate"
            }), 400
        
        if project.status == ProjectStatus.GRAPH_BUILDING and not force:
            return jsonify({
                "success": False,
                "error": "graphin progress构建 ，请勿重复submit。如需forced重建，请添加 force: true",
                "task_id": project.graph_build_task_id
            }), 400
        
        # ifforced重建，重置status
        if force and project.status in [ProjectStatus.GRAPH_BUILDING, ProjectStatus.FAILED, ProjectStatus.GRAPH_COMPLETED]:
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            project.graph_id = None
            project.graph_build_task_id = None
            project.error = None
        
        # getconfiguration
        graph_name = data.get('graph_name', project.name or 'MiroFish Graph')
        chunk_size = data.get('chunk_size', project.chunk_size or Config.DEFAULT_CHUNK_SIZE)
        chunk_overlap = data.get('chunk_overlap', project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP)
        
        # updateprojectconfiguration
        project.chunk_size = chunk_size
        project.chunk_overlap = chunk_overlap
        
        # getExtractof文本
        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            return jsonify({
                "success": False,
                "error": "not找到Extractof文本content"
            }), 400
        
        # getontology
        ontology = project.ontology
        if not ontology:
            return jsonify({
                "success": False,
                "error": "not找到ontology definition"
            }), 400
        
        # create异步任务
        task_manager = TaskManager()
        task_id = task_manager.create_task(f"构建graph: {graph_name}")
        logger.info(f"created graph build task: task_id={task_id}, project_id={project_id}")
        
        # updateprojectstatus
        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        ProjectManager.save_project(project)
        
        # start后台任务
        def build_task():
            build_logger = get_logger('mirofish.build')
            try:
                build_logger.info(f"[{task_id}] start buildinggraph...")
                task_manager.update_task(
                    task_id, 
                    status=TaskStatus.PROCESSING,
                    message="initializationgraph构建service..."
                )
                
                # created graph构建service
                builder = GraphBuilderService()
                
                # 分blocks
                task_manager.update_task(
                    task_id,
                    message="文本分blocks ...",
                    progress=5
                )
                chunks = TextProcessor.split_text(
                    text, 
                    chunk_size=chunk_size, 
                    overlap=chunk_overlap
                )
                total_chunks = len(chunks)
                
                # created graph
                task_manager.update_task(
                    task_id,
                    message="createZepgraph...",
                    progress=10
                )
                graph_id = builder.create_graph(name=graph_name)
                
                # updateprojectofgraph_id
                project.graph_id = graph_id
                ProjectManager.save_project(project)
                
                # setontology
                task_manager.update_task(
                    task_id,
                    message="setontology definition...",
                    progress=15
                )
                builder.set_ontology(graph_id, ontology)
                
                # 添加文本（progress_callback 签名is (msg, progress_ratio)）
                def add_progress_callback(msg, progress_ratio):
                    progress = 15 + int(progress_ratio * 40)  # 15% - 55%
                    task_manager.update_task(
                        task_id,
                        message=msg,
                        progress=progress
                    )
                
                task_manager.update_task(
                    task_id,
                    message=f"start添加 {total_chunks} 文本blocks...",
                    progress=15
                )
                
                episode_uuids = builder.add_text_batches(
                    graph_id, 
                    chunks,
                    batch_size=3,
                    progress_callback=add_progress_callback
                )
                
                # waitingZepprocessingcompleted（query每episodeofprocessedstatus）
                task_manager.update_task(
                    task_id,
                    message="waitingZepprocessingcount据...",
                    progress=55
                )
                
                def wait_progress_callback(msg, progress_ratio):
                    progress = 55 + int(progress_ratio * 35)  # 55% - 90%
                    task_manager.update_task(
                        task_id,
                        message=msg,
                        progress=progress
                    )
                
                builder._wait_for_episodes(episode_uuids, wait_progress_callback)
                
                # getgraphcount据
                task_manager.update_task(
                    task_id,
                    message="getgraphcount据...",
                    progress=95
                )
                graph_data = builder.get_graph_data(graph_id)
                
                # updateprojectstatus
                project.status = ProjectStatus.GRAPH_COMPLETED
                ProjectManager.save_project(project)
                
                node_count = graph_data.get("node_count", 0)
                edge_count = graph_data.get("edge_count", 0)
                build_logger.info(f"[{task_id}] graph构建completed: graph_id={graph_id}, node={node_count}, edge={edge_count}")
                
                # completed
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    message="graph构建completed",
                    progress=100,
                    result={
                        "project_id": project_id,
                        "graph_id": graph_id,
                        "node_count": node_count,
                        "edge_count": edge_count,
                        "chunk_count": total_chunks
                    }
                )
                
            except Exception as e:
                # updateprojectstatusforfailed
                build_logger.error(f"[{task_id}] graph构建failed: {str(e)}")
                build_logger.debug(traceback.format_exc())
                
                project.status = ProjectStatus.FAILED
                project.error = str(e)
                ProjectManager.save_project(project)
                
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message=f"构建failed: {str(e)}",
                    error=traceback.format_exc()
                )
        
        # start后台线程
        thread = threading.Thread(target=build_task, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "data": {
                "project_id": project_id,
                "task_id": task_id,
                "message": "graph build taskalreadystart，请through /task/{task_id} query进度"
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 任务queryinterface ==============

@graph_bp.route('/task/<task_id>', methods=['GET'])
def get_task(task_id: str):
    """
    Query task status
    If task doesn't exist (404), check if it's a completed graph build task
    """
    task = TaskManager().get_task(task_id)
    
    if not task:
        # Task not found (likely due to backend restart)
        # Check if this is a graph build task by finding associated project
        project = None
        for p in ProjectManager.list_projects(limit=100):
            if p.graph_build_task_id == task_id:
                project = p
                break
        
        if project and project.status == ProjectStatus.GRAPH_COMPLETED:
            # Graph build is complete, return synthetic completed task
            return jsonify({
                "success": True,
                "data": {
                    "task_id": task_id,
                    "task_type": "Graph Build",
                    "status": "completed",
                    "progress": 100,
                    "message": "Graph build completed",
                    "result": {
                        "project_id": project.project_id,
                        "graph_id": project.graph_id
                    }
                }
            })
        
        # Task truly doesn't exist
        return jsonify({
            "success": False,
            "error": f"Task does not exist: {task_id}"
        }), 404
    
    return jsonify({
        "success": True,
        "data": task.to_dict()
    })


@graph_bp.route('/tasks', methods=['GET'])
def list_tasks():
    """
    列出所have任务
    """
    tasks = TaskManager().list_tasks()
    
    return jsonify({
        "success": True,
        "data": [t.to_dict() for t in tasks],
        "count": len(tasks)
    })


# ============== graphcount据interface ==============

@graph_bp.route('/data/<graph_id>', methods=['GET'])
def get_graph_data(graph_id: str):
    """
    getgraphcount据（nodesandedges）
    """
    try:
        if not Config.NEO4J_URI:
            return jsonify({
                "success": False,
                "error": "Neo4j connection not configured"
            }), 500
        
        builder = GraphBuilderService()
        graph_data = builder.get_graph_data(graph_id)
        
        return jsonify({
            "success": True,
            "data": graph_data
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@graph_bp.route('/delete/<graph_id>', methods=['DELETE'])
def delete_graph(graph_id: str):
    """
    deleteZepgraph
    """
    try:
        if not Config.NEO4J_URI:
            return jsonify({
                "success": False,
                "error": "Neo4j connection not configured"
            }), 500
        
        builder = GraphBuilderService()
        builder.delete_graph(graph_id)
        
        return jsonify({
            "success": True,
            "message": f"graphalreadydelete: {graph_id}"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
