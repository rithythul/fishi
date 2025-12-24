#!/bin/bash
# Comprehensive Vue translation script
find . -name "*.vue" -exec sed -i '
# Step names
s/Environment搭建/Environment Setup/g
s/报告Generating/Report Generating/g

# UI labels and text  
s/Work台/Workbench/g
s/未知职业/Unknown Profession/g
s/暂NoneBio/No Bio Available/g
s/选择to话to象/Select Chat Target/g
s/with世界中任意units体to话/Chat with any agent in the world/g
s/withReport Agentto话/Chat with Report Agent/g
s/Send问卷调查到世界中/Send Survey to Simulation World/g

# Comments
s/顶部工具栏/Top Toolbar/g
s/maximum化/maximize/g
s/还原/restore/g
s/可视化/Visualization/g
s/Building中/Building/g
s/Simulation中/Simulating/g
s/Simulationend后/After Simulation/g
s/卡片头部/Card Header/g
s/Activetime轴/Activity Timeline/g
s/行forparameters/Parameter Row/g
s/可use动作/Available Actions/g
s/Twitter Platform进度/Twitter Platform Progress/g
s/Reddit Platform进度/Reddit Platform Progress/g
s/发布帖子/Publish Post/g
s/inCompleted后/After Completion/g
s/整unitss/entire section/g
s/还没/not yet/g
s/完整/complete/g
s/含所Yes/including all/g
s/子section/subsections/g
s/当Yesfinal/when final/g
s/显示特殊/show special/g
s/涉andEntity/Entities Involved/g
s/statuswith步骤/status and steps/g
s/itemsSimulation步骤介绍/Simulation Steps/g
s/新增区域/new section/g
s/split线/divider/g
s/输入区域/input area/g
s/启动button/start button/g
s/Relations展示/Relations Display/g
s/count据/data/g
s/右侧/Right Side/g
s/本体/Ontology/g
s/准备Next Step骤/Prepare Next Step/g

# More specific patterns
s/使useAutomaticconfiguration/Use automatic configuration/g
s/check并CloseIn progressRun/Check and close running/g
' {} \;

echo "✅ Translated all Chinese in Vue files"
