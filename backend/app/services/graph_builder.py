"""
Graph Builder Service
API 2: Build Knowledge Graph with Neo4j
"""

import os
import uuid
import time
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from .text_processor import TextProcessor
from .neo4j_service import Neo4jService
from .llm_entity_extractor import LLMEntityExtractor
from ..utils.logger import get_logger

logger = get_logger('fishi.graph_builder')


@dataclass
class GraphInfo:
    """Graph information"""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class GraphBuilderService:
    """
    Graph Builder Service
    Responsible for calling Neo4j to build knowledge graphs
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize graph builder with Neo4j
        
        Args:
            api_key: Not used anymore (kept for API compatibility)
        """
        # Initialize Neo4j service
        self.neo4j = Neo4jService()
        
        # Initialize LLM entity extractor
        self.entity_extractor = LLMEntityExtractor()
        
        self.task_manager = TaskManager()
        
        logger.info("GraphBuilderService initialized with Neo4j")
    
    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "Fishi Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3
    ) -> str:
        """
        Build graph asynchronously
        
        Args:
            text: Input text
            ontology: Ontology definition (from API 1 output)
            graph_name: Graph name
            chunk_size: Text chunk size
            chunk_overlap: Chunk overlap size
            batch_size: Batch size for processing
            
        Returns:
            Task ID
        """
        # Create task
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            }
        )
        
        # Execute build in background thread
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size)
        )
        thread.daemon = True
        thread.start()
        
        return task_id
    
    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int
    ):
        """Graph build worker thread"""
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message="Starting graph build..."
            )
            
            # 1. Create graph
            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=f"Graph created: {graph_id}"
            )
            
            # 2. Set ontology (create constraints and indexes)
            self.set_ontology(graph_id, ontology)
            self.task_manager.update_task(
                task_id,
                progress=15,
                message="Ontology set"
            )
            
            # 3. Split text into chunks
            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(
                task_id,
                progress=20,
                message=f"Text split into {total_chunks} chunks"
            )
            
            # 4. Process text in batches, extract entities and add to graph
            self.add_text_batches(
                graph_id, chunks, ontology, batch_size,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=20 + int(prog * 70),  # 20-90%
                    message=msg
                )
            )
            
            # 5. Get graph information
            self.task_manager.update_task(
                task_id,
                progress=95,
                message="Getting graph information..."
            )
            
            graph_information = self._get_graph_information(graph_id)
            
            # Set to 100% before completing
            self.task_manager.update_task(
                task_id,
                progress=100,
                message="Graph build complete!"
            )
            
            # Complete
            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_information": graph_information.to_dict(),
                "chunks_processed": total_chunks,
            })
            
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            logger.error(f"Graph build failed: {error_msg}")
            self.task_manager.fail_task(task_id, error_msg)
    
    def create_graph(self, name: str) -> str:
        """
        Create Neo4j graph (public method)
        
        Args:
            name: Graph name
            
        Returns:
            Graph ID
        """
        graph_id = f"fishi_{uuid.uuid4().hex[:16]}"
        
        # Create graph metadata node
        self.neo4j.create_node(
            labels=["Graph", "Metadata"],
            properties={
                "graph_id": graph_id,
                "name": name,
                "description": "Fishi Social Simulation Graph",
                "created_at": datetime.now().isoformat()
            }
        )
        
        # Create constraints and indexes
        self.neo4j.create_constraints(graph_id)
        
        logger.info(f"Created graph: {graph_id}")
        return graph_id
    
    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        """
        Set graph ontology (public method)
        
        In Neo4j, we store ontology as metadata and create indexes
        
        Args:
            graph_id: Graph ID
            ontology: Ontology definition
        """
        # Store ontology in metadata
        query = """
        MATCH (g:Graph:Metadata {graph_id: $graph_id})
        SET g.ontology = $ontology
        """
        
        self.neo4j.execute_write(
            query,
            {
                "graph_id": graph_id,
                "ontology": str(ontology)  # Convert to string for storage
            }
        )
        
        # Create indexes for entity types
        entity_types = ontology.get("entity_types", [])
        for entity_type in entity_types:
            type_name = entity_type.get("name", "")
            if type_name:
                try:
                    # Create index for this entity type
                    index_query = f"CREATE INDEX {graph_id}_{type_name}_name IF NOT EXISTS FOR (n:{type_name}) ON (n.name)"
                    with self.neo4j.session() as session:
                        session.run(index_query)
                except Exception as e:
                    logger.warning(f"Could not create index for {type_name}: {e}")
        
        logger.info(f"Set ontology for graph {graph_id}")
    
    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        ontology: Dict[str, Any],
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """
        Add text to graph in batches, using LLM to extract entities and add to Neo4j
        
        Args:
            graph_id: Graph ID
            chunks: Text chunks
            ontology: Ontology definition
            batch_size: Batch size
            progress_callback: Progress callback
            
        Returns:
            List of processed chunk IDs
        """
        processed_ids = []
        total_chunks = len(chunks)
        
        for i in range(0, total_chunks, batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_chunks + batch_size - 1) // batch_size
            
            if progress_callback:
                progress = (i + len(batch_chunks)) / total_chunks
                progress_callback(
                    f"Processing batch {batch_num}/{total_batches} ({len(batch_chunks)} chunks)...",
                    progress
                )
            
            # Process each chunk
            for chunk in batch_chunks:
                try:
                    # Extract entities and relationships using LLM
                    extraction = self.entity_extractor.extract_entities(chunk, ontology)
                    
                    # Add to Neo4j
                    self._add_extraction_to_graph(
                        graph_id,
                        extraction,
                        source_text=chunk[:100]  # First 100 chars for reference
                    )
                    
                    processed_ids.append(f"chunk_{i}")
                    
                except Exception as e:
                    logger.error(f"Failed to process chunk {i}: {e}")
            
            # Avoid request overload
            time.sleep(0.5)
        
        return processed_ids
    
    def _add_extraction_to_graph(
        self,
        graph_id: str,
        extraction: Dict[str, Any],
        source_text: str = ""
    ):
        """
        Add extracted entities and relationships to Neo4j graph
        
        Args:
            graph_id: Graph ID
            extraction: Extraction result from LLM
            source_text: Source text reference
        """
        entities = extraction.get("entities", [])
        relationships = extraction.get("relationships", [])
        
        # Track entity name to UUID mapping for this extraction
        entity_map = {}
        
        # Add entities
        for entity in entities:
            name = entity.get("name", "")
            labels = entity.get("labels", [])
            properties = entity.get("properties", {})
            
            if not name or not labels:
                continue
            
            # Add graph_id and timestamps to properties
            properties["graph_id"] = graph_id
            properties["name"] = name
            properties["created_at"] = datetime.now().isoformat()
            
            # Check if entity already exists
            existing = self.neo4j.execute_query(
                "MATCH (n {graph_id: $graph_id, name: $name}) RETURN n.uuid as uuid LIMIT 1",
                {"graph_id": graph_id, "name": name}
            )
            
            if existing:
                # Entity exists, use existing UUID
                entity_uuid = existing[0]["uuid"]
                entity_map[name] = entity_uuid
                
                # Update properties
                update_query = f"""
                MATCH (n {{uuid: $uuid}})
                SET n += $properties
                """
                self.neo4j.execute_write(update_query, {
                    "uuid": entity_uuid,
                    "properties": properties
                })
            else:
                # Create new entity
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
            
            # Get UUIDs
            source_uuid = entity_map.get(source_name)
            target_uuid = entity_map.get(target_name)
            
            if not source_uuid or not target_uuid:
                continue
            
            # Add temporal properties for memory classification
            now = datetime.now().isoformat()
            rel_props["created_at"] = now
            rel_props["valid_at"] = now  # Mark as currently valid for memory queries
            rel_props["graph_id"] = graph_id
            
            # Create relationship
            self.neo4j.create_relationship(
                source_uuid,
                target_uuid,
                rel_type,
                rel_props
            )
    
    def _get_graph_information(self, graph_id: str) -> GraphInfo:
        """
        Get graph information
        
        Args:
            graph_id: Graph ID
            
        Returns:
            GraphInfo object
        """
        # Get node count
        node_result = self.neo4j.execute_query(
            "MATCH (n:GraphNode {graph_id: $graph_id}) RETURN count(n) as count",
            {"graph_id": graph_id}
        )
        node_count = node_result[0]["count"] if node_result else 0
        
        # Get edge count
        edge_result = self.neo4j.execute_query(
            """
            MATCH (a:GraphNode {graph_id: $graph_id})-[r]->(b:GraphNode {graph_id: $graph_id})
            RETURN count(r) as count
            """,
            {"graph_id": graph_id}
        )
        edge_count = edge_result[0]["count"] if edge_result else 0
        
        # Get entity types
        types_result = self.neo4j.execute_query(
            """
            MATCH (n:GraphNode {graph_id: $graph_id})
            UNWIND labels(n) as label
            WITH DISTINCT label
            WHERE label <> 'GraphNode'
            RETURN collect(label) as types
            """,
            {"graph_id": graph_id}
        )
        entity_types = types_result[0]["types"] if types_result else []
        
        return GraphInfo(
            graph_id=graph_id,
            node_count=node_count,
            edge_count=edge_count,
            entity_types=entity_types
        )
    
    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """
        Get complete graph data (with detailed information)
        
        Args:
            graph_id: Graph ID
            
        Returns:
            Dictionary containing nodes and edges
        """
        # Get all nodes
        nodes_result = self.neo4j.execute_query(
            """
            MATCH (n:GraphNode {graph_id: $graph_id})
            RETURN n, labels(n) as labels
            """,
            {"graph_id": graph_id}
        )
        
        nodes_data = []
        for record in nodes_result:
            node = dict(record["n"])
            labels = [l for l in record["labels"] if l != "GraphNode"]
            
            nodes_data.append({
                "uuid": node.get("uuid", ""),
                "name": node.get("name", ""),
                "labels": labels,
                "summary": node.get("summary", ""),
                "attributes": {k: v for k, v in node.items() if k not in ["uuid", "name", "graph_id", "created_at"]},
                "created_at": node.get("created_at"),
            })
        
        # Get all edges
        edges_result = self.neo4j.execute_query(
            """
            MATCH (a:GraphNode {graph_id: $graph_id})-[r]->(b:GraphNode {graph_id: $graph_id})
            RETURN a.uuid as source_uuid, a.name as source_name,
                   b.uuid as target_uuid, b.name as target_name,
                   type(r) as rel_type, properties(r) as rel_props
            """,
            {"graph_id": graph_id}
        )
        
        edges_data = []
        for record in edges_result:
            rel_props = record["rel_props"]
            
            edges_data.append({
                "uuid": rel_props.get("uuid", ""),
                "name": record["rel_type"],
                "fact": rel_props.get("fact", ""),
                "fact_type": record["rel_type"],
                "source_node_uuid": record["source_uuid"],
                "target_node_uuid": record["target_uuid"],
                "source_node_name": record["source_name"],
                "target_node_name": record["target_name"],
                "attributes": {k: v for k, v in rel_props.items() if k not in ["graph_id", "created_at"]},
                "created_at": rel_props.get("created_at"),
            })
        
        return {
            "graph_id": graph_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
        }
    
    def delete_graph(self, graph_id: str):
        """
        Delete graph
        
        Args:
            graph_id: Graph ID
        """
        self.neo4j.delete_graph(graph_id)
        logger.info(f"Deleted graph: {graph_id}")
