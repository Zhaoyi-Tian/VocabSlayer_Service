#!/usr/bin/env python3
"""
应用更新到api_server.py
"""
import os
import shutil

# 读取progress_manager.py的内容
with open('progress_manager.py', 'r') as f:
    manager_content = f.read()

# 将进度管理器代码插入到api_server.py的合适位置
with open('api_server.py', 'r') as f:
    content = f.read()

# 在导入部分添加progress_manager
if 'from progress_manager import progress_manager' not in content:
    # 找到插入位置
    insert_pos = content.find('sys.path.insert(0, os.path.join(current_dir, \'common\'))')
    if insert_pos > 0:
        insert_pos = content.find('\n', insert_pos)
        content = content[:insert_pos+1] + '\n' + manager_content + content[insert_pos+1:]

# 添加必要的导入
if 'from flask import Response' not in content:
    content = content.replace('from flask import Flask, request, jsonify',
                                     'from flask import Flask, request, jsonify, Response, stream_with_context')
if 'import threading' not in content:
    content = content.replace('import logging', 'import logging\nimport threading')
if 'import uuid' not in content:
    content = content.replace('import logging\nimport threading', 'import logging\nimport threading\nimport uuid')
if 'from queue import Queue, Empty' not in content:
    content = content.replace('import uuid', 'import uuid\nfrom queue import Queue, Empty')

# 写回文件
with open('api_server.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✓ 已更新 api_server.py，添加了进度推送功能")