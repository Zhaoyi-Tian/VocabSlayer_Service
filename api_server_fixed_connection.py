#!/usr/bin/env python3
"""
创建一个新版本的api_server.py，使用独立连接
"""
import os
import sys
import json
import hashlib
import logging
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from flask_cors import CORS
import tempfile
import time

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'vocabulary_db',
    'user': 'openEuler',
    'password': 'Qq13896842746',
    'connect_timeout': 5
}

def get_db_connection():
    """每次都创建新的数据库连接"""
    try:
        import psycopg2
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = True  # 设置自动提交
        return conn
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        return None

def execute_db_query(query, params=None, fetch=True):
    """执行数据库查询的辅助函数"""
    conn = get_db_connection()
    if not conn:
        raise Exception("无法连接到数据库")

    cur = None
    try:
        cur = conn.cursor()
        if params:
            cur.execute(query, params)
        else:
            cur.execute(query)

        if fetch:
            if cur.description:
                return cur.fetchall()
            return None
        else:
            return cur.rowcount if cur.rowcount > -1 else None
    finally:
        if cur:
            cur.close()
        conn.close()

# 创建Flask应用
app = Flask(__name__)
CORS(app, origins=["*"], methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

# 配置
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

# 健康检查端点
@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    try:
        # 测试数据库连接
        result = execute_db_query("SELECT 1")

        modules_status = {
            "database": True,
            "document_parser": True,
            "question_generator": True,
            "text_processor": True
        }

        return jsonify({
            'message': 'VocabSlayer API Server is running',
            'modules': modules_status,
            'status': 'ok',
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.%f')
        })
    except Exception as e:
        return jsonify({
            'message': 'VocabSlayer API Server is running',
            'modules': {
                'database': False,
                'document_parser': True,
                'question_generator': True,
                'text_processor': True
            },
            'status': 'warning',
            'error': str(e),
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.%f')
        })

# 获取题库列表
@app.route('/api/banks/<int:user_id>', methods=['GET'])
def get_banks(user_id):
    """获取用户的所有题库"""
    try:
        banks = execute_db_query(
            f"SELECT * FROM user_custom_banks WHERE user_id = {user_id} ORDER BY created_at DESC"
        )

        bank_list = []
        for bank in banks:
            bank_list.append({
                'bank_id': bank[0],
                'user_id': bank[1],
                'bank_name': bank[2],
                'source_file': bank[3],
                'description': bank[4],
                'question_count': bank[5],
                'created_at': bank[6].isoformat() if bank[6] else None,
                'file_hash': bank[7],
                'processing_status': bank[8]
            })

        return jsonify({'success': True, 'banks': bank_list})
    except Exception as e:
        logger.error(f"获取题库列表失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 60)
    print("VocabSlayer 自定义题库API服务器")
    print("=" * 60)
    print("注意：使用独立数据库连接模式")
    print("=" * 60)

    # 测试数据库连接
    conn = get_db_connection()
    if conn:
        print("✓ 数据库连接成功")
        conn.close()
    else:
        print("✗ 数据库连接失败")

    # 启动服务器
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)