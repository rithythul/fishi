"""
LLM-Based Entity Extractor
Replaces manual entity extraction with LLM-based extraction
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
            if not result_text:
                logger.error("LLM returned empty response")
                return {"entities": [], "relationships": []}
                
            try:
                result = json.loads(result_text)
            except json.JSONDecodeError as je:
                logger.error(f"Failed to parse LLM response as JSON: {je}")
                logger.error(f"Raw response: {result_text}")
                # Try to repair common JSON errors if needed, or structured fallback
                return {"entities": [], "relationships": []}
            
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
        
        # Build comprehensive entity type descriptions with ALL attributes
        entity_type_details = []
        for et in entity_types:
            attrs = et.get("attributes", [])
            attr_list = ", ".join([f'"{a["name"]}"' for a in attrs]) if attrs else "none specified"
            entity_type_details.append(
                f"  - **{et['name']}**: {et.get('description', 'No description')}\n"
                f"    Required attributes: [{attr_list}]"
            )
        entity_descriptions = "\n".join(entity_type_details)
        
        edge_descriptions = "\n".join([
            f"  - {et['name']}: {et.get('description', 'No description')}"
            for et in edge_types
        ])
        
        # Build full attribute schema for each entity type
        attribute_schema = {}
        for et in entity_types:
            attrs = et.get("attributes", [])
            attribute_schema[et['name']] = {
                a['name']: a.get('description', 'No description') 
                for a in attrs
            }
        
        prompt = f"""You are an expert entity extractor for knowledge graph construction. 
Extract ALL entities and relationships from the text below.

**IMPORTANT: Be thorough and extract RICH information for each entity!**

**Entity Types to Extract:**
{entity_descriptions}

**Relationship Types to Extract:**
{edge_descriptions}

**Attribute Schema (extract ALL these attributes for each entity type):**
{json.dumps(attribute_schema, indent=2)}

**Extraction Instructions:**
1. Find ALL entities matching the defined types in the text
2. For EACH entity, extract:
   - name: The entity's proper name
   - labels: The entity type(s) from the schema
   - summary: A 2-3 sentence description of the entity based on the text
   - properties: Extract ALL attributes defined in the schema above!
     - If an attribute value isn't mentioned, infer reasonable values OR leave empty
     - Include at least 3-5 properties per entity
3. Extract ALL relationships between entities
4. For relationships, include a "fact" property describing the relationship

**Text to Analyze:**
{text}

**Return JSON format:**
{{
  "entities": [
    {{
      "name": "Entity Name",
      "labels": ["EntityType"],
      "summary": "2-3 sentence description of this entity's role and characteristics",
      "properties": {{
        "attribute1": "value1",
        "attribute2": "value2", 
        "description": "Brief description if applicable"
      }}
    }}
  ],
  "relationships": [
    {{
      "source_name": "Entity1 Name",
      "target_name": "Entity2 Name",
      "type": "RELATIONSHIP_TYPE",
      "properties": {{
        "fact": "Descriptive sentence about this relationship"
      }}
    }}
  ]
}}

CRITICAL: Each entity MUST have at least 3 properties. Include summary for all entities.
Return ONLY valid JSON, no explanations.
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
            summary = entity.get("summary", "")  # Extract summary field
            
            if not name or not labels:
                continue
            
            # Ensure labels is a list
            if isinstance(labels, str):
                labels = [labels]
            
            # Add summary to properties if provided
            if summary and "summary" not in properties:
                properties["summary"] = summary
            
            normalized_entities.append({
                "name": name,
                "labels": labels,
                "properties": properties,
                "summary": summary  # Include summary at top level too
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
2. Topics, concepts, or content discussed (with context and significance)
3. Actions/relationships between entities

**IMPORTANT: For each Topic, provide rich details including:**
- A summary (2-3 sentences explaining the topic in context)
- Why it's significant in this activity
- Related keywords or context

Return JSON with "entities" and "relationships" arrays.

**Format:**
{{
  "entities": [
    {{
      "name": "Entity Name",
      "labels": ["Person" or "Topic"],
      "summary": "2-3 sentence description of this entity's role and significance",
      "properties": {{
        "context": "Why this entity is mentioned",
        "significance": "Its importance in the discussion",
        "keywords": "related terms"
      }}
    }}
  ],
  "relationships": [
    {{
      "source_name": "agent",
      "target_name": "entity",
      "type": "MENTIONED/DISCUSSED/ANALYZED/LIKED/etc",
      "properties": {{
        "fact": "Descriptive sentence about this interaction",
        "sentiment": "positive/neutral/negative"
      }}
    }}
  ]
}}

CRITICAL: Each entity MUST have a summary and at least 2 properties.
"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "Extract structured data from social media activities with rich details. Return JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"} if hasattr(self.client, 'response_format') else None
            )
            
            result_text = response.choices[0].message.content
            if not result_text:
                return {"entities": [], "relationships": []}
                
            try:
                result = json.loads(result_text)
                # Ensure summary is included in properties for each entity
                for entity in result.get("entities", []):
                    if entity.get("summary") and "summary" not in entity.get("properties", {}):
                        if "properties" not in entity:
                            entity["properties"] = {}
                        entity["properties"]["summary"] = entity["summary"]
                return result
            except json.JSONDecodeError:
                logger.error(f"Failed to parse activity extraction JSON: {result_text}")
                return {"entities": [], "relationships": []}
            
        except Exception as e:
            logger.error(f"Activity extraction failed: {e}")
            return {"entities": [], "relationships": []}
