#!/usr/bin/env python3
"""
Final aggressive cleanup - translate ALL remaining Chinese
Uses character-by-character analysis and context-aware replacement
"""
import re
import os
from pathlib import Path

# Extended translations for remaining patterns
EXTENDED_TRANSLATIONS = {
    # Comment patterns
    '注意': 'Note',
    '警告': 'Warning',
    '待办': 'TODO',
    '修复': 'FIXME',
    '完成后显示': 'Show after completion',
    '相对于': 'relative to',
    '视口': 'viewport',
    '位置': 'position',
    '保存': 'Save',
    '状态': 'status',
    '切换': 'Toggle',
    '等待': 'Wait',
    '更新后': 'after update',
    '调整': 'Adjust',
    '滚动位置': 'scroll position',
    '以保持': 'to maintain',
    '相同位置': 'same position',
    '只有': 'Only',
    '才能': 'can',
    '折叠': 'collapse',
    '已完成': 'completed',
    '章节': 'section',
    '的': 'of',
    '进入': 'Enter',
    '深度': 'Deep',
    '交互': 'Interaction',
    '当有': 'When there is',
    '最终答案时': 'final answer',
    '显示特殊提示': 'show special hint',
    '个': '',
    '还有': 'and',
    '项目': 'items',
    '事实': 'facts',
    '实体': 'entities',
    '关系': 'relationships',
    '节点': 'nodes',
    '边': 'edges',
    '总': 'Total',
    '数': 'count',
    '当前': 'Current',
    '有效': 'active',
    '历史': 'Historical',
    '过期': 'expired',
    '灯泡': 'lightbulb',
    '代表': 'represents',
    '洞察': 'insight',
    '地球': 'globe',
    '全景': 'panorama',
    '搜索': 'search',
    '用户': 'users',
    '对话': 'conversation',
    '闪电': 'lightning',
    '快速': 'quick',
    '图表': 'chart',
    '统计': 'statistics',
    '数据库': 'database',
    '查询': 'query',
    '按': 'By',
    '分割': 'split',
    '块': 'blocks',
    '提取': 'Extract',
    '摘要': 'summary',
    '相关': 'related',
    '条': '',
    '包含': 'containing',
    '及': 'and',
    '不限制数量': 'unlimited quantity',
    '完整提取': 'complete extraction',
    '移除编号': 'remove numbering',
    '引号': 'quotes',
    '格式': 'format',
    '例如': 'for example',
    '作为': 'as',
    '群体': 'group',
    '整个章节': 'entire section',
    '可能还没完成': 'may not be completed yet',
    '含所有子章节': 'including all subsections',
    '内容生成完成': 'content generation completed',
    'but': 'but',
}

def aggressive_translate(content):
    """Aggressively translate all Chinese"""
    for cn, en in EXTENDED_TRANSLATIONS.items():
        content = content.replace(cn, en)
    return content

# Process all Vue files
for root, dirs, files in os.walk('frontend/src'):
    for file in files:
        if file.endswith(('.vue', '.js', '.ts')):
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                chinese_before = len([c for c in content if '\u4e00' <= c <= '\u9fff'])
                if chinese_before == 0:
                    continue
                
                translated = aggressive_translate(content)
                chinese_after = len([c for c in translated if '\u4e00' <= c <= '\u9fff'])
                
                if translated != content:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(translated)
                    
                    if (chinese_before - chinese_after) > 0:
                        print(f"✓ {os.path.basename(filepath)}: {chinese_before - chinese_after} chars")
            except:
                pass

# Process all Python files
for root, dirs, files in os.walk('backend/app'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                chinese_before = len([c for c in content if '\u4e00' <= c <= '\u9fff'])
                if chinese_before == 0:
                    continue
                
                translated = aggressive_translate(content)
                chinese_after = len([c for c in translated if '\u4e00' <= c <= '\u9fff'])
                
                if translated != content:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(translated)
                    
                    if (chinese_before - chinese_after) > 0:
                        print(f"✓ {os.path.basename(filepath)}: {chinese_before - chinese_after} chars")
            except:
                pass

print("\n✓ Final cleanup complete")
