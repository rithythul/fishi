"""
Project context management
Used for server-side persistent project status, avoiding passing large amounts of data between frontend interfaces
"""

import os
import json
import uuid
import shutil
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass, field, asdict


class ProjectStatus(str, Enum):
    """Project status enumeration"""
    CREATED = "created"                # Just created, files already uploaded
    ONTOLOGY_GENERATED = "ontology_generated"  # Ontology has been generated
    GRAPH_BUILDING = "graph_building"   # Graph building in progress
    GRAPH_BUILT = "graph_built"         # Graph building completed
    GRAPH_COMPLETED = "graph_completed" # Graph completed
    SIMULATION_READY = "simulation_ready"
    SIMULATION_RUNNING = "simulation_running"
    SIMULATION_COMPLETED = "simulation_completed"
    REPORT_GENERATING = "report_generating"
    REPORT_COMPLETED = "report_completed"


@dataclass
class Project:
    """Project data class"""
    # Basic information
    project_id: str
    name: str
    status: ProjectStatus
    created_at: str
    updated_at: str
    
    # Ontology information (populated after API 1 generation)
    ontology: Optional[Dict] = None
    analysis_summary: Optional[str] = None
    total_text_length: Optional[int] = None
    
    # Graph information (populated after API 2 completion)
    graph_id: Optional[str] = None
    node_count: Optional[int] = None
    edge_count: Optional[int] = None
    
    # Simulation requirement
    simulation_requirement: Optional[str] = None
    additional_context: Optional[str] = None
    
    # Simulation related
    simulation_id: Optional[str] = None
    simulation_config: Optional[Dict] = None
    
    # File related
    files: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = asdict(self)
        # Convert status to string
        result['status'] = self.status.value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Project':
        """Create from dictionary"""
        # Convert status string to enum
        if isinstance(data.get('status'), str):
            data['status'] = ProjectStatus(data['status'])
        return cls(**data)


class ProjectManager:
    """Project manager - responsible for project persistence and retrieval"""
    
    # Project storage root directory
    PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"
    
    @classmethod
    def _ensure_projects_dir(cls):
        """Ensure projects directory exists"""
        cls.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def _get_project_dir(cls, project_id: str) -> Path:
        """Get project directory path"""
        return cls.PROJECTS_DIR / project_id
    
    @classmethod
    def _get_project_metadata_path(cls, project_id: str) -> Path:
        """Get project metadata file path"""
        return cls._get_project_dir(project_id) / "metadata.json"
    
    @classmethod
    def _get_project_files_dir(cls, project_id: str) -> Path:
        """Get project files storage directory"""
        return cls._get_project_dir(project_id) / "files"
    
    @classmethod
    def _get_extracted_text_path(cls, project_id: str) -> Path:
        """Get extracted text storage path"""
        return cls._get_project_dir(project_id) / "extracted_text.txt"
    
    @classmethod
    def create_project(cls, name: str = "Unnamed Project") -> Project:
        """
        Create new project
        
        Args:
            name: Project name
            
        Returns:
            Newly created Project object
        """
        cls._ensure_projects_dir()
        
        project_id = f"proj_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        
        project = Project(
            project_id=project_id,
            name=name,
            status=ProjectStatus.CREATED,
            created_at=now,
            updated_at=now
        )
        
        # Create project directory structure
        project_dir = cls._get_project_dir(project_id)
        files_dir = cls._get_project_files_dir(project_id)
        os.makedirs(project_dir, exist_ok=True)
        os.makedirs(files_dir, exist_ok=True)
        
        # Save project metadata
        cls.save_project(project)
        
        return project
    
    @classmethod
    def save_project(cls, project: Project):
        """Save project metadata"""
        project.updated_at = datetime.now().isoformat()
        metadata_path = cls._get_project_metadata_path(project.project_id)
        
        # Ensure directory exists
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(project.to_dict(), f, ensure_ascii=False, indent=2)
    
    @classmethod
    def get_project(cls, project_id: str) -> Optional[Project]:
        """
        Get project
        
        Returns:
            Project object, returns None if not exists
        """
        metadata_path = cls._get_project_metadata_path(project_id)
        
        if not metadata_path.exists():
            return None
        
        with open(metadata_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return Project.from_dict(data)
    
    @classmethod
    def list_projects(cls, limit: int = 50) -> List[Project]:
        """
        List all projects
        
        Args:
            limit: Return quantity limit
            
        Returns:
            Project list, sorted by creation time descending
        """
        cls._ensure_projects_dir()
        
        projects = []
        for project_dir in cls.PROJECTS_DIR.iterdir():
            if project_dir.is_dir():
                project = cls.get_project(project_dir.name)
                if project:
                    projects.append(project)
        
        # Sort by creation time descending
        projects.sort(key=lambda p: p.created_at, reverse=True)
        
        return projects[:limit]
    
    @classmethod
    def delete_project(cls, project_id: str) -> bool:
        """
        Delete project and all its files
        """
        project_dir = cls._get_project_dir(project_id)
        
        if not project_dir.exists():
            return False
        
        # Delete entire project directory
        shutil.rmtree(project_dir)
        return True
    
    @classmethod
    def save_project_file(
        cls, 
        project_id: str, 
        file_content: bytes, 
        original_filename: str
    ) -> str:
        """
        Save uploaded file to project directory
        
        Args:
            project_id: Project ID
            file_content: File content
            original_filename: Original filename
            
        Returns:
            Saved file path
        """
        # Generate safe filename
        safe_filename = original_filename.replace(" ", "_")
        files_dir = cls._get_project_files_dir(project_id)
        files_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = files_dir / safe_filename
        
        # Check if file exists, add suffix if so
        counter = 1
        while file_path.exists():
            stem = Path(safe_filename).stem
            suffix = Path(safe_filename).suffix
            file_path = files_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        
        with open(file_path, 'wb') as f:
            f.write(file_content)
        
        return str(file_path)
    
    @classmethod
    def save_extracted_text(cls, project_id: str, text: str):
        """Save extracted text"""
        text_path = cls._get_extracted_text_path(project_id)
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(text)
    
    @classmethod
    def get_extracted_text(cls, project_id: str) -> Optional[str]:
        """Get extracted text"""
        text_path = cls._get_extracted_text_path(project_id)
        
        if not text_path.exists():
            return None
        
        with open(text_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    @classmethod
    def get_project_files(cls, project_id: str) -> List[str]:
        """Get all project file paths"""
        files_dir = cls._get_project_files_dir(project_id)
        
        if not files_dir.exists():
            return []
        
        return [str(f) for f in files_dir.iterdir() if f.is_file()]
