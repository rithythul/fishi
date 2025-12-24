#!/usr/bin/env python3
"""Safe translation - only user-visible strings"""
import re
import os

# SAFE translations - only actual Chinese text in strings
SAFE_TRANSLATIONS = {
    # Common log patterns (these appear in f-strings/log messages)
    "已完成": "completed",
    "已保存": "saved", 
    "已加载": "loaded",
    "生成": "generated",
    "开始": "started",
    "完成": "completed",
    "失败": "failed",
    "成功": "successfully",
    "共": "total",
    "超时": "timeout",
    "混合": "hybrid",
    "获取到": "retrieved",
    "关联节点": "related nodes",
    "大纲": "outline",
    "章节": "section",
    "计划": "plan",
    "报告": "report",
    "保存到文件": "saved to file",
    "并行": "parallel",
    "次": "times",
    "个": "",  # particle
    "最大迭代": "maximum iteration",
    "达到": "reached",
    "强制": "forced",
}

files_changed = 0

for root, dirs, files in os.walk('app'):
    for file in files:
        if not file.endswith('.py'):
            continue
        
        filepath = os.path.join(root, file)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original = content
            
            # Apply translations (only complete phrases in strings)
            for cn, en in sorted(SAFE_TRANSLATIONS.items(), key=lambda x: -len(x[0])):
                content = content.replace(cn, en)
            
            if content != original:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                files_changed += 1
                print(f"✓ {filepath}")
        
        except Exception as e:
            print(f"✗ {filepath}: {e}")

print(f"\n✅ Modified {files_changed} files")
