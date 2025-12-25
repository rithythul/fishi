"""
Neo4j Graph Memory Updater Service
Dynamically updates Neo4j graph with agent activities from simulation
"""

import os
import time
import threading
import json
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from queue import Queue, Empty

from ..config import Config
from ..utils.logger import get_logger
from .neo4j_service import Neo4jService
from .llm_entity_extractor import LLMEntityExtractor

logger = get_logger('fishi.neo4j_graph_memory_updater')


@dataclass
class AgentActivity:
    """Agent activity record"""
    platform: str           # twitter / reddit
    agent_id: int
    agent_name: str
    action_type: str        # CREATE_POST, LIKE_POST, etc.
    action_args: Dict[str, Any]
    round_num: int
    timestamp: str
    
    def to_episode_text(self) -> str:
        """
        Convert activity to text description for graph extraction
        
        Uses natural language description format for entity/relationship extraction
        """
        # Generate different descriptions for different action types
        action_descriptions = {
            "CREATE_POST": self._describe_create_post,
            "LIKE_POST": self._describe_like_post,
            "DISLIKE_POST": self._describe_dislike_post,
            "REPOST": self._describe_repost,
            "QUOTE_POST": self._describe_quote_post,
            "FOLLOW": self._describe_follow,
            "CREATE_COMMENT": self._describe_create_comment,
            "LIKE_COMMENT": self._describe_like_comment,
            "DISLIKE_COMMENT": self._describe_dislike_comment,
            "SEARCH_POSTS": self._describe_search,
            "SEARCH_USER": self._describe_search_user,
            "MUTE": self._describe_mute,
        }
        
        describe_func = action_descriptions.get(self.action_type, self._describe_generic)
        description = describe_func()
        
        # Return "agent name: activity description" format
        return f"{self.agent_name}: {description}"
    
    def _describe_create_post(self) -> str:
        content = self.action_args.get("content", "")
        if content:
            return f"published a post: '{content}'"
        return "published a post"
    
    def _describe_like_post(self) -> str:
        """Like post - includes post content and author info"""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if post_content and post_author:
            return f"liked {post_author}'s post: '{post_content}'"
        elif post_content:
            return f"liked a post: '{post_content}'"
        elif post_author:
            return f"liked a post by {post_author}"
        return "liked a post"
    
    def _describe_dislike_post(self) -> str:
        """Dislike post - includes post content and author info"""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if post_content and post_author:
            return f"disliked {post_author}'s post: '{post_content}'"
        elif post_content:
            return f"disliked a post: '{post_content}'"
        elif post_author:
            return f"disliked a post by {post_author}"
        return "disliked a post"
    
    def _describe_repost(self) -> str:
        """Repost - includes original content and author info"""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        
        if original_content and original_author:
            return f"reposted {original_author}'s post: '{original_content}'"
        elif original_content:
            return f"reposted a post: '{original_content}'"
        elif original_author:
            return f"reposted a post by {original_author}"
        return "reposted a post"
    
    def _describe_quote_post(self) -> str:
        """Quote post - includes original content, author info and quote comment"""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        quote_content = self.action_args.get("quote_content", "") or self.action_args.get("content", "")
        
        base = ""
        if original_content and original_author:
            base = f"quoted {original_author}'s post '{original_content}'"
        elif original_content:
            base = f"quoted a post '{original_content}'"
        elif original_author:
            base = f"quoted a post by {original_author}"
        else:
            base = "quoted a post"
        
        if quote_content:
            base += f", commenting: '{quote_content}'"
        return base
    
    def _describe_follow(self) -> str:
        """Follow user - includes target user name"""
        target_user_name = self.action_args.get("target_user_name", "")
        
        if target_user_name:
            return f"followed user '{target_user_name}'"
        return "followed a user"
    
    def _describe_create_comment(self) -> str:
        """Create comment - includes comment content and post info"""
        content = self.action_args.get("content", "")
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if content:
            if post_content and post_author:
                return f"commented on {post_author}'s post '{post_content}': '{content}'"
            elif post_content:
                return f"commented on post '{post_content}': '{content}'"
            elif post_author:
                return f"commented on {post_author}'s post: '{content}'"
            return f"commented: '{content}'"
        return "posted a comment"
    
    def _describe_like_comment(self) -> str:
        """Like comment - includes comment content and author info"""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        
        if comment_content and comment_author:
            return f"liked {comment_author}'s comment: '{comment_content}'"
        elif comment_content:
            return f"liked a comment: '{comment_content}'"
        elif comment_author:
            return f"liked a comment by {comment_author}"
        return "liked a comment"
    
    def _describe_dislike_comment(self) -> str:
        """Dislike comment - includes comment content and author info"""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        
        if comment_content and comment_author:
            return f"disliked {comment_author}'s comment: '{comment_content}'"
        elif comment_content:
            return f"disliked a comment: '{comment_content}'"
        elif comment_author:
            return f"disliked a comment by {comment_author}"
        return "disliked a comment"
    
    def _describe_search(self) -> str:
        """Search posts - includes search query"""
        query = self.action_args.get("query", "") or self.action_args.get("keyword", "")
        return f"searched for '{query}'" if query else "performed a search"
    
    def _describe_search_user(self) -> str:
        """Search user - includes search query"""
        query = self.action_args.get("query", "") or self.action_args.get("username", "")
        return f"searched for user '{query}'" if query else "searched for users"
    
    def _describe_mute(self) -> str:
        """Mute user - includes target user name"""
        target_user_name = self.action_args.get("target_user_name", "")
        
        if target_user_name:
            return f"muted user '{target_user_name}'"
        return "muted a user"
    
    def _describe_generic(self) -> str:
        # For unknown action types, generate generic description
        return f"performed {self.action_type} action"


class Neo4jGraphMemoryUpdater:
    """
    Neo4j Graph Memory Updater
    
    Monitors simulation action logs and updates Neo4j graph in real-time with agent activities.
    Groups by platform, batches activities and sends to Neo4j after accumulating BATCH_SIZE items.
    
    All meaningful actions are updated to Neo4j, with action_args containing full context:
    - Liked/disliked post content
    - Reposted/quoted post content
    - Followed/muted user names
    - Liked/disliked comment content
    """
    
    # Batch send size (how many activities to accumulate per platform before sending)
    BATCH_SIZE = 5
    
    # Send interval (seconds) to avoid request overload
    SEND_INTERVAL = 0.5
    
    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds
    
    def __init__(self, graph_id: str, api_key: Optional[str] = None):
        """
        Initialize updater
        
        Args:
            graph_id: Neo4j graph ID
            api_key: Not used (kept for API compatibility)
        """
        self.graph_id = graph_id
        
        # Initialize Neo4j service
        self.neo4j = Neo4jService()
        
        # Initialize LLM entity extractor
        self.entity_extractor = LLMEntityExtractor()
        
        # Activity queue
        self._activity_queue: Queue = Queue()
        
        # Platform-grouped activity buffers (each platform accumulates to BATCH_SIZE then sends)
        self._platform_buffers: Dict[str, List[AgentActivity]] = {
            'twitter': [],
            'reddit': [],
        }
        self._buffer_lock = threading.Lock()
        
        # Control flags
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        
        # Statistics
        self._total_activities = 0  # Activities actually added to queue
        self._total_sent = 0        # Batches successfully sent to Neo4j
        self._total_items_sent = 0  # Activities successfully sent to Neo4j
        self._failed_count = 0      # Failed batch sends
        self._skipped_count = 0     # Filtered activities (DO_NOTHING)
        
        logger.info(f"Neo4jGraphMemoryUpdater initialized: graph_id={graph_id}, batch_size={self.BATCH_SIZE}")
    
    def start(self):
        """Start background worker thread"""
        if self._running:
            return
        
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name=f"Neo4jMemoryUpdater-{self.graph_id[:8]}"
        )
        self._worker_thread.start()
        logger.info(f"Neo4jGraphMemoryUpdater started: graph_id={self.graph_id}")
    
    def stop(self):
        """Stop background worker thread"""
        self._running = False
        
        # Send remaining activities
        self._flush_remaining()
        
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10)
        
        logger.info(f"Neo4jGraphMemoryUpdater stopped: graph_id={self.graph_id}, "
                   f"total_activities={self._total_activities}, "
                   f"batches_sent={self._total_sent}, "
                   f"items_sent={self._total_items_sent}, "
                   f"failed={self._failed_count}, "
                   f"skipped={self._skipped_count}")
    
    def add_activity(self, activity: AgentActivity):
        """
        Add an agent activity to the queue
        
        All meaningful actions will be added to queue, including:
        - CREATE_POST (post)
        - CREATE_COMMENT (comment)
        - QUOTE_POST (quote post)
        - SEARCH_POSTS (search posts)
        - SEARCH_USER (search user)
        - LIKE_POST/DISLIKE_POST (like/dislike post)
        - REPOST (repost)
        - FOLLOW (follow)
        - MUTE (mute)
        - LIKE_COMMENT/DISLIKE_COMMENT (like/dislike comment)
        
        action_args will contain complete context info (post content, user names, etc.)
        
        Args:
            activity: Agent activity record
        """
        # Skip DO_NOTHING type activities
        if activity.action_type == "DO_NOTHING":
            self._skipped_count += 1
            return
        
        self._activity_queue.put(activity)
        self._total_activities += 1
        logger.debug(f"Added activity to queue: {activity.agent_name} - {activity.action_type}")
    
    def add_activity_from_dict(self, data: Dict[str, Any], platform: str):
        """
        Add activity from dictionary data
        
        Args:
            data: Dictionary data parsed from actions.jsonl
            platform: Platform name (twitter/reddit)
        """
        # Skip event type entries
        if "event_type" in data:
            return
        
        activity = AgentActivity(
            platform=platform,
            agent_id=data.get("agent_id", 0),
            agent_name=data.get("agent_name", ""),
            action_type=data.get("action_type", ""),
            action_args=data.get("action_args", {}),
            round_num=data.get("round", 0),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )
        
        self.add_activity(activity)
    
    def _worker_loop(self):
        """Background worker loop - batch sends activities to Neo4j by platform"""
        while self._running or not self._activity_queue.empty():
            try:
                # Try to get activity from queue (timeout 1 second)
                try:
                    activity = self._activity_queue.get(timeout=1)
                    
                    # Add activity to corresponding platform buffer
                    platform = activity.platform.lower()
                    with self._buffer_lock:
                        if platform not in self._platform_buffers:
                            self._platform_buffers[platform] = []
                        self._platform_buffers[platform].append(activity)
                        
                        # Check if platform has reached batch size
                        if len(self._platform_buffers[platform]) >= self.BATCH_SIZE:
                            batch = self._platform_buffers[platform][:self.BATCH_SIZE]
                            self._platform_buffers[platform] = self._platform_buffers[platform][self.BATCH_SIZE:]
                            # Release lock before sending
                            self._send_batch_activities(batch, platform)
                            # Send interval to avoid request overload
                            time.sleep(self.SEND_INTERVAL)
                    
                except Empty:
                    pass
                    
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                time.sleep(1)
    
    def _send_batch_activities(self, activities: List[AgentActivity], platform: str):
        """
        Batch send activities to Neo4j graph using LLM extraction
        
        Args:
            activities: Agent activity list
            platform: Platform name
        """
        if not activities:
            return
        
        # Combine multiple activities into one text, separated by newlines
        episode_texts = [activity.to_episode_text() for activity in activities]
        combined_text = "\n".join(episode_texts)
        
        # Extract entities using LLM
        agent_names = list(set(a.agent_name for a in activities))
        extraction = self.entity_extractor.extract_from_activity(
            combined_text,
            agent_name=agent_names[0] if agent_names else "Agent"
        )
        
        # Send with retry
        for attempt in range(self.MAX_RETRIES):
            try:
                # Add extracted entities and relationships to graph
                self._add_extraction_to_graph(extraction, activities)
                
                self._total_sent += 1
                self._total_items_sent += len(activities)
                logger.info(f"Successfully sent batch of {len(activities)} {platform} activities to graph {self.graph_id}")
                logger.debug(f"Batch content preview: {combined_text[:200]}...")
                return
                
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"Batch send to Neo4j failed (attempt {attempt + 1}/{self.MAX_RETRIES}): {e}")
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Batch send to Neo4j failed after {self.MAX_RETRIES} retries: {e}")
                    self._failed_count += 1
    
    def _add_extraction_to_graph(
        self,
        extraction: Dict[str, Any],
        activities: List[AgentActivity]
    ):
        """
        Add extracted entities and relationships to Neo4j
        
        Args:
            extraction: LLM extraction result
            activities: Source activities for metadata
        """
        entities = extraction.get("entities", [])
        relationships = extraction.get("relationships", [])
        
        # Track entity name to UUID mapping
        entity_map = {}
        
        # Add entities
        for entity in entities:
            name = entity.get("name", "")
            labels = entity.get("labels", [])
            properties = entity.get("properties", {})
            
            if not name or not labels:
                continue
            
            # Add graph_id and timestamps
            properties["graph_id"] = self.graph_id
            properties["name"] = name
            properties["updated_at"] = datetime.now().isoformat()
            
            # Check if entity exists
            existing = self.neo4j.execute_query(
                "MATCH (n {graph_id: $graph_id, name: $name}) RETURN n.uuid as uuid LIMIT 1",
                {"graph_id": self.graph_id, "name": name}
            )
            
            if existing:
                # Update entity
                entity_uuid = existing[0]["uuid"]
                entity_map[name] = entity_uuid
                
                update_query = """
                MATCH (n {uuid: $uuid})
                SET n += $properties
                """
                self.neo4j.execute_write(update_query, {
                    "uuid": entity_uuid,
                    "properties": properties
                })
            else:
                # Create new entity
                properties["created_at"] = datetime.now().isoformat()
                entity_uuid = self.neo4j.create_node(
                    labels=["GraphNode"] + labels,
                    properties=properties
                )
                entity_map[name] = entity_uuid
        
        # Add relationships
        for rel in relationships:
            source_name = rel.get("source_name", "")
            target_name = rel.get("target_name", "")
            rel_type = rel.get("type", "RELATED_TO")
            rel_props = rel.get("properties", {})
            
            if not all([source_name, target_name]):
                continue
            
            source_uuid = entity_map.get(source_name)
            target_uuid = entity_map.get(target_name)
            
            if not source_uuid or not target_uuid:
                continue
            
            # Add temporal properties
            rel_props["created_at"] = datetime.now().isoformat()
            rel_props["graph_id"] = self.graph_id
            
            # Create relationship
            self.neo4j.create_relationship(
                source_uuid,
                target_uuid,
                rel_type,
                rel_props
            )
    
    def _flush_remaining(self):
        """Send remaining activities in queue and buffers"""
        # First process remaining activities in queue, add to buffers
        while not self._activity_queue.empty():
            try:
                activity = self._activity_queue.get_nowait()
                platform = activity.platform.lower()
                with self._buffer_lock:
                    if platform not in self._platform_buffers:
                        self._platform_buffers[platform] = []
                    self._platform_buffers[platform].append(activity)
            except Empty:
                break
        
        # Then send remaining activities in each platform buffer (even if less than BATCH_SIZE)
        with self._buffer_lock:
            for platform, buffer in self._platform_buffers.items():
                if buffer:
                    logger.info(f"Sending remaining {len(buffer)} {platform} activities")
                    self._send_batch_activities(buffer, platform)
            # Clear all buffers
            for platform in self._platform_buffers:
                self._platform_buffers[platform] = []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        with self._buffer_lock:
            buffer_sizes = {p: len(b) for p, b in self._platform_buffers.items()}
        
        return {
            "graph_id": self.graph_id,
            "batch_size": self.BATCH_SIZE,
            "total_activities": self._total_activities,  # Total activities added to queue
            "batches_sent": self._total_sent,            # Number of batches successfully sent
            "items_sent": self._total_items_sent,        # Number of activities successfully sent
            "failed_count": self._failed_count,          # Number of failed batch sends
            "skipped_count": self._skipped_count,        # Number of filtered activities (DO_NOTHING)
            "queue_size": self._activity_queue.qsize(),
            "buffer_sizes": buffer_sizes,                # Size of each platform buffer
            "running": self._running,
        }


class Neo4jGraphMemoryManager:
    """
    Manages Neo4j graph memory updaters for multiple simulations
    
    Each simulation can have its own updater instance
    """
    
    _updaters: Dict[str, Neo4jGraphMemoryUpdater] = {}
    _lock = threading.Lock()
    
    @classmethod
    def create_updater(cls, simulation_id: str, graph_id: str) -> Neo4jGraphMemoryUpdater:
        """
        Create graph memory updater for simulation
        
        Args:
            simulation_id: Simulation ID
            graph_id: Neo4j graph ID
            
        Returns:
            Neo4jGraphMemoryUpdater instance
        """
        with cls._lock:
            # If already exists, stop the old one first
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
            
            updater = Neo4jGraphMemoryUpdater(graph_id)
            updater.start()
            cls._updaters[simulation_id] = updater
            
            logger.info(f"Created graph memory updater: simulation_id={simulation_id}, graph_id={graph_id}")
            return updater
    
    @classmethod
    def get_updater(cls, simulation_id: str) -> Optional[Neo4jGraphMemoryUpdater]:
        """Get simulation updater"""
        return cls._updaters.get(simulation_id)
    
    @classmethod
    def stop_updater(cls, simulation_id: str):
        """Stop and remove simulation updater"""
        with cls._lock:
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
                del cls._updaters[simulation_id]
                logger.info(f"Stopped graph memory updater: simulation_id={simulation_id}")
    
    # Flag to prevent duplicate stop_all calls
    _stop_all_done = False
    
    @classmethod
    def stop_all(cls):
        """Stop all updaters"""
        # Prevent duplicate calls
        if cls._stop_all_done:
            return
        cls._stop_all_done = True
        
        with cls._lock:
            if cls._updaters:
                for simulation_id, updater in list(cls._updaters.items()):
                    try:
                        updater.stop()
                    except Exception as e:
                        logger.error(f"Failed to stop updater: simulation_id={simulation_id}, error={e}")
                cls._updaters.clear()
            logger.info("Stopped all graph memory updaters")
    
    @classmethod
    def get_all_stats(cls) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all updaters"""
        return {
            sim_id: updater.get_stats() 
            for sim_id, updater in cls._updaters.items()
        }
