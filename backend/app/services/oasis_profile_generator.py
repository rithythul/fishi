"""
OASIS Agent Profile Generator
Converts entities from Zep graph to Agent Profile format required by OASIS simulation platform

Optimizations:
1. Call Zep retrieval function to enrich node informationrmation
2. Optimized prompts to generate very detailed personas
3. Distinguish individual entities from abstract group entities
"""

import json
import random
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from openai import OpenAI
from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import EntityNode, ZepEntityReader

logger = get_logger('mirofish.oasis_profile')


@dataclass
class OasisAgentProfile:
    """OASIS Agent Profile data structure"""
    # 通use字段
    user_id: int
    user_name: str
    name: str
    bio: str
    persona: str
    
    #  can 选字段 - Reddit风格
    karma: int = 1000
    
    #  can 选字段 - Twitter风格
    friend_count: int = 100
    follower_count: int = 150
    statuses_count: int = 500
    
    # 额外people设information
    age: Optional[int] = None
    gender: Optional[str] = None
    mbti: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None
    interested_topics: List[str] = field(default_factory=list)
    
    # come源entityinformation
    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None
    
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    
    def to_reddit_format(self) -> Dict[str, Any]:
        """ConvertforRedditplatformformat"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS librarywant求字段名for username（无下划线）
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "created_at": self.created_at,
        }
        
        # 添加额外people设information（ifhave）
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
        """ConvertforTwitterplatformformat"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS librarywant求字段名for username（无下划线）
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "created_at": self.created_at,
        }
        
        # 添加额外people设information
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
        """Convertforcompletedictionaryformat"""
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
    OASIS Profilegenerate器
    
     will Zep图谱 ofentitiesconvertforOASISsimulation所需ofAgent Profile
    
    优化特性：
    1. callZep图谱searchfunctionget更丰富of上下文
    2. generate非常detailedofpeople设（package括基本information、职业经历、性格特征、社交媒体行foretc）
    3. 区分peopleentitiesand抽象groupentities
    """
    
    # MBTItypelist
    MBTI_TYPES = [
        "INTJ", "INTP", "ENTJ", "ENTP",
        "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ",
        "ISTP", "ISFP", "ESTP", "ESFP"
    ]
    
    # 常见国家list
    COUNTRIES = [
        "China", "US", "UK", "Japan", "Germany", "France", 
        "Canada", "Australia", "Brazil", "India", "South Korea"
    ]
    
    # peopletypeentity（需wantgeneration具体people设）
    INDIVIDUAL_ENTITY_TYPES = [
        "student", "alumni", "professor", "person", "publicfigure", 
        "expert", "faculty", "official", "journalist", "activist"
    ]
    
    # group/机构typeentity（需wantgenerationgrouprepresentspeople设）
    GROUP_ENTITY_TYPES = [
        "university", "governmentagency", "organization", "ngo", 
        "mediaoutlet", "company", "institution", "group", "community"
    ]
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        zep_api_key: Optional[str] = None,
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
        
        # Zep客户端use于retrieval丰富上下文
        self.zep_api_key = zep_api_key or Config.ZEP_API_KEY
        self.zep_client = None
        self.graph_id = graph_id
        
        if self.zep_api_key:
            try:
                self.zep_client = Zep(api_key=self.zep_api_key)
            except Exception as e:
                logger.warning(f"Zep客户端initializationfailed: {e}")
    
    def generate_profile_from_entity(
        self, 
        entity: EntityNode, 
        user_id: int,
        use_llm: bool = True
    ) -> OasisAgentProfile:
        """
        fromZepentitiesgenerateOASIS Agent Profile
        
        Args:
            entity: Zepentitiesnodes
            user_id: userID（use于OASIS）
            use_llm: whether touseLLMgeneratedetailedpeople设
            
        Returns:
            OasisAgentProfile
        """
        entity_type = entity.get_entity_type() or "Entity"
        
        # 基础information
        name = entity.name
        user_name = self._generate_username(name)
        
        # 构建上下文information
        context = self._build_entity_context(entity)
        
        if use_llm:
            # useLLMgenerationdetailedpeople设
            profile_data = self._generate_profile_with_llm(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes,
                context=context
            )
        else:
            # use规则generation基础people设
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
    
    def _generate_username(self, name: str) -> str:
        """generationuser名"""
        # 移除特殊characters，convertfor小写
        username = name.lower().replace(" ", "_")
        username = ''.join(c for c in username if c.isalnum() or c == '_')
        
        # 添加随机后缀避免重复
        suffix = random.randint(100, 999)
        return f"{username}_{suffix}"
    
    def _search_zep_for_entity(self, entity: EntityNode) -> Dict[str, Any]:
        """
        useZep图谱hybridsearchfunctiongetentitiesrelatedof丰富information
        
        Zep没have内置hybridsearchinterface，需want分别searchedgesandnodesthen合并result。
        useparallelrequest同时search，提高效率。
        
        Args:
            entity: entitiesnodesobject
            
        Returns:
            containsfacts, node_summaries, contextofdictionary
        """
        import concurrent.futures
        
        if not self.zep_client:
            return {"facts": [], "node_summaries": [], "context": ""}
        
        entity_name = entity.name
        
        results = {
            "facts": [],
            "node_summaries": [],
            "context": ""
        }
        
        # musthavegraph_id才can进行search
        if not self.graph_id:
            logger.debug(f"跳过Zepretrieval：notsetgraph_id")
            return results
        
        comprehensive_query = f"all informationrmation about、活动、事件、relationshipand背景"
        
        def search_edges():
            """searchedge（facts/relationship）- 带retry机制"""
            max_retries = 3
            last_exception = None
            delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=comprehensive_query,
                        graph_id=self.graph_id,
                        limit=30,
                        scope="edges",
                        reranker="rrf"
                    )
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.debug(f"Zepedgesearch第 {attempt + 1} timesfailed: {str(e)[:80]}, retrying...")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.debug(f"Zepedgesearchin {max_retries} attempts后仍failed: {e}")
            return None
        
        def search_nodes():
            """searchnode（entity摘want）- 带retry机制"""
            max_retries = 3
            last_exception = None
            delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=comprehensive_query,
                        graph_id=self.graph_id,
                        limit=20,
                        scope="nodes",
                        reranker="rrf"
                    )
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.debug(f"Zepnodesearch第 {attempt + 1} timesfailed: {str(e)[:80]}, retrying...")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.debug(f"Zepnodesearchin {max_retries} attempts后仍failed: {e}")
            return None
        
        try:
            # parallelexecuteedgesandnodessearch
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                edge_future = executor.submit(search_edges)
                node_future = executor.submit(search_nodes)
                
                # getresult
                edge_result = edge_future.result(timeout=30)
                node_result = node_future.result(timeout=30)
            
            # processingedgesearchresult
            all_facts = set()
            if edge_result and hasattr(edge_result, 'edges') and edge_result.edges:
                for edge in edge_result.edges:
                    if hasattr(edge, 'fact') and edge.fact:
                        all_facts.add(edge.fact)
            results["facts"] = list(all_facts)
            
            # processingnodesearchresult
            all_summaries = set()
            if node_result and hasattr(node_result, 'nodes') and node_result.nodes:
                for node in node_result.nodes:
                    if hasattr(node, 'summary') and node.summary:
                        all_summaries.add(node.summary)
                    if hasattr(node, 'name') and node.name and node.name != entity_name:
                        all_summaries.add(f"relatedentity: {node.name}")
            results["node_summaries"] = list(all_summaries)
            
            # 构建综合上下文
            context_parts = []
            if results["facts"]:
                context_parts.append("Fact informationrmation:\n" + "\n".join(f"- {f}" for f in results["facts"][:20]))
            if results["node_summaries"]:
                context_parts.append("relatedentity:\n" + "\n".join(f"- {s}" for s in results["node_summaries"][:10]))
            results["context"] = "\n\n".join(context_parts)
            
            logger.info(f"Zephybridretrievalcompleted: {entity_name}, get {len(results['facts'])} facts, {len(results['node_summaries'])} relatednode")
            
        except concurrent.futures.TimeoutError:
            logger.warning(f"Zepretrievaltimeout ({entity_name})")
        except Exception as e:
            logger.warning(f"Zepretrievalfailed ({entity_name}): {e}")
        
        return results
    
    def _build_entity_context(self, entity: EntityNode) -> str:
        """
        构建entitiesofcomplete上下文information
        
        package括：
        1. entities本身ofedge informationrmation（facts）
        2. 关联nodesofdetailed informationrmation
        3. Zephybridsearch到of丰富information
        """
        context_parts = []
        
        # 1. 添加entityattributesinformation
        if entity.attributes:
            attrs = []
            for key, value in entity.attributes.items():
                if value and str(value).strip():
                    attrs.append(f"- {key}: {value}")
            if attrs:
                context_parts.append("### entityattributes\n" + "\n".join(attrs))
        
        # 2. 添加relatededgeinformation（facts/relationship）
        existing_facts = set()
        if entity.related_edges:
            relationships = []
            for edge in entity.related_edges:  # not限制quantity
                fact = edge.get("fact", "")
                edge_name = edge.get("edge_name", "")
                direction = edge.get("direction", "")
                
                if fact:
                    relationships.append(f"- {fact}")
                    existing_facts.add(fact)
                elif edge_name:
                    if direction == "outgoing":
                        relationships.append(f"- {entity.name} --[{edge_name}]--> (relatedentity)")
                    else:
                        relationships.append(f"- (relatedentity) --[{edge_name}]--> {entity.name}")
            
            if relationships:
                context_parts.append("### relatedfactsandrelationship\n" + "\n".join(relationships))
        
        # 3. 添加关联nodeofdetailed informationrmation
        if entity.related_nodes:
            related_information = []
            for node in entity.related_nodes:  # not限制quantity
                node_name = node.get("name", "")
                node_labels = node.get("labels", [])
                node_summary = node.get("summary", "")
                
                # filter掉默认label
                custom_labels = [l for l in node_labels if l not in ["Entity", "Node"]]
                label_str = f" ({', '.join(custom_labels)})" if custom_labels else ""
                
                if node_summary:
                    related_information.append(f"- **{node_name}**{label_str}: {node_summary}")
                else:
                    related_information.append(f"- **{node_name}**{label_str}")
            
            if related_information:
                context_parts.append("### 关联entityinformation\n" + "\n".join(related_information))
        
        # 4. useZephybridretrievalget更丰富ofinformation
        zep_results = self._search_zep_for_entity(entity)
        
        if zep_results.get("facts"):
            # go重：排除already存inoffacts
            new_facts = [f for f in zep_results["facts"] if f not in existing_facts]
            if new_facts:
                context_parts.append("### Zepretrieval到offactsinformation\n" + "\n".join(f"- {f}" for f in new_facts[:15]))
        
        if zep_results.get("node_summaries"):
            context_parts.append("### Zepretrieval到ofrelatednode\n" + "\n".join(f"- {s}" for s in zep_results["node_summaries"][:10]))
        
        return "\n\n".join(context_parts)
    
    def _is_individual_entity(self, entity_type: str) -> bool:
        """判断whether toispeopletypeentity"""
        return entity_type.lower() in self.INDIVIDUAL_ENTITY_TYPES
    
    def _is_group_entity(self, entity_type: str) -> bool:
        """判断whether toisgroup/机构typeentity"""
        return entity_type.lower() in self.GROUP_ENTITY_TYPES
    
    def _generate_profile_with_llm(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> Dict[str, Any]:
        """
        useLLMgenerate非常detailedofpeople设
        
        according toentitiestype区分：
        - peopleentities：generate具体ofpeople物set
        - group/机构entities：generaterepresents性账号set
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

        # 尝试多timesgeneration，直到success or reachedmaximumretrytimescount
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
                    temperature=0.7 - (attempt * 0.1)  # 每timesretry降低温度
                    # notsetmax_tokens，让LLM自由发挥
                )
                
                content = response.choices[0].message.content
                
                # checkwhether to被截断（finish_reasonnotis'stop'）
                finish_reason = response.choices[0].finish_reason
                if finish_reason == 'length':
                    logger.warning(f"LLMoutput truncated (attempt {attempt+1}), attempting to fix...")
                    content = self._fix_truncated_json(content)
                
                # 尝试parseJSON
                try:
                    result = json.loads(content)
                    
                    # validate必需字段
                    if "bio" not in result or not result["bio"]:
                        result["bio"] = entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}"
                    if "persona" not in result or not result["persona"]:
                        result["persona"] = entity_summary or f"{entity_name}is a{entity_type}。"
                    
                    return result
                    
                except json.JSONDecodeError as je:
                    logger.warning(f"JSONparsefailed (attempt {attempt+1}): {str(je)[:80]}")
                    
                    # attempting to fixJSON
                    result = self._try_fix_json(content, entity_name, entity_type, entity_summary)
                    if result.get("_fixed"):
                        del result["_fixed"]
                        return result
                    
                    last_error = je
                    
            except Exception as e:
                logger.warning(f"LLMcallfailed (attempt {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(1 * (attempt + 1))  # 指count退避
        
        logger.warning(f"LLMgenerationpeople设failed（{max_attempts}attempts）: {last_error}, using rule-based generation")
        return self._generate_profile_rule_based(
            entity_name, entity_type, entity_summary, entity_attributes
        )
    
    def _fix_truncated_json(self, content: str) -> str:
        """FIXME被截断ofJSON（输出被max_tokens限制截断）"""
        import re
        
        # ifJSON被截断，尝试闭合it
        content = content.strip()
        
        # 计算not闭合of括号
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        
        # checkwhether tohavenot闭合ofstring
        # 简单check：if最后一quotes后没have逗号 or 闭合括号， can canisstring被截断
        if content and content[-1] not in '",}]':
            # 尝试闭合string
            content += '"'
        
        # 闭合括号
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
    
    def _try_fix_json(self, content: str, entity_name: str, entity_type: str, entity_summary: str = "") -> Dict[str, Any]:
        """attempting to fix损坏ofJSON"""
        import re
        
        # 1. 首firstattempting to fix被截断of情况
        content = self._fix_truncated_json(content)
        
        # 2. 尝试ExtractJSON部分
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()
            
            # 3. processingstring of换行符问题
            # 找到所havestringvalue并替换其 of换行符
            def fix_string_newlines(match):
                s = match.group(0)
                # 替换string内of实际换行符for空格
                s = s.replace('\n', ' ').replace('\r', ' ')
                # 替换多余空格
                s = re.sub(r'\s+', ' ', s)
                return s
            
            # 匹配JSONstringvalue
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string_newlines, json_str)
            
            # 4. 尝试parse
            try:
                result = json.loads(json_str)
                result["_fixed"] = True
                return result
            except json.JSONDecodeError as e:
                # 5. if还isfailed，尝试更激进ofFIXME
                try:
                    # 移除所have控制characters
                    json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                    # 替换所have连续空白
                    json_str = re.sub(r'\s+', ' ', json_str)
                    result = json.loads(json_str)
                    result["_fixed"] = True
                    return result
                except:
                    pass
        
        # 6. 尝试fromcontent Extract部分information
        bio_match = re.search(r'"bio"\s*:\s*"([^"]*)"', content)
        persona_match = re.search(r'"persona"\s*:\s*"([^"]*)', content)  #  can can被截断
        
        bio = bio_match.group(1) if bio_match else (entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}")
        persona = persona_match.group(1) if persona_match else (entity_summary or f"{entity_name}is a{entity_type}。")
        
        # ifExtract到have意义ofcontent，标记foralreadyFIXME
        if bio_match or persona_match:
            logger.info(f"extracted partial informationrmation from corrupted JSON")
            return {
                "bio": bio,
                "persona": persona,
                "_fixed": True
            }
        
        # 7. 完全failed，returning basic structure
        logger.warning(f"JSONFIXMEfailed，returning basic structure")
        return {
            "bio": entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}",
            "persona": entity_summary or f"{entity_name}is a{entity_type}。"
        }
    
    def _get_system_prompt(self, is_individual: bool) -> str:
        """get系统hint词"""
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
        """Buildpeopleentityofdetailedpeople设hint词"""
        
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "无"
        context_str = context[:3000] if context else "无额外上下文"
        
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
   - Basic informationrmation (age, occupation, educational background, location)
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
- Content must be consistent with entity informationrmation
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
        """Buildgroup/机构entityofdetailedpeople设hint词"""
        
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "无"
        context_str = context[:3000] if context else "无额外上下文"
        
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
   - Organization basic informationrmation (official name, institution type, founding background, main functions)
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
        """use规则generation基础people设"""
        
        # according toentity typesgenerationnot同ofpeople设
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
                "age": random.randint(35, 60),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(["ENTJ", "INTJ", "ENTP", "INTP"]),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_attributes.get("occupation", "Expert"),
                "interested_topics": ["Politics", "Economics", "Culture & Society"],
            }
        
        elif entity_type_lower in ["mediaoutlet", "socialmediaplatform"]:
            return {
                "bio": f"Official account for {entity_name}. News and updates.",
                "persona": f"{entity_name} is a media entity that reports news and facilitates public discourse. The account shares timely updates and engages with the audience on current events.",
                "age": 30,  # 机构虚拟年龄
                "gender": "other",  # 机构useother
                "mbti": "ISTJ",  # 机构风格：严谨保守
                "country": " 国",
                "profession": "Media",
                "interested_topics": ["General News", "Current Events", "Public Affairs"],
            }
        
        elif entity_type_lower in ["university", "governmentagency", "ngo", "organization"]:
            return {
                "bio": f"Official account of {entity_name}.",
                "persona": f"{entity_name} is an institutional entity that communicates official positions, announcements, and engages with stakeholders on relevant matters.",
                "age": 30,  # 机构虚拟年龄
                "gender": "other",  # 机构useother
                "mbti": "ISTJ",  # 机构风格：严谨保守
                "country": " 国",
                "profession": entity_type,
                "interested_topics": ["Public Policy", "Community", "Official Announcements"],
            }
        
        else:
            # 默认people设
            return {
                "bio": entity_summary[:150] if entity_summary else f"{entity_type}: {entity_name}",
                "persona": entity_summary or f"{entity_name} is a {entity_type.lower()} participating in social discussions.",
                "age": random.randint(25, 50),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_type,
                "interested_topics": ["General", "Social Issues"],
            }
    
    def set_graph_id(self, graph_id: str):
        """setgraphIDuse于Zepretrieval"""
        self.graph_id = graph_id
    
    def generate_profiles_from_entities(
        self,
        entities: List[EntityNode],
        use_llm: bool = True,
        progress_callback: Optional[callable] = None,
        graph_id: Optional[str] = None,
        parallel_count: int = 5,
        realtime_output_path: Optional[str] = None,
        output_platform: str = "reddit"
    ) -> List[OasisAgentProfile]:
        """
        批量fromentitiesgenerateAgent Profile（supportparallelgenerate）
        
        Args:
            entities: entitieslist
            use_llm: whether touseLLMgeneratedetailedpeople设
            progress_callback: 进度回调function (current, total, message)
            graph_id: 图谱ID，use于Zepsearchget更丰富上下文
            parallel_count: parallelgeneratequantity，默认5
            realtime_output_path: 实时writeoffile路径（if提供，每generate一thenwrite一times）
            output_platform: 输出平台format ("reddit"  or  "twitter")
            
        Returns:
            Agent Profilelist
        """
        import concurrent.futures
        from threading import Lock
        
        # setgraph_iduse于Zepretrieval
        if graph_id:
            self.graph_id = graph_id
        
        total = len(entities)
        profiles = [None] * total  # 预分配list保持顺序
        completed_count = [0]  # uselist以便in闭package modify
        lock = Lock()
        
        # 实时writefileof辅助function
        def save_profiles_realtime():
            """实时savealreadygenerationof profiles to file"""
            if not realtime_output_path:
                return
            
            with lock:
                # filter出alreadygenerationof profiles
                existing_profiles = [p for p in profiles if p is not None]
                if not existing_profiles:
                    return
                
                try:
                    if output_platform == "reddit":
                        # Reddit JSON format
                        profiles_data = [p.to_reddit_format() for p in existing_profiles]
                        with open(realtime_output_path, 'w', encoding='utf-8') as f:
                            json.dump(profiles_data, f, ensure_ascii=False, indent=2)
                    else:
                        # Twitter CSV format
                        import csv
                        profiles_data = [p.to_twitter_format() for p in existing_profiles]
                        if profiles_data:
                            fieldnames = list(profiles_data[0].keys())
                            with open(realtime_output_path, 'w', encoding='utf-8', newline='') as f:
                                writer = csv.DictWriter(f, fieldnames=fieldnames)
                                writer.writeheader()
                                writer.writerows(profiles_data)
                except Exception as e:
                    logger.warning(f"实时save profiles failed: {e}")
        
        def generate_single_profile(idx: int, entity: EntityNode) -> tuple:
            """generation单profileof工作function"""
            entity_type = entity.get_entity_type() or "Entity"
            
            try:
                profile = self.generate_profile_from_entity(
                    entity=entity,
                    user_id=idx,
                    use_llm=use_llm
                )
                
                # 实时输出generationofpeople设到控制台andlog
                self._print_generated_profile(entity.name, entity_type, profile)
                
                return idx, profile, None
                
            except Exception as e:
                logger.error(f"generationentity {entity.name} ofpeople设failed: {str(e)}")
                # create一基础profile
                fallback_profile = OasisAgentProfile(
                    user_id=idx,
                    user_name=self._generate_username(entity.name),
                    name=entity.name,
                    bio=f"{entity_type}: {entity.name}",
                    persona=entity.summary or f"A participant in social discussions.",
                    source_entity_uuid=entity.uuid,
                    source_entity_type=entity_type,
                )
                return idx, fallback_profile, str(e)
        
        logger.info(f"startparallelgeneration {total} Agentpeople设（parallelcount: {parallel_count}）...")
        print(f"\n{'='*60}")
        print(f"start generationAgentpeople设 - total {total} entity，parallelcount: {parallel_count}")
        print(f"{'='*60}\n")
        
        # use线程池parallelexecute
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_count) as executor:
            # submit所have任务
            future_to_entity = {
                executor.submit(generate_single_profile, idx, entity): (idx, entity)
                for idx, entity in enumerate(entities)
            }
            
            # 收集result
            for future in concurrent.futures.as_completed(future_to_entity):
                idx, entity = future_to_entity[future]
                entity_type = entity.get_entity_type() or "Entity"
                
                try:
                    result_idx, profile, error = future.result()
                    profiles[result_idx] = profile
                    
                    with lock:
                        completed_count[0] += 1
                        current = completed_count[0]
                    
                    # 实时writefile
                    save_profiles_realtime()
                    
                    if progress_callback:
                        progress_callback(
                            current, 
                            total, 
                            f"alreadycompleted {current}/{total}: {entity.name}（{entity_type}）"
                        )
                    
                    if error:
                        logger.warning(f"[{current}/{total}] {entity.name} use备usepeople设: {error}")
                    else:
                        logger.info(f"[{current}/{total}] successgenerationpeople设: {entity.name} ({entity_type})")
                        
                except Exception as e:
                    logger.error(f"processingentity {entity.name} 时发生异常: {str(e)}")
                    with lock:
                        completed_count[0] += 1
                    profiles[idx] = OasisAgentProfile(
                        user_id=idx,
                        user_name=self._generate_username(entity.name),
                        name=entity.name,
                        bio=f"{entity_type}: {entity.name}",
                        persona=entity.summary or "A participant in social discussions.",
                        source_entity_uuid=entity.uuid,
                        source_entity_type=entity_type,
                    )
                    # 实时writefile（即使is备usepeople设）
                    save_profiles_realtime()
        
        print(f"\n{'='*60}")
        print(f"people设generation completed！totalgenerate {len([p for p in profiles if p])} Agent")
        print(f"{'='*60}\n")
        
        return profiles
    
    def _print_generated_profile(self, entity_name: str, entity_type: str, profile: OasisAgentProfile):
        """实时输出generationofpeople设到控制台（completecontent，not截断）"""
        separator = "-" * 70
        
        # 构建complete输出content（not截断）
        topics_str = ', '.join(profile.interested_topics) if profile.interested_topics else '无'
        
        output_lines = [
            f"\n{separator}",
            f"[alreadygeneration] {entity_name} ({entity_type})",
            f"{separator}",
            f"user名: {profile.user_name}",
            f"",
            f"【简介】",
            f"{profile.bio}",
            f"",
            f"【detailedpeople设】",
            f"{profile.persona}",
            f"",
            f"【基本attributes】",
            f"年龄: {profile.age} | 性别: {profile.gender} | MBTI: {profile.mbti}",
            f"职业: {profile.profession} | 国家: {profile.country}",
            f"兴趣话题: {topics_str}",
            separator
        ]
        
        output = "\n".join(output_lines)
        
        # 只输出到控制台（避免重复，loggernot再输出completecontent）
        print(output)
    
    def save_profiles(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """
        saveProfileto file（according to平台选择正确format）
        
        OASIS平台formatwant求：
        - Twitter: CSVformat
        - Reddit: JSONformat
        
        Args:
            profiles: Profilelist
            file_path: file路径
            platform: 平台type ("reddit"  or  "twitter")
        """
        if platform == "twitter":
            self._save_twitter_csv(profiles, file_path)
        else:
            self._save_reddit_json(profiles, file_path)
    
    def _save_twitter_csv(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        saveTwitter ProfileforCSVformat（符合OASIS官方want求）
        
        OASIS Twitterwant求ofCSV字段：
        - user_id: userID（according toCSV顺序from0start）
        - name: user真实姓名
        - username: 系统 ofuser名
        - user_char: detailedpeople设description（注入到LLM系统hint ，指导Agent行for）
        - description: 简短of公开简介（显示inuser资料page）
        
        user_char vs description 区别：
        - user_char: 内部use，LLM系统hint，决定Agent如何thinkingand行动
        - description: 外部显示，其heuser can 见of简介
        """
        import csv
        
        # 确保file扩展名is.csv
        if not file_path.endswith('.csv'):
            file_path = file_path.replace('.json', '.csv')
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # writeOASISwant求of表头
            headers = ['user_id', 'name', 'username', 'user_char', 'description']
            writer.writerow(headers)
            
            # writecount据行
            for idx, profile in enumerate(profiles):
                # user_char: completepeople设（bio + persona），use于LLM系统hint
                user_char = profile.bio
                if profile.persona and profile.persona != profile.bio:
                    user_char = f"{profile.bio} {profile.persona}"
                # processing换行符（CSV use空格替代）
                user_char = user_char.replace('\n', ' ').replace('\r', ' ')
                
                # description: 简短简介，use于外部显示
                description = profile.bio.replace('\n', ' ').replace('\r', ' ')
                
                row = [
                    idx,                    # user_id: from0startof顺序ID
                    profile.name,           # name: 真实姓名
                    profile.user_name,      # username: user名
                    user_char,              # user_char: completepeople设（内部LLMuse）
                    description             # description: 简短简介（外部显示）
                ]
                writer.writerow(row)
        
        logger.info(f"alreadysave {len(profiles)} Twitter Profile到 {file_path} (OASIS CSVformat)")
    
    def _normalize_gender(self, gender: Optional[str]) -> str:
        """
        标准化gender字段forOASISwant求of英文format
        
        OASISwant求: male, female, other
        """
        if not gender:
            return "other"
        
        gender_lower = gender.lower().strip()
        
        #  文映射
        gender_map = {
            "男": "male",
            "女": "female",
            "机构": "other",
            "其he": "other",
            # 英文alreadyhave
            "male": "male",
            "female": "female",
            "other": "other",
        }
        
        return gender_map.get(gender_lower, "other")
    
    def _save_reddit_json(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        saveReddit ProfileforJSONformat
        
        usewith to_reddit_format() 一致offormat，确保 OASIS can正确read。
        mustcontains user_id 字段，thisis OASIS agent_graph.get_agent() 匹配of关key！
        
        必需字段：
        - user_id: userID（整count，use于匹配 initial_posts  of poster_agent_id）
        - username: user名
        - name: 显示名称
        - bio: 简介
        - persona: detailedpeople设
        - age: 年龄（整count）
        - gender: "male", "female",  or  "other"
        - mbti: MBTItype
        - country: 国家
        """
        data = []
        for idx, profile in enumerate(profiles):
            # usewith to_reddit_format() 一致offormat
            item = {
                "user_id": profile.user_id if profile.user_id is not None else idx,  # 关key：mustcontains user_id
                "username": profile.user_name,
                "name": profile.name,
                "bio": profile.bio[:150] if profile.bio else f"{profile.name}",
                "persona": profile.persona or f"{profile.name} is a participant in social discussions.",
                "karma": profile.karma if profile.karma else 1000,
                "created_at": profile.created_at,
                # OASIS必需字段 - 确保都have默认value
                "age": profile.age if profile.age else 30,
                "gender": self._normalize_gender(profile.gender),
                "mbti": profile.mbti if profile.mbti else "ISTJ",
                "country": profile.country if profile.country else " 国",
            }
            
            #  can 选字段
            if profile.profession:
                item["profession"] = profile.profession
            if profile.interested_topics:
                item["interested_topics"] = profile.interested_topics
            
            data.append(item)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"alreadysave {len(profiles)} Reddit Profile到 {file_path} (JSONformat，containsuser_id字段)")
    
    # 保留旧method名作for别名，保持向后兼容
    def save_profiles_to_json(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """[already废弃] 请use save_profiles() method"""
        logger.warning("save_profiles_to_jsonalready废弃，请usesave_profilesmethod")
        self.save_profiles(profiles, file_path, platform)

