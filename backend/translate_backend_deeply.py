#!/usr/bin/env python3
"""Deep translation script - translate ALL docstrings and comments"""
import re
import os

def translate_file(filepath):
    """Translate Chinese in a single file"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # Replace multi-character Chinese sequences in strings and comments
    chinese_map = {
        # From the sample I saw in report_agent.py
        'Report Agent服务': 'Report Agent Service',
        '使useLangChain + Zep实现ReACT模式of模拟报告生成': 'Use LangChain + Zep to implement ReACT mode simulation report generation',
        '功can：': 'Features:',
        'according to模拟需求andZep图谱info生成报告': 'Generate reports according to simulation requirements and Zep graph information',
        '先规划目录结构，然后分段生成': 'Plan directory structure first, then generate in sections',
        '每段采useReACT多轮思考with反思模式': 'Each section uses ReACT multi-round thinking with reflection mode',
        '支持withuse户to话，into话中自主调use检索工具': 'Support user dialogue, autonomously call search tools in dialogue',
        
        # Common patterns
        '服务': 'service',
        '使use': 'use',
        '实现': 'implement',
        '模式': 'mode',
        '模拟': 'simulation',
        '报告': 'report',
        '生成': 'generate',
        '功can': 'function',
        'according to': 'according to',
        '需求': 'requirement',
        'info': 'information',
        '先': 'first',
        '规划': 'plan',
        '目录': 'directory',
        '结构': 'structure',
        '然后': 'then',
        '分段': 'section by section',
        '每段': 'each section',
        '采use': 'use',
        '多轮': 'multi-round',
        '思考': 'thinking',
        'with': 'with',
        '反思': 'reflection',
        '支持': 'support',
        'use户': 'user',
        'to话': 'dialogue',
        'in': 'in',
        'to话中': 'in dialogue',
        '自主': 'autonomous',
        '调use': 'call',
        '检索': 'search',
        '工具': 'tool',
        
        # More patterns from error logs
        '详细': 'detailed',
        'logrecord器': 'logger',
        '文件夹中': 'in folder',
        '文件': 'file',
        'record': 'record',
        '每一步': 'each step',
        '动作': 'action',
        '每行': 'each line',
        'is一': 'is a',
        '完整': 'complete',
        'to象': 'object',
        'package含': 'contains',
        'time戳': 'timestamp',
        'class型': 'type',
        'contentetc': 'content, etc',
        
        # Single character replacements (be careful with these)
        '的': ' ',
        '了': '',
        '和': ' and ',
        '与': ' and ',
        '或': ' or ',
        '中': ' ',
        '从': ' from ',
        '将': ' will ',
        '可': ' can ',
        '已': ' already ',
        '未': ' not ',
        '不': ' not ',
        '有': ' have ',
    }
    
    # Apply replacements
    for cn, en in sorted(chinese_map.items(), key=lambda x: -len(x[0])):  # Longest first
        content = content.replace(cn, en)
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

# Process all Python files
count = 0
for root, dirs, files in os.walk('app'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            if translate_file(filepath):
                count += 1
                print(f"Translated: {filepath}")

print(f"\nProcessed {count} files")
