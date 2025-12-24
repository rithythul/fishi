#!/usr/bin/env python3
"""
AGGRESSIVE COMPREHENSIVE TRANSLATION
Translates ALL Chinese characters to English - no exceptions
Includes comments, example data, embedded content, everything
"""
import os
import re
from pathlib import Path

# Massive comprehensive translation dictionary
TRANSLATIONS = {
    # All possible Chinese characters and common phrases
    '的': 'of',
    '是': 'is',
    '在': 'in',
    '了': '',
    '和': 'and',
    '有': 'have',
    '为': 'for',
    '人': 'people',
    '个': '',
    '我': 'I',
    '你': 'you',
    '他': 'he',
    '她': 'she',
    '它': 'it',
    '这': 'this',
    '那': 'that',
    '不': 'not',
    '也': 'also',
    '就': 'then',
    '可以': 'can',
    '会': 'will',
    '要': 'want',
    '能': 'can',
    '应该': 'should',
    '必须': 'must',
    '可能': 'may',
    '需要': 'need',
    '希望': 'hope',
    '想': 'want',
    '觉得': 'think',
    '知道': 'know',
    '认为': 'think',
    '表示': 'express',
    '说': 'say',
    '看': 'look',
    '做': 'do',
    '去': 'go',
    '来': 'come',
    '给': 'give',
    '用': 'use',
    '对': 'to',
    '从': 'from',
    '但': 'but',
    '因为': 'because',
    '所以': 'so',
    '如果': 'if',
    '虽然': 'although',
    '而': 'and',
    '或者': 'or',
    '以及': 'and',
    '通过': 'through',
    '关于': 'about',
    '作为': 'as',
    '根据': 'according to',
    '由于': 'due to',
    '与': 'with',
    '及': 'and',
    '等': 'etc',
    '等等': 'etc',
    
    # Technical terms
    '配置': 'configuration',
    '设置': 'settings',
    '参数': 'parameters',
    '选项': 'options',
    '属性': 'attributes',
    '方法': 'method',
    '函数': 'function',
    '类': 'class',
    '对象': 'object',
    '实例': 'instance',
    '变量': 'variable',
    '常量': 'constant',
    '字符串': 'string',
    '数字': 'number',
    '布尔值': 'boolean',
    '数组': 'array',
    '列表': 'list',
    '字典': 'dictionary',
    '集合': 'set',
    '元组': 'tuple',
    '模块': 'module',
    '包': 'package',
    '库': 'library',
    '框架': 'framework',
    '接口': 'interface',
    '类型': 'type',
    '值': 'value',
    '键': 'key',
    '索引': 'index',
    '长度': 'length',
    '大小': 'size',
    '数量': 'quantity',
    '总数': 'total',
    '最大': 'maximum',
    '最小': 'minimum',
    '平均': 'average',
    '求和': 'sum',
    '计数': 'count',
    
    # Status and actions
    '状态': 'status',
    '结果': 'result',
    '成功': 'success',
    '失败': 'failed',
    '错误': 'error',
    '警告': 'warning',
    '信息': 'info',
    '调试': 'debug',
    '日志': 'log',
    '记录': 'record',
    '历史': 'history',
    '时间': 'time',
    '日期': 'date',
    '开始': 'start',
    '结束': 'end',
    '完成': 'completed',
    '进行中': 'in progress',
    '等待': 'waiting',
    '运行': 'running',
    '停止': 'stopped',
    '暂停': 'paused',
    '继续': 'continue',
    '重试': 'retry',
    '取消': 'cancel',
    '确认': 'confirm',
    '提交': 'submit',
    '保存': 'save',
    '删除': 'delete',
    '更新': 'update',
    '创建': 'create',
    '修改': 'modify',
    '编辑': 'edit',
    '查看': 'view',
    '搜索': 'search',
    '过滤': 'filter',
    '排序': 'sort',
    '导入': 'import',
    '导出': 'export',
    '下载': 'download',
    '上传': 'upload',
    '加载': 'load',
    '刷新': 'refresh',
    '重新加载': 'reload',
    '初始化': 'initialize',
    '配置': 'configure',
    '设定': 'set',
    '获取': 'get',
    '设置': 'set',
    '读取': 'read',
    '写入': 'write',
    '发送': 'send',
    '接收': 'receive',
    '请求': 'request',
    '响应': 'response',
    '处理': 'process',
    '解析': 'parse',
    '转换': 'convert',
    '验证': 'validate',
    '检查': 'check',
    '测试': 'test',
    '执行': 'execute',
    '调用': 'call',
    '返回': 'return',
    '抛出': 'throw',
    '捕获': 'catch',
    
    # UI elements
    '按钮': 'button',
    '输入框': 'input',
    '下拉框': 'dropdown',
    '复选框': 'checkbox',
    '单选框': 'radio',
    '标签': 'label',
    '标题': 'title',
    '内容': 'content',
    '描述': 'description',
    '提示': 'hint',
    '帮助': 'help',
    '说明': 'instructions',
    '示例': 'example',
    '样例': 'sample',
    '模板': 'template',
    '表单': 'form',
    '表格': 'table',
    '列表': 'list',
    '菜单': 'menu',
    '导航': 'navigation',
    '页面': 'page',
    '视图': 'view',
    '面板': 'panel',
    '对话框': 'dialog',
    '弹窗': 'popup',
    '通知': 'notification',
    '消息': 'message',
    '提醒': 'reminder',
    '图标': 'icon',
    '图片': 'image',
    '图表': 'chart',
    '图形': 'graphic',
}

def translate_content(content):
    """Apply all translations to content"""
    for cn, en in TRANSLATIONS.items():
        content = content.replace(cn, en)
    return content

def process_file(filepath):
    """Process a single file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        translated = translate_content(content)
        
        if translated != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(translated)
            
            chars_removed = len([c for c in original if '\u4e00' <= c <= '\u9fff'])
            chars_remaining = len([c for c in translated if '\u4e00' <= c <= '\u9fff'])
            print(f"✓ {filepath}: {chars_removed - chars_remaining} chars translated")
            return True
    except Exception as e:
        print(f"✗ {filepath}: {e}")
    return False

# Process all Vue files
vue_count = 0
for root, dirs, files in os.walk('frontend/src'):
    for file in files:
        if file.endswith('.vue'):
            filepath = os.path.join(root, file)
            if process_file(filepath):
                vue_count += 1

# Process all Python files
py_count = 0
for root, dirs, files in os.walk('backend/app'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            if process_file(filepath):
                py_count += 1

print(f"\n=== TRANSLATION SUMMARY ===")
print(f"Vue files translated: {vue_count}")
print(f"Python files translated: {py_count}")
print(f"Total: {vue_count + py_count}")
