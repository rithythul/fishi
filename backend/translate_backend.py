#!/usr/bin/env python3
"""
Comprehensive backend translation script
Translates all Chinese text in Python files to English
"""
import os
import re
from pathlib import Path

# Translation dictionary for common terms
TRANSLATIONS = {
    # Technical terms
    "本体": "ontology",
    "图谱": "graph",
    "知识图谱": "knowledge graph",
    "实体": "entity",
    "关系": "relationship",
    "节点": "node",
    "边": "edge",
    "检索": "retrieval",
    "生成": "generation",
    "模拟": "simulation",
    "配置": "configuration",
    "环境": "environment",
    "平台": "platform",
    
    # Actions
    "开始": "start",
    "启动": "start",
    "停止": "stop",
    "暂停": "pause",
    "继续": "continue",
    "完成": "completed",
    "失败": "failed",
    "成功": "success",
    "错误": "error",
    "警告": "warning",
    
    # Status
    "正在": "in progress",
    "已": "already",
    "未": "not",
    "初始化": "initialization",
    "运行中": "running",
    "等待": "waiting",
    "处理": "processing",
    
    # Common phrases
    "未配置": "not configured",
    "初始化失败": "initialization failed",
    "获取": "get/fetch",
    "设置": "set",
    "调用": "call",
    "创建": "create",
    "删除": "delete",
    "更新": "update",
    "加载": "load",
    "保存": "save"
}

def translate_file(filepath):
    """Translate a single Python file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        
        # Apply translations
        for cn, en in TRANSLATIONS.items():
            # Only translate in strings and comments, not in code
            content = re.sub(
                rf'(["\'].*?){cn}(.*?["\'])',
                rf'\1{en}\2',
                content
            )
            # Translate in comments
            content = re.sub(
                rf'(#.*?){cn}(.*?)$',
                rf'\1{en}\2',
                content,
                flags=re.MULTILINE
            )
        
        if content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print(f"Error translating {filepath}: {e}")
        return False

# Find all Python files in app/
python_files = []
for root, dirs, files in os.walk('app'):
    for file in files:
        if file.endswith('.py'):
            python_files.append(os.path.join(root, file))

print(f"Found {len(python_files)} Python files")
translated = 0

for filepath in python_files:
    if translate_file(filepath):
        print(f"✓ {filepath}")
        translated += 1

print(f"\n✓ Translated {translated}/{len(python_files)} files")
