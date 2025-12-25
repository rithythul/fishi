"""
Graph-related API routes
Uses project context mechanism with server-side persistent state
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

# Get logger
logger = get_logger('mirofish.api')


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    return ext in Config.ALLOWED_EXTENSIONS


# ============== Project Management API ==============

@graph_bp.route('/project/<project_id>', methods=['GET'])
def get_project(project_id: str):
    """
    Get project details
    """
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": f"Project does not exist: {project_id}"
        }), 404
    
    return jsonify({
        "success": True,
        "data": project.to_dict()
    })


@graph_bp.route('/project/<project_id>', methods=['DELETE'])
def delete_project(project_id: str):
    """
    Delete project
    """
    success = ProjectManager.delete_project(project_id)
    
    if not success:
        return jsonify({
            "success": False,
            "error": f"Project does not exist: {project_id}"
        }), 404
    
    return jsonify({
        "success": True,
        "message": "Project deleted successfully"
    })


@graph_bp.route('/projects', methods=['GET'])
def list_projects():
    """
    Get list of all projects
    """
    projects = ProjectManager.list_projects()
    
    return jsonify({
        "success": True,
        "data": {
            "projects": [p.to_dict() for p in projects],
            "total": len(projects)
        }
    })


# ============== API 1: Generate Ontology ==============

@graph_bp.route('/ontology/generate', methods=['POST'])
def generate_ontology():
    """
   API 1: Upload files and generate ontology definition
    
    Request (multipart/form-data):
        - files: One or more files (PDF, MD, TXT)
        - simulation_requirement: Simulation requirement description (required)
        - additional_context: Additional context (optional)
        - project_name: Project name (optional, default "Unnamed Project")
    
    Returns:
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "ontology": {
                    "entity_types": [...],
                    "edge_types": [...]
                },
                "analysis_summary": "...",
                "total_text_length": 12345
            }
        }
    
    Workflow:
        1. Check configuration
        2. Parse request parameters
        3. Create project
        4. Extract text from uploaded files
        5. Call LLM to generate ontology
        6. Save ontology to project
        7. Return ontology definition
    """
    try:
        logger.info("=== Starting ontology generation ===")
        
        # Get form data
        files = request.files.getlist('files')
        simulation_requirement = request.form.get('simulation_requirement', '').strip()
        additional_context = request.form.get('additional_context', '').strip()
        project_name = request.form.get('project_name', 'Unnamed Project').strip()
        
        logger.debug(f"Project name: {project_name}")
        logger.debug(f"Simulation requirement: {simulation_requirement}")
        logger.debug(f"Files count: {len(files)}")
        
        # Validate parameters
        if not files:
            return jsonify({
                "success": False,
                "error": "At least one file required"
            }), 400
        
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": "Simulation requirement is required"
            }), 400
        
        # Create project
        project = ProjectManager.create_project(name=project_name)
        project.simulation_requirement = simulation_requirement
        project.additional_context = additional_context if additional_context else None
        ProjectManager.save_project(project)
        logger.info(f"Created project: {project.project_id}")
        
        # Extract file text
        document_texts = []
        for file in files:
            if not file or not file.filename:
                continue
            
            if not allowed_file(file.filename):
                return jsonify({
                    "success": False,
                    "error": f"File type not supported: {file.filename}"
                }), 400
            
            try:
                # Save uploaded file temporarily
                temp_dir = Config.UPLOAD_FOLDER
                os.makedirs(temp_dir, exist_ok=True)
                temp_path = os.path.join(temp_dir, file.filename)
                file.save(temp_path)
                
                # Extract text using FileParser
                text = FileParser.extract_text(temp_path)
                
                # Clean up temp file
                os.remove(temp_path)
                
                if text:
                    document_texts.append(text)
                    logger.debug(f"Extracted text from {file.filename}: {len(text)} characters")
            except Exception as e:
                logger.error(f"Failed to extract text from {file.filename}: {e}")
                return jsonify({
                    "success": False,
                    "error": f"Failed to parse file {file.filename}: {str(e)}"
                }), 500
        
        if not document_texts:
            return jsonify({
                "success": False,
                "error": "No valid text extracted from uploaded files"
            }), 400
        
        # Save extracted text
        all_text = "\n\n".join(document_texts)
        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project.project_id, all_text)
        logger.info(f"Text extraction complete, total {len(all_text)} characters")
        
        # Generate ontology
        logger.info("Calling LLM to generate ontology definition...")
        try:
            generator = OntologyGenerator()
            ontology = generator.generate(
                document_texts=document_texts,
                simulation_requirement=simulation_requirement,
                additional_context=additional_context if additional_context else None
            )
        except Exception as e:
            logger.error(f"Ontology generation failed: {type(e).__name__}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise
        
        # Save ontology to project
        entity_count = len(ontology.get("entity_types", []))
        edge_count = len(ontology.get("edge_types", []))
        logger.info(f"Ontology generation complete: {entity_count} entity types, {edge_count} relationship types")
        
        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", [])
        }
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        ProjectManager.save_project(project)
        logger.info(f"=== Ontology generation complete === Project ID: {project.project_id}")
        
        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id,
                "ontology": project.ontology,
                "analysis_summary": project.analysis_summary,
                "total_text_length": project.total_text_length
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== API 2: Build Graph ==============

@graph_bp.route('/build', methods=['POST'])
def build_graph():
    """
    API 2: Build graph based on project_id
    
    Request (JSON):
        {
            "project_id": "proj_xxxx",  // Required, from API 1
            "graph_name": "Graph name",    // Optional
            "chunk_size": 500,          // Optional, default 500
            "chunk_overlap": 50         // Optional, default 50
        }
    
    Returns:
        {
            "success": true,
            "data": {
                "task_id": "task_xxxx"
            }
        }
    
    Workflow:
        1. Check configuration
        2. Validate project
        3. Get ontology from project
        4. Get text from project
        5. Create background task to build graph
        6. Return task_id (use /task/<task_id> to query progress)
    """
    try:
        logger.info("=== Starting graph build ===")
        
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
        
        # Parse request
        data = request.get_json()
        project_id = data.get('project_id', '').strip()
        graph_name = data.get('graph_name', '').strip() or "MiroFish Graph"
        chunk_size = int(data.get('chunk_size', Config.DEFAULT_CHUNK_SIZE))
        chunk_overlap = int(data.get('chunk_overlap', Config.DEFAULT_CHUNK_OVERLAP))
        
        logger.debug(f"Project ID: {project_id}")
        logger.debug(f"Graph name: {graph_name}")
        logger.debug(f"Chunk size: {chunk_size}, overlap: {chunk_overlap}")
        
        # Validate parameters
        if not project_id:
            return jsonify({
                "success": False,
                "error": "project_id is required"
            }), 400
        
        # Get project
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Project does not exist: {project_id}"
            }), 404
        
        # Check if ontology exists
        if not project.ontology or project.status != ProjectStatus.ONTOLOGY_GENERATED:
            return jsonify({
                "success": False,
                "error": "Project ontology not generated, please call /ontology/generate first"
            }), 400
        
        # Get extracted text
        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            return jsonify({
                "success": False,
                "error": "Project text not found, file may have been deleted"
            }), 404
        
        logger.info(f"Text length: {len(text)} characters")
        
        # Create task manager
        task_manager = TaskManager()
        
        # Start graph build in background thread
        def build_graph_worker(task_id: str):
            try:
                # Create graph builder service
                builder = GraphBuilderService()
                
                # Split text into chunks
                task_manager.update_task(
                    task_id,
                    progress=5,
                    message="Splitting text into chunks..."
                )
                chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
                logger.info(f"Text split into {len(chunks)} chunks")
                
                # Build graph asynchronously
                task_manager.update_task(
                    task_id,
                    progress=10,
                    message="Starting graph build..."
                )
                
                # Call graph builder's internal async method
                # The graph builder will update progress through task_manager
                graph_task_id = builder.build_graph_async(
                    text=text,
                    ontology=project.ontology,
                    graph_name=f"{project.name} - {graph_name}",
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap
                )
                
                # Wait for graph build to complete and forward progress
                while True:
                    graph_task = task_manager.get_task(graph_task_id)
                    if not graph_task:
                        break
                    
                    # Forward progress
                    task_manager.update_task(
                        task_id,
                        status=graph_task.status,
                        progress=graph_task.progress,
                        message=graph_task.message
                    )
                    
                    if graph_task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                        if graph_task.status == TaskStatus.COMPLETED:
                            # Update project with graph_id
                            project.graph_id = graph_task.result.get("graph_id")
                            project.status = ProjectStatus.GRAPH_BUILT
                            ProjectManager.save_project(project)
                            
                            task_manager.complete_task(
                                task_id,
                                result=graph_task.result
                            )
                        else:
                            task_manager.fail_task(task_id, graph_task.error)
                        break
                    
                    import time
                    time.sleep(1)
                
            except Exception as e:
                logger.error(f"Graph build failed: {str(e)}\n{traceback.format_exc()}")
                task_manager.fail_task(task_id, str(e))
        
        # Create task
        task_id = task_manager.create_task(
            task_type="graph_build",
            metadata={
                "project_id": project_id,
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap
            }
        )
        
        # Start background thread
        thread = threading.Thread(target=build_graph_worker, args=(task_id,))
        thread.daemon = True
        thread.start()
        
        logger.info(f"Graph build task created: {task_id}")
        
        return jsonify({
            "success": True,
            "data": {
                "task_id": task_id
            }
        })
        
    except Exception as e:
        logger.error(f"Graph build request failed: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Task Status Query ==============

@graph_bp.route('/task/<task_id>', methods=['GET'])
def get_task_status(task_id: str):
    """
    Query task status and progress
    
    Returns:
        {
            "success": true,
            "data": {
                "task_id": "task_xxxx",
                "status": "processing|completed|failed",
                "progress": 50,  // 0-100
                "message": "Current status message",
                "result": {},    // Only when completed
                "error": ""      // Only when failed
            }
        }
    """
    task_manager = TaskManager()
    task = task_manager.get_task(task_id)
    
    if not task:
        return jsonify({
            "success": False,
            "error": f"Task does not exist: {task_id}"
        }), 404
    
    return jsonify({
        "success": True,
        "data": task.to_dict()
    })


# ============== Get Graph Data ==============

@graph_bp.route('/data/<graph_id>', methods=['GET'])
def get_graph_data(graph_id: str):
    """
    Get graph data (nodes and edges)
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
        logger.error(f"Failed to get graph data: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Delete Graph ==============

@graph_bp.route('/delete/<graph_id>', methods=['DELETE'])
def delete_graph(graph_id: str):
    """
    Delete Neo4j graph
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
            "message": "Graph deleted successfully"
        })
        
    except Exception as e:
        logger.error(f"Failed to delete graph: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
