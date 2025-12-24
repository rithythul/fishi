#!/usr/bin/env python3
"""Extract Chinese text with context to understand what needs translation"""
import re

# Check Step4Report.vue
with open('frontend/src/components/Step4Report.vue', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("=== Chinese text contexts in Step4Report.vue ===\n")
for i, line in enumerate(lines[:200], 1):
    if re.search(r'[\u4e00-\u9fff]', line):
        # Print line number and the line
        print(f"Line {i}: {line.strip()[:100]}")
        if i > 50:  # Just show first 50 matches
            print(f"... (continuing, total {sum(1 for l in lines if re.search(r'[\u4e00-\u9fff]', l))} lines with Chinese)")
            break
