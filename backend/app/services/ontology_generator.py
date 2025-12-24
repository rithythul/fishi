"""
本体generateservice
interface1：分析文本content，generate适合社willsimulationofentitiesandrelationshipstype定义
"""

import json
from typing import Dict, Any, List, Optional
from ..utils.llm_client import LLMClient


# ontologygenerationof系统hint词
ONTOLOGY_SYSTEM_PROMPT = """youis a专业of知识图谱本体设计专家。youof任务is分析give定of文本contentandsimulationrequirement，设计适合**社交媒体舆论simulation**ofentitiestypeandrelationshipstype。

**重want：youmust输出have效ofJSONformatcount据，notwant输出任何其hecontent。**

## 核心任务背景

I们正in构建一**社交媒体舆论simulation系统**。inthis系统 ：
- 每entities都is acanin社交媒体上发声、互动、传播informationof"账号" or "主体"
- entities之间will相互影响、转发、评论、回应
- I们需wantsimulation舆论事件 各方of反应andinformation传播路径

因此，**entitiesmustis现实 真实存inof、canin社媒上发声and互动of主体**：

**canis**：
- 具体ofpeople（公众people物、当事people、意见领袖、专家学者、普通people）
- 公司、企业（package括其官方账号）
- 组织机构（大学、协will、NGO、工willetc）
- 政府部门、监管机构
- 媒体机构（报纸、电视台、自媒体、网站）
- 社交媒体平台本身
- 特定grouprepresents（如校友will、粉丝团、维权groupetc）

**notcanis**：
- 抽象概念（如"舆论"、"情绪"、"趋势"）
- 主题/话题（如"学术诚信"、"教育改革"）
- 观点/态度（如"support方"、"反to方"）

## 输出format

请输出JSONformat，contains以下structure：

```json
{
    "entity_types": [
        {
            "name": "entity types名称（英文，PascalCase）",
            "description": "简短description（英文，not超过100characters）",
            "attributes": [
                {
                    "name": "attributes名（英文，snake_case）",
                    "type": "text",
                    "description": "attributesdescription"
                }
            ],
            "examples": ["exampleentity1", "exampleentity2"]
        }
    ],
    "edge_types": [
        {
            "name": "relationship types名称（英文，UPPER_SNAKE_CASE）",
            "description": "简短description（英文，not超过100characters）",
            "source_targets": [
                {"source": "源entity types", "target": "目标entity types"}
            ],
            "attributes": []
        }
    ],
    "analysis_summary": "to文本contentof简want分析say明（ 文）"
}
```

## 设计指南（极其重want！）

### 1. entity types设计 - must严格遵守

**quantitywant求：must正好10entitiestype**

**层timesstructurewant求（must同时contains具体typeand兜底type）**：

youof10entitiestypemustcontains以下层times：

A. **兜底type（mustcontains，放inlist最后2）**：
   - `Person`: 任何自然people体of兜底type。当一peoplenot属于其he更具体ofpeople物type时，归入此class。
   - `Organization`: 任何组织机构of兜底type。当一组织not属于其he更具体of组织type时，归入此class。

B. **具体type（8，according to文本content设计）**：
   - 针to文本 出现of主want角色，设计更具体oftype
   - for example：if文本涉and学术事件，canhave `Student`, `Professor`, `University`
   - for example：if文本涉and商业事件，canhave `Company`, `CEO`, `Employee`

**for什么需want兜底type**：
- 文本 will出现各种people物，如" 小学教师"、"路people甲"、"某位网友"
- if没have专门oftype匹配，he们should被归入 `Person`
- 同理，小型组织、临时团体etcshould归入 `Organization`

**具体typeof设计原则**：
- from文本 识别出高频出现 or 关keyof角色type
- 每具体typeshouldhave明确ofedges界，避免重叠
- description must清晰say明thistypeand兜底typeof区别

### 2. relationship types设计

- quantity：6-10
- relationshipsshould反映社媒互动 of真实联系
- 确保relationshipsof source_targets 涵盖you定义ofentitiestype

### 3. attributes设计

- 每entitiestype1-3关keyattributes
- **Note**：attributes名notcanuse `name`、`uuid`、`group_id`、`created_at`、`summary`（this些is系统保留字）
- 推荐use：`full_name`, `title`, `role`, `position`, `location`, `description` etc

## entity types参考

**peopleclass（具体）**：
- Student: 学生
- Professor: 教授/学者
- Journalist: 记者
- Celebrity: 明星/网红
- Executive: 高管
- Official: 政府官员
- Lawyer: 律师
- Doctor: 医生

**peopleclass（兜底）**：
- Person: 任何自然people（not属于上述具体type时use）

**组织class（具体）**：
- University: 高校
- Company: 公司企业
- GovernmentAgency: 政府机构
- MediaOutlet: 媒体机构
- Hospital: 医院
- School:  小学
- NGO: 非政府组织

**组织class（兜底）**：
- Organization: 任何组织机构（not属于上述具体type时use）

## relationship types参考

- WORKS_FOR: 工作于
- STUDIES_AT: then读于
- AFFILIATED_WITH: 隶属于
- REPRESENTS: represents
- REGULATES: 监管
- REPORTS_ON: 报道
- COMMENTS_ON: 评论
- RESPONDS_TO: 回应
- SUPPORTS: support
- OPPOSES: 反to
- COLLABORATES_WITH: 合作
- COMPETES_WITH: 竞争
"""


class OntologyGenerator:
    """
    本体generate器
    分析文本content，generateentitiesandrelationshipstype定义
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()
    
    def generate(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        generate本体定义
        
        Args:
            document_texts: 文档文本list
            simulation_requirement: simulationrequirementdescription
            additional_context: 额外上下文
            
        Returns:
            本体定义（entity_types, edge_typesetc）
        """
        # 构建usermessage
        user_message = self._build_user_message(
            document_texts, 
            simulation_requirement,
            additional_context
        )
        
        messages = [
            {"role": "system", "content": ONTOLOGY_SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]
        
        # callLLM
        result = self.llm_client.chat_json(
            messages=messages,
            temperature=0.3,
            max_tokens=4096
        )
        
        # validateand后processing
        result = self._validate_and_process(result)
        
        return result
    
    # 传give LLM of文本maximumlength（5万字）
    MAX_TEXT_LENGTH_FOR_LLM = 50000
    
    def _build_user_message(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str]
    ) -> str:
        """Buildusermessage"""
        
        # 合并文本
        combined_text = "\n\n---\n\n".join(document_texts)
        original_length = len(combined_text)
        
        # if文本超过5万字，截断（仅影响传giveLLMofcontent，not影响graph构建）
        if len(combined_text) > self.MAX_TEXT_LENGTH_FOR_LLM:
            combined_text = combined_text[:self.MAX_TEXT_LENGTH_FOR_LLM]
            combined_text += f"\n\n...(原文total{original_length}字，already截取前{self.MAX_TEXT_LENGTH_FOR_LLM}字use于ontology分析)..."
        
        message = f"""## simulationrequirement

{simulation_requirement}

## 文档content

{combined_text}
"""
        
        if additional_context:
            message += f"""
## 额外say明

{additional_context}
"""
        
        message += """
请according to以上content，设计适合社will舆论simulationofentitiestypeandrelationshipstype。

**must遵守of规则**：
1. must正好输出10entitiestype
2. 最后2mustis兜底type：Person（people兜底）and Organization（组织兜底）
3. 前8isaccording to文本content设计of具体type
4. 所haveentitiestypemustis现实 can发声of主体，notcanis抽象概念
5. attributes名notcanuse name、uuid、group_id etc保留字，use full_name、org_name etc替代
"""
        
        return message
    
    def _validate_and_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validateand后processingresult"""
        
        # 确保必want字段存in
        if "entity_types" not in result:
            result["entity_types"] = []
        if "edge_types" not in result:
            result["edge_types"] = []
        if "analysis_summary" not in result:
            result["analysis_summary"] = ""
        
        # validateentity types
        for entity in result["entity_types"]:
            if "attributes" not in entity:
                entity["attributes"] = []
            if "examples" not in entity:
                entity["examples"] = []
            # 确保descriptionnot超过100characters
            if len(entity.get("description", "")) > 100:
                entity["description"] = entity["description"][:97] + "..."
        
        # validaterelationship types
        for edge in result["edge_types"]:
            if "source_targets" not in edge:
                edge["source_targets"] = []
            if "attributes" not in edge:
                edge["attributes"] = []
            if len(edge.get("description", "")) > 100:
                edge["description"] = edge["description"][:97] + "..."
        
        # Zep API 限制：最多 10 自定义entity types，最多 10 自定义edgetype
        MAX_ENTITY_TYPES = 10
        MAX_EDGE_TYPES = 10
        
        # 兜底type定义
        person_fallback = {
            "name": "Person",
            "description": "Any individual person not fitting other specific person types.",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name of the person"},
                {"name": "role", "type": "text", "description": "Role or occupation"}
            ],
            "examples": ["ordinary citizen", "anonymous netizen"]
        }
        
        organization_fallback = {
            "name": "Organization",
            "description": "Any organization not fitting other specific organization types.",
            "attributes": [
                {"name": "org_name", "type": "text", "description": "Name of the organization"},
                {"name": "org_type", "type": "text", "description": "Type of organization"}
            ],
            "examples": ["small business", "community group"]
        }
        
        # checkwhether toalreadyhave兜底type
        entity_names = {e["name"] for e in result["entity_types"]}
        has_person = "Person" in entity_names
        has_organization = "Organization" in entity_names
        
        # 需want添加of兜底type
        fallbacks_to_add = []
        if not has_person:
            fallbacks_to_add.append(person_fallback)
        if not has_organization:
            fallbacks_to_add.append(organization_fallback)
        
        if fallbacks_to_add:
            current_count = len(result["entity_types"])
            needed_slots = len(fallbacks_to_add)
            
            # if添加后will超过 10 ，需want移除一些现havetype
            if current_count + needed_slots > MAX_ENTITY_TYPES:
                # 计算需want移除多少
                to_remove = current_count + needed_slots - MAX_ENTITY_TYPES
                # from末尾移除（保留前面更重wantof具体type）
                result["entity_types"] = result["entity_types"][:-to_remove]
            
            # 添加兜底type
            result["entity_types"].extend(fallbacks_to_add)
        
        # 最终确保not超过限制（防御性编程）
        if len(result["entity_types"]) > MAX_ENTITY_TYPES:
            result["entity_types"] = result["entity_types"][:MAX_ENTITY_TYPES]
        
        if len(result["edge_types"]) > MAX_EDGE_TYPES:
            result["edge_types"] = result["edge_types"][:MAX_EDGE_TYPES]
        
        return result
    
    def generate_python_code(self, ontology: Dict[str, Any]) -> str:
        """
         will 本体定义convertforPython代码（class似ontology.py）
        
        Args:
            ontology: 本体定义
            
        Returns:
            Python代码string
        """
        code_lines = [
            '"""',
            '自定义entity types定义',
            '由MiroFish自动generation，use于社will舆论simulation',
            '"""',
            '',
            'from pydantic import Field',
            'from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel',
            '',
            '',
            '# ============== entity types定义 ==============',
            '',
        ]
        
        # generationentity types
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            desc = entity.get("description", f"A {name} entity.")
            
            code_lines.append(f'class {name}(EntityModel):')
            code_lines.append(f'    """{desc}"""')
            
            attrs = entity.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')
            
            code_lines.append('')
            code_lines.append('')
        
        code_lines.append('# ============== relationship types定义 ==============')
        code_lines.append('')
        
        # generationrelationship types
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            # convertforPascalCaseclass名
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            desc = edge.get("description", f"A {name} relationship.")
            
            code_lines.append(f'class {class_name}(EdgeModel):')
            code_lines.append(f'    """{desc}"""')
            
            attrs = edge.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')
            
            code_lines.append('')
            code_lines.append('')
        
        # generationtypedictionary
        code_lines.append('# ============== typeconfiguration ==============')
        code_lines.append('')
        code_lines.append('ENTITY_TYPES = {')
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            code_lines.append(f'    "{name}": {name},')
        code_lines.append('}')
        code_lines.append('')
        code_lines.append('EDGE_TYPES = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            code_lines.append(f'    "{name}": {class_name},')
        code_lines.append('}')
        code_lines.append('')
        
        # generationedgeofsource_targets映射
        code_lines.append('EDGE_SOURCE_TARGETS = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            source_targets = edge.get("source_targets", [])
            if source_targets:
                st_list = ', '.join([
                    f'{{"source": "{st.get("source", "Entity")}", "target": "{st.get("target", "Entity")}"}}'
                    for st in source_targets
                ])
                code_lines.append(f'    "{name}": [{st_list}],')
        code_lines.append('}')
        
        return '\n'.join(code_lines)

