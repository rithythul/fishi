"""
LLM-Based Entity Extractor
Replaces ZEP's automatic entity extraction with LLM-based extraction
"""

import json
from typing import Dict, Any, List, Optional
from openai import OpenAI

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('fishi.llm_entity_extractor')


class LLMEntityExtractor:
    """
    Extract entities and relationships from text using LLM
    Guided by ontology definition to ensure consistent extraction
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None
    ):
        """
        Initialize entity extractor
        
        Args:
            api_key: OpenAI-compatible API key
            base_url: API base URL
            model_name: Model name
        """
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model_name = model_name or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY not configured")
        
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
    
    def extract_entities(
        self,
        text: str,
        ontology: Dict[str, Any],
        batch_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Extract entities and relationships from text
        
        Args:
            text: Input text to analyze
            ontology: Ontology definition (entity_types, edge_types)
            batch_mode: If True, optimize for batch processing
            
        Returns:
            {
                "entities": [
                    {
                        "name": "entity name",
                        "labels": ["EntityType"],
                        "properties": {"key": "value", ...}
                    },
                    ...
                ],
                "relationships": [
                    {
                        "source_name": "entity1",
                        "target_name": "entity2",
                        "type": "RELATIONSHIP_TYPE",
                        "properties": {"key": "value", ...}
                    },
                    ...
                ]
            }
        """
        # Build extraction prompt
        prompt = self._build_extraction_prompt(text, ontology)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at extracting structured information from text. "
                                 "Extract entities and relationships according to the provided ontology. "
                                 "Return valid JSON only, no explanations."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                response_format={"type": "json_object"} if hasattr(self.client, 'response_format') else None
            )
            
            result_text = response.choices[0].message.content
            result = json.loads(result_text)
            
            # Validate and normalize result
            normalized = self._normalize_extraction(result, ontology)
            
            logger.debug(f"Extracted {len(normalized['entities'])} entities, "
                        f"{len(normalized['relationships'])} relationships")
            
            return normalized
            
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return {"entities": [], "relationships": []}
    
    def _build_extraction_prompt(self, text: str, ontology: Dict[str, Any]) -> str:
        """Build extraction prompt with ontology guidance"""
        
        # Get entity types
        entity_types = ontology.get("entity_types", [])
        edge_types = ontology.get("edge_types", [])
        
        entity_descriptions = "\n".join([
            f"  - {et['name']}: {et.get('description', 'No description')}"
            for et in entity_types
        ])
        
        edge_descriptions = "\n".join([
            f"  - {et['name']}: {et.get('description', 'No description')}"
            for et in edge_types
        ])
        
        attribute_examples = {}
        for et in entity_types:
            attrs = et.get("attributes", [])
            if attrs:
                attribute_examples[et['name']] = [a['name'] for a in attrs[:3]]  # First 3 attributes
        
        prompt = f"""Extract entities and relationships from the following text.

**Entity Types (extract these):**
{entity_descriptions}

**Relationship Types (extract these):**
{edge_descriptions}

**Instructions:**
1. Identify ALL entities mentioned in the text that match the defined entity types
2. For each entity, extract relevant properties (name, attributes, etc.)
3. Identify relationships between entities that match the defined relationship types
4. Return results in JSON format with "entities" and "relationships" arrays

**Example attribute properties for entities:**
{json.dumps(attribute_examples, indent=2)}

**Text to analyze:**
{text}

**Return format (JSON only):**
{{
  "entities": [
    {{
      "name": "entity name",
      "labels": ["EntityType"],
      "properties": {{"key": "value"}}
    }}
  ],
  "relationships": [
    {{
      "source_name": "entity1 name",
      "target_name": "entity2 name",
      "type": "RELATIONSHIP_TYPE",
      "properties": {{"key": "value"}}
    }}
  ]
}}
"""
        return prompt
    
    def _normalize_extraction(
        self,
        raw_result: Dict[str, Any],
        ontology: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Normalize and validate extraction results
        
        Args:
            raw_result: Raw LLM output
            ontology: Ontology definition
            
        Returns:
            Normalized result
        """
        entities = raw_result.get("entities", [])
        relationships = raw_result.get("relationships", [])
        
        # Normalize entities
        normalized_entities = []
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            
            name = entity.get("name", "")
            labels = entity.get("labels", [])
            properties = entity.get("properties", {})
            
            if not name or not labels:
                continue
            
            # Ensure labels is a list
            if isinstance(labels, str):
                labels = [labels]
            
            normalized_entities.append({
                "name": name,
                "labels": labels,
                "properties": properties
            })
        
        # Normalize relationships
        normalized_relationships = []
        for rel in relationships:
            if not isinstance(rel, dict):
                continue
            
            source = rel.get("source_name", "")
            target = rel.get("target_name", "")
            rel_type = rel.get("type", "")
            properties = rel.get("properties", {})
            
            if not all([source, target, rel_type]):
                continue
            
            normalized_relationships.append({
                "source_name": source,
                "target_name": target,
                "type": rel_type,
                "properties": properties
            })
        
        return {
            "entities": normalized_entities,
            "relationships": normalized_relationships
        }
    
    def extract_from_activity(
        self,
        activity_description: str,
        agent_name: str
    ) -> Dict[str, Any]:
        """
        Extract entities and facts from agent activity description
        Used for memory updates during simulation
        
        Args:
            activity_description: Natural language activity description
            agent_name: Name of the agent performing activity
            
        Returns:
            Extracted entities and facts
        """
        prompt = f"""Extract entities and relationships from this social media activity.

**Activity:**
{activity_description}

**Extract:**
1. People mentioned (including the agent: {agent_name})
2. Topics or content discussed
3. Actions/relationships between entities

Return JSON with "entities" and "relationships" arrays.

**Format:**
{{
  "entities": [
    {{"name": "person/topic name", "labels": ["Person" or "Topic"], "properties": {{}}}}
  ],
  "relationships": [
    {{"source_name": "agent", "target_name": "entity", "type": "MENTIONED/LIKED/etc", "properties": {{}}}}
  ]
}}
"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "Extract structured data from social media activities. Return JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"} if hasattr(self.client, 'response_format') else None
            )
            
            result_text = response.choices[0].message.content
            return json.loads(result_text)
            
        except Exception as e:
            logger.error(f"Activity extraction failed: {e}")
            return {"entities": [], "relationships": []}
