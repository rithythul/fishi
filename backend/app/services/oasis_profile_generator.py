"""
OASIS Agent Profile Generator
Converts entities from Neo4j graph to Agent Profile format required by OASIS simulation platform

Optimizations:
1. Use Neo4j graph queries to enrich node information
2. Optimized prompts to generate very detailed personas
3. Distinguish individual entities from abstract group entities
"""

import json
import random
import time
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime

from openai import OpenAI

from ..config import Config
from ..utils.logger import get_logger
from .neo4j_entity_reader import EntityNode, Neo4jEntityReader
from .neo4j_tools import Neo4jToolsService

logger = get_logger('fishi.oasis_profile')


@dataclass
class OasisAgentProfile:
    """OASIS Agent Profile data structure"""
    # Common fields
    user_id: int
    user_name: str
    name: str
    bio: str
    persona: str
    
    # Optional fields - Reddit style
    karma: int = 1000
    
    # Optional fields - Twitter style
    friend_count: int = 100
    follower_count: int = 150
    statuses_count: int = 500
    
    # Extra persona info
    age: Optional[int] = None
    gender: Optional[str] = None
    mbti: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None
    interested_topics: List[str] = field(default_factory=list)
    
    # Source entity info
    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None
    
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    
    def to_reddit_format(self) -> Dict[str, Any]:
        """Convert to Reddit platform format"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS library requires field name as username (no underscore)
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "created_at": self.created_at,
        }
        
        # Add extra persona info (if available)
        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_twitter_format(self) -> Dict[str, Any]:
        """Convert to Twitter platform format"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS library requires field name as username
            "name": self.name,
            "bio": self.bio,
            "description": self.bio,  # OASIS library requires description field
            "persona": self.persona,
            "user_char": self.persona,  # OASIS library requires user_char field
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "created_at": self.created_at,
        }
        
        # Add extra persona info
        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to complete dictionary format"""
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "age": self.age,
            "gender": self.gender,
            "mbti": self.mbti,
            "country": self.country,
            "profession": self.profession,
            "interested_topics": self.interested_topics,
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "created_at": self.created_at,
        }


class OasisProfileGenerator:
    """
    OASIS Profile Generator
    
    Converts Neo4j graph entities to Agent Profiles required by OASIS simulation
    
    Optimized features:
    1. Use Neo4j graph queries to get richer context
    2. Generate very detailed personas (including basic info, career history, personality traits, social media behavior etc)
    3. Distinguish between individual entities and abstract group entities
    """
    
    # MBTI type list
    MBTI_TYPES = [
        "INTJ", "INTP", "ENTJ", "ENTP",
        "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ",
        "ISTP", "ISFP", "ESTP", "ESFP"
    ]
    
    # Common countries
    COUNTRIES = [
        "China", "US", "UK", "Japan", "Germany", "France", 
        "Canada", "Australia", "Brazil", "India", "South Korea"
    ]
    
    # Individual entity types (need specific persona generation)
    INDIVIDUAL_ENTITY_TYPES = [
        "student", "alumni", "professor", "person", "publicfigure", 
        "expert", "faculty", "official", "journalist", "activist"
    ]
    
    # Group/Institution entity types (need group representative persona)
    GROUP_ENTITY_TYPES = [
        "university", "governmentagency", "organization", "ngo", 
        "mediaoutlet", "company", "institution", "group", "community"
    ]
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        graph_id: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model_name = model_name or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY not configured")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        # Neo4j tools for retrieving rich context
        self.graph_id = graph_id
        self.neo4j_tools = None
        
        try:
            self.neo4j_tools = Neo4jToolsService()
        except Exception as e:
            logger.warning(f"Neo4j tools initialization failed: {e}")
    
    def generate_profile_from_entity(
        self, 
        entity: EntityNode, 
        user_id: int,
        use_llm: bool = True
    ) -> OasisAgentProfile:
        """
        Generate OASIS Agent Profile from Neo4j entity
        
        Args:
            entity: Neo4j entity node
            user_id: User ID (for OASIS)
            use_llm: Whether to use LLM to generate detailed persona
            
        Returns:
            OasisAgentProfile
        """
        entity_type = entity.get_entity_type() or "Entity"
        
        # Basic info
        name = entity.name
        user_name = self._generate_username(name)
        
        # Build context info
        context = self._build_entity_context(entity)
        
        if use_llm:
            # Use LLM to generate detailed persona
            profile_data = self._generate_profile_with_llm(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes,
                context=context
            )
        else:
            # Use rules to generate basic persona
            profile_data = self._generate_profile_rule_based(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes
            )
        
        return OasisAgentProfile(
            user_id=user_id,
            user_name=user_name,
            name=name,
            bio=profile_data.get("bio", f"{entity_type}: {name}"),
            persona=profile_data.get("persona", entity.summary or f"A {entity_type} named {name}."),
            karma=profile_data.get("karma", random.randint(500, 5000)),
            friend_count=profile_data.get("friend_count", random.randint(50, 500)),
            follower_count=profile_data.get("follower_count", random.randint(100, 1000)),
            statuses_count=profile_data.get("statuses_count", random.randint(100, 2000)),
            age=profile_data.get("age"),
            gender=profile_data.get("gender"),
            mbti=profile_data.get("mbti"),
            country=profile_data.get("country"),
            profession=profile_data.get("profession"),
            interested_topics=profile_data.get("interested_topics", []),
            source_entity_uuid=entity.uuid,
            source_entity_type=entity_type,
        )
    
    
    def generate_profiles_from_entities(
        self,
        entities: List[EntityNode],
        use_llm: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        graph_id: Optional[str] = None,
        parallel_count: int = 1,
        realtime_output_path: Optional[str] = None,
        output_platform: str = "reddit"
    ) -> List[OasisAgentProfile]:
        """
        Generate multiple Agent Profiles from a list of entities
        
        Args:
            entities: List of entities
            use_llm: Whether to use LLM
            progress_callback: Progress callback
            graph_id: Graph ID
            parallel_count: Number of parallel threads
            realtime_output_path: Real-time save path
            output_platform: Output platform (reddit/twitter)
            
        Returns:
            List of OasisAgentProfile
        """
        if graph_id:
            self.graph_id = graph_id
            
        total = len(entities)
        profiles = []
        
        # Helper function for single profile generation
        def process_entity(idx, entity):
            try:
                # Use hash of entity name as deterministic user_id
                user_id = abs(hash(entity.name)) % 100000000
                
                if progress_callback:
                    progress_callback(idx, total, f"Generating profile for {entity.name}...")
                
                profile = self.generate_profile_from_entity(
                    entity=entity,
                    user_id=user_id,
                    use_llm=use_llm
                )
                return profile
            except Exception as e:
                logger.error(f"Failed to generate profile for {entity.name}: {e}")
                return None

        # Sequential processing for now to ensure stability 
        # (can be upgraded to parallel later if needed)
        for i, entity in enumerate(entities):
            profile = process_entity(i + 1, entity)
            if profile:
                profiles.append(profile)
                
                # Real-time saving
                if realtime_output_path:
                    self.save_profiles(profiles, realtime_output_path, output_platform)
        
        return profiles

    def save_profiles(
        self, 
        profiles: List[OasisAgentProfile], 
        file_path: str, 
        platform: str = "reddit"
    ):
        """Save profiles to file"""
        import os
        import csv
        
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        if platform == "reddit":
            data = [p.to_reddit_format() for p in profiles]
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        elif platform == "twitter":
            # Twitter uses CSV format
            if not profiles:
                return
                
            data = [p.to_twitter_format() for p in profiles]
            fieldnames = data[0].keys()
            
            with open(file_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(data)

    def _generate_username(self, name: str) -> str:
        """Generate username"""
        # Remove special characters, convert to lowercase
        username = name.lower().replace(" ", "_")
        username = ''.join(c for c in username if c.isalnum() or c == '_')
        
        # Add random suffix to avoid duplicates
        suffix = random.randint(100, 999)
        return f"{username}_{suffix}"
    
    def _search_neo4j_for_entity(self, entity: EntityNode) -> Dict[str, Any]:
        """
        Use Neo4j graph queries to get rich information related to entity
        
        Args:
            entity: Entity node object
            
        Returns:
            Dictionary containing facts, node_summaries, context
        """
        if not self.neo4j_tools:
            return {"facts": [], "node_summaries": [], "context": ""}
        
        entity_name = entity.name
        
        results = {
            "facts": [],
            "node_summaries": [],
            "context": ""
        }
        
        # Must have graph_id to search
        if not self.graph_id:
            logger.debug(f"Skip Neo4j retrieval: graph_id not set")
            return results
        
        try:
            # Use Neo4j tools to search for entity information
            search_result = self.neo4j_tools.search_graph(
                graph_id=self.graph_id,
                query=entity_name,
                limit=30,
                scope="edges"
            )
            
            # Get facts from search results
            results["facts"] = search_result.facts
            
            # Get related nodes
            all_nodes = self.neo4j_tools.get_all_nodes(self.graph_id)
            related_summaries = []
            for node in all_nodes:
                if node.name != entity_name and node.summary:
                    # Check if this node is related to the entity
                    if entity_name.lower() in node.summary.lower():
                        related_summaries.append(node.summary)
                    elif node.name.lower() in str(results["facts"]).lower():
                        related_summaries.append(f"related entity: {node.name}")
            
            results["node_summaries"] = related_summaries[:10]
            
            # Build comprehensive context
            context_parts = []
            if results["facts"]:
                context_parts.append("Fact information:\n" + "\n".join(f"- {f}" for f in results["facts"][:20]))
            if results["node_summaries"]:
                context_parts.append("Related entities:\n" + "\n".join(f"- {s}" for s in results["node_summaries"][:10]))
            results["context"] = "\n\n".join(context_parts)
            
            logger.info(f"Neo4j retrieval completed: {entity_name}, got {len(results['facts'])} facts, {len(results['node_summaries'])} related nodes")
            
        except Exception as e:
            logger.warning(f"Neo4j retrieval failed ({entity_name}): {e}")
        
        return results
    
    def _build_entity_context(self, entity: EntityNode) -> str:
        """
        Build complete context information for entity
        
        Including:
        1. Entity's own attribute info
        2. Related edge info (facts/relationships)
        3. Related node detailed info
        4. Rich info from Neo4j hybrid search
        """
        context_parts = []
        
        # 1. Add entity attribute info
        if entity.attributes:
            attrs = []
            for key, value in entity.attributes.items():
                if value and str(value).strip():
                    attrs.append(f"- {key}: {value}")
            if attrs:
                context_parts.append("### Entity Attributes\n" + "\n".join(attrs))
        
        # 2. Add related edge info (facts/relationships)
        existing_facts = set()
        if entity.related_edges:
            relationships = []
            for edge in entity.related_edges:  # No limit on quantity
                fact = edge.get("fact", "")
                edge_name = edge.get("edge_name", "")
                direction = edge.get("direction", "")
                
                if fact:
                    relationships.append(f"- {fact}")
                    existing_facts.add(fact)
                elif edge_name:
                    if direction == "outgoing":
                        relationships.append(f"- {entity.name} --[{edge_name}]--> (related entity)")
                    else:
                        relationships.append(f"- (related entity) --[{edge_name}]--> {entity.name}")
            
            if relationships:
                context_parts.append("### Related Facts and Relationships\n" + "\n".join(relationships))
        
        # 3. Add related node detailed info
        if entity.related_nodes:
            related_information = []
            for node in entity.related_nodes:  # No limit on quantity
                node_name = node.get("name", "")
                node_labels = node.get("labels", [])
                node_summary = node.get("summary", "")
                
                # Filter specific labels
                custom_labels = [l for l in node_labels if l not in ["Entity", "Node"]]
                label_str = f" ({', '.join(custom_labels)})" if custom_labels else ""
                
                if node_summary:
                    related_information.append(f"- **{node_name}**{label_str}: {node_summary}")
                else:
                    related_information.append(f"- **{node_name}**{label_str}")
            
            if related_information:
                context_parts.append("### Related Entity Information\n" + "\n".join(related_information))
        
        # 4. Use Neo4j retrieval to get richer info
        neo4j_results = self._search_neo4j_for_entity(entity)
        
        if neo4j_results.get("facts"):
            existing_facts = set(context_parts)
            new_facts = [f for f in neo4j_results["facts"] if f not in existing_facts]
            if new_facts:
                context_parts.append("### Neo4j Retrieved Fact Information\n" + "\n".join(f"- {f}" for f in new_facts[:15]))
        
        if neo4j_results.get("node_summaries"):
            context_parts.append("### Neo4j Retrieved Related Nodes\n" + "\n".join(f"- {s}" for s in neo4j_results["node_summaries"][:10]))
        
        return "\n\n".join(context_parts)
    
    def _generate_profile_with_llm(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> Dict[str, Any]:
        """
        Use LLM to generate very detailed persona
        
        Distinguish based on entity type:
        - Individual entities: generate specific character persona
        - Group/Institution entities: generate representative account persona
        """
        
        is_individual = self._is_individual_entity(entity_type)
        
        if is_individual:
            prompt = self._build_individual_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )
        else:
            prompt = self._build_group_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )

        # Try multiple generations until success or max retries reached
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt(is_individual)},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1)  # Reduce temperature each retry
                    # do not set max_tokens, let LLM decide
                )
                
                content = response.choices[0].message.content
                
                # Check if truncated (finish_reason is not 'stop')
                finish_reason = response.choices[0].finish_reason
                if finish_reason == 'length':
                    logger.warning(f"LLM output truncated (attempt {attempt+1}), attempting to fix...")
                    content = self._fix_truncated_json(content)
                
                # Try parsing JSON
                try:
                    result = json.loads(content)
                    
                    # Validate required fields
                    if "bio" not in result or not result["bio"]:
                        result["bio"] = entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}"
                    if "persona" not in result or not result["persona"]:
                        result["persona"] = entity_summary or f"{entity_name} is a {entity_type}."
                    
                    return result
                    
                except json.JSONDecodeError as je:
                    logger.warning(f"JSON parse failed (attempt {attempt+1}): {str(je)[:80]}")
                    
                    # Attempt to fix JSON
                    result = self._try_fix_json(content, entity_name, entity_type, entity_summary)
                    if result.get("_fixed"):
                        del result["_fixed"]
                        return result
                    
                    last_error = je
                    
            except Exception as e:
                logger.warning(f"LLM call failed (attempt {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(1 * (attempt + 1))  # Exponential backoff
        
        logger.warning(f"LLM persona generation failed ({max_attempts} attempts): {last_error}, using rule-based generation")
        return self._generate_profile_rule_based(
            entity_name, entity_type, entity_summary, entity_attributes
        )
    
    def _fix_truncated_json(self, content: str) -> str:
        """Fix truncated JSON (truncated by max_tokens limit)"""
        import re
        
        # If JSON is truncated, try to close it
        content = content.strip()
        
        # Calculate unclosed brackets
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        
        # Check for unclosed string
        # Simple check: if no comma or closing bracket after last quote, it might be truncated string
        if content and content[-1] not in '",}]':
            # Try closing string
            content += '"'
        
        # Close brackets
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
    
    def _try_fix_json(self, content: str, entity_name: str, entity_type: str, entity_summary: str = "") -> Dict[str, Any]:
        """Attempt to fix corrupted JSON"""
        import re
        
        # 1. First attempt to fix truncated case
        content = self._fix_truncated_json(content)
        
        # 2. Try extracting JSON part
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()
            
            # 3. Process newlines in strings
            # Find all string values and replace newlines within them
            def fix_string_newlines(match):
                s = match.group(0)
                # Replace actual newlines in string with space
                s = s.replace('\n', ' ').replace('\r', ' ')
                # Replace excess spaces
                s = re.sub(r'\s+', ' ', s)
                return s
            
            # Match JSON string values
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string_newlines, json_str)
            
            # 4. Try parsing
            try:
                result = json.loads(json_str)
                result["_fixed"] = True
                return result
            except json.JSONDecodeError as e:
                # 5. If still failing, try more aggressive fix
                try:
                    # Remove all control characters
                    json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                    # Replace all continuous whitespace
                    json_str = re.sub(r'\s+', ' ', json_str)
                    result = json.loads(json_str)
                    result["_fixed"] = True
                    return result
                except:
                    pass
        
        # 6. Try extracting partial information from content
        bio_match = re.search(r'"bio"\s*:\s*"([^"]*)"', content)
        persona_match = re.search(r'"persona"\s*:\s*"([^"]*)', content)  # Might be truncated
        
        bio = bio_match.group(1) if bio_match else (entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}")
        persona = persona_match.group(1) if persona_match else (entity_summary or f"{entity_name} is a {entity_type}.")
        
        # If meaningful content extracted, mark as fixed
        if bio_match or persona_match:
            logger.info(f"extracted partial information from corrupted JSON")
            return {
                "bio": bio,
                "persona": persona,
                "_fixed": True
            }
        
        # 7. Completely failed, return basic structure
        logger.warning(f"JSON fix failed, returning basic structure")
        return {
            "bio": entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}",
            "persona": entity_summary or f"{entity_name} is a {entity_type}."
        }
    
    def _is_individual_entity(self, entity_type: str) -> bool:
        """
        Determine if an entity type represents an individual (person) or a group/organization.
        
        Args:
            entity_type: The entity type string to check
            
        Returns:
            True if entity is an individual, False if group/organization
        """
        entity_type_lower = entity_type.lower().replace(" ", "").replace("_", "")
        
        # Check if it matches known individual types
        for individual_type in self.INDIVIDUAL_ENTITY_TYPES:
            if individual_type in entity_type_lower or entity_type_lower in individual_type:
                return True
        
        # Check if it matches known group types
        for group_type in self.GROUP_ENTITY_TYPES:
            if group_type in entity_type_lower or entity_type_lower in group_type:
                return False
        
        # Default: treat unknown types as individuals for more detailed personas
        return True
    
    def _get_system_prompt(self, is_individual: bool) -> str:
        """Get system prompt"""
        base_prompt = "You are an expert in generating social media user profiles. Generate detailed, realistic personas for public opinion simulation, maximizing restoration of existing real situations. Must return valid JSON format, all string values cannot contain unescaped newlines. Use English for output."
        return base_prompt
    
    def _build_individual_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> str:
        """Build detailed persona prompt for individual entity"""
        
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "None"
        context_str = context[:3000] if context else "No extra context"
        
        return f"""Generate a detailed social media user persona for this entity, maximizing restoration of existing real situations.

Entity Name: {entity_name}
Entity Type: {entity_type}
Entity Summary: {entity_summary}
Entity Attributes: {attrs_str}

Context Information:
{context_str}

Please generate JSON with the following fields:

1. bio: Social media bio, 200 characters maximum
2. persona: Detailed persona description (2000-character plain text), must include:
   - Basic information (age, occupation, educational background, location)
   - Character background (important experiences, event associations, social relationships)
   - Personality traits (MBTI type, core personality, emotional expression style)
   - Social media behavior (posting frequency, content preferences, interaction style, language characteristics)
   - Stance and views (attitudes toward topics, content that may anger/move them)
   - Unique characteristics (catchphrases, special experiences, personal hobbies)
   - Personal memory (important part of persona, describe this individual's association with events and their existing actions and reactions in events)
3. age: Age as integer
4. gender: Gender, must be English: "male" or "female"
5. mbti: MBTI type (e.g., INTJ, ENFP, etc.)
6. country: Country (use English, e.g., "China", "United States")
7. profession: Occupation/profession
8. interested_topics: Array of interested topics

Important:
- All field values must be strings or numbers, do not use newline characters
- persona must be a coherent text description
- Use English for all content (gender field must use English male/female)
- Content must be consistent with entity information
- age must be a valid integer, gender must be "male" or "female"
"""

    def _build_group_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> str:
        """Build detailed persona prompt for group/institution entity"""
        
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "None"
        context_str = context[:3000] if context else "No extra context"
        
        return f"""Generate a detailed social media account profile for this organization/group entity, maximizing restoration of existing real situations.

Entity Name: {entity_name}
Entity Type: {entity_type}
Entity Summary: {entity_summary}
Entity Attributes: {attrs_str}

Context Information:
{context_str}

Please generate JSON with the following fields:

1. bio: Official account bio, 200 characters maximum, professional and appropriate
2. persona: Detailed account profile description (2000-character plain text), must include:
   - Organization basic information (official name, institution type, founding background, main functions)
   - Account positioning (account type, target audience, core functions)
   - Communication style (language characteristics, common expressions, taboo topics)
   - Content publishing characteristics (content types, posting frequency, active time periods)
   - Stance and attitude (official position on core topics, handling of controversies)
   - Special notes (represented group profile, operational habits)
   - Institutional memory (important part of organization persona, describe this organization's association with events and its existing actions and reactions in events)
3. age: Fixed value of 30 (virtual age for institutional account)
4. gender: Fixed value "other" (institutional accounts use "other" to indicate non-personal)
5. mbti: MBTI type to describe account style, e.g., ISTJ represents rigorous and conservative
6. country: Country (use English, e.g., "China")
7. profession: Description of institutional function
8. interested_topics: Array of focus areas

Important:
- All field values must be strings or numbers, no null values allowed
- persona must be a coherent text description, do not use newline characters
- Use English for all content (gender field must use English "other")
- age must be integer 30, gender must be string "other"
- Institutional account communication must match its identity positioning"""
    
    def _generate_profile_rule_based(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Use rules to generate basic persona"""
        
        # Generate different personas based on entity types
        entity_type_lower = entity_type.lower()
        
        if entity_type_lower in ["student", "alumni"]:
            return {
                "bio": f"{entity_type} with interests in academics and social issues.",
                "persona": f"{entity_name} is a {entity_type.lower()} who is actively engaged in academic and social discussions. They enjoy sharing perspectives and connecting with peers.",
                "age": random.randint(18, 30),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": "Student",
                "interested_topics": ["Education", "Social Issues", "Technology"],
            }
        
        elif entity_type_lower in ["publicfigure", "expert", "faculty"]:
            return {
                "bio": f"Expert and thought leader in their field.",
                "persona": f"{entity_name} is a recognized {entity_type.lower()} who shares insights and opinions on important matters. They are known for their expertise and influence in public discourse.",
                "age": random.randint(35, 65),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_type,
                "interested_topics": ["Politics", "Economy", "Society"],
            }
            
        elif entity_type_lower in ["official", "government", "governmentagency"]:
            return {
                "bio": f"Official account representing {entity_name}.",
                "persona": f"{entity_name} is an official entity responsible for public administration and service. Their communications are formal, authoritative, and focused on policy and public welfare.",
                "age": 40,
                "gender": "other",
                "mbti": "ISTJ",
                "country": "China",
                "profession": "Government Official",
                "interested_topics": ["Policy", "Regulation", "Public Service"],
            }
            
        elif entity_type_lower in ["media", "mediaoutlet", "journalist"]:
            return {
                "bio": f"News and media coverage.",
                "persona": f"{entity_name} is a media entity dedicated to reporting news and events. They focus on accuracy, timeliness, and public interest.",
                "age": 30,
                "gender": "other",
                "mbti": "ESTP",
                "country": "China",
                "profession": "Media",
                "interested_topics": ["News", "Current Events", "Society"],
            }
            
        else:
            # General default
            return {
                "bio": f"{entity_type}: {entity_name}",
                "persona": entity_summary or f"{entity_name} is a {entity_type}.",
                "age": 25,
                "gender": "other",
                "mbti": random.choice(self.MBTI_TYPES),
                "country": "Global",
                "profession": entity_type,
                "interested_topics": ["General"],
            }
