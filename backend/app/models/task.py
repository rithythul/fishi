"""
Task status management
Used for tracking long-running tasks (such as graph building)
"""

import uuid
from enum import Enum
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from datetime import datetime
import threading


class TaskStatus(str, Enum):
    """Task status enumeration"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    """Task data class"""
    task_id: str
    task_type: str
    status: TaskStatus
    created_at: str
    progress: int = 0                   # Progress percentage 0-100
    message: str = ""
    result: Optional[Dict] = None
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    progress_detail: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = asdict(self)
        result['status'] = self.status.value
        return result


class TaskManager:
    """
    Task manager
    Thread-safe task status management
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._tasks: Dict[str, Task] = {}
                    cls._instance._task_lock = threading.Lock()
        return cls._instance
    
    def create_task(
        self, 
        task_type: str,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Create new task
        
        Args:
            task_type: Task type
            metadata: Additional metadata
            
        Returns:
            Task ID
        """
        task_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        task = Task(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            created_at=now,
            metadata=metadata or {}
        )
        
        with self._task_lock:
            self._tasks[task_id] = task
        
        return task_id
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task"""
        with self._task_lock:
            return self._tasks.get(task_id)
    
    def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        result: Optional[Dict] = None,
        error: Optional[str] = None,
        progress_detail: Optional[Dict] = None
    ):
        """
        Update task status
        
        Args:
            task_id: Task ID
            status: New status
            progress: Progress
            message: Status message
            result: Result data
            error: Error message
            progress_detail: Detailed progress information
        """
        with self._task_lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            
            if status is not None:
                task.status = status
            if progress is not None:
                task.progress = progress
            if message is not None:
                task.message = message
            if result is not None:
                task.result = result
            if error is not None:
                task.error = error
            if progress_detail is not None:
                task.progress_detail = progress_detail
    
    def complete_task(self, task_id: str, result: Optional[Dict] = None):
        """Mark task as completed"""
        self.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            result=result
        )
    
    def fail_task(self, task_id: str, error: str):
        """Mark task as failed"""
        self.update_task(
            task_id,
            status=TaskStatus.FAILED,
            error=error
        )
    
    def list_tasks(self, task_type: Optional[str] = None) -> List[Task]:
        """List tasks"""
        with self._task_lock:
            tasks = list(self._tasks.values())
            if task_type:
                tasks = [t for t in tasks if t.task_type == task_type]
            return tasks
    
    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """Clean up old completed tasks"""
        now = datetime.now()
        to_delete = []
        
        with self._task_lock:
            for task_id, task in self._tasks.items():
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                    created = datetime.fromisoformat(task.created_at)
                    age = (now - created).total_seconds() / 3600
                    if age > max_age_hours:
                        to_delete.append(task_id)
            
            for task_id in to_delete:
                del self._tasks[task_id]
