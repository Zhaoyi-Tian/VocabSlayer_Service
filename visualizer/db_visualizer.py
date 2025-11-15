#!/usr/bin/env python3
"""
openGauss数据库可视化工具
提供Web界面访问和查看数据库内容
"""
import os
import sys
from datetime import datetime
import json

# 添加项目路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(current_dir, 'VocabSlayer_update'))
sys.path.insert(0, os.path.join(current_dir, 'VocabSlayer_update_servier'))

try:
    import py_opengauss
    import psycopg2
    from flask import Flask, render_template_string, request, jsonify
    import pandas as pd
    import plotly.graph_objs as go
    import plotly.utils
    HAS_DEPS = True
except ImportError as e:
    print(f"缺少依赖: {e}")
    HAS_DEPS = False

# Flask应用
app = Flask(__name__)

# 数据库连接配置
DB_CONFIG = {
    'host': '10.129.211.118',
    'port': 5432,
    'database': 'vocabulary_db',
    'user': 'vocabuser',
    'password': 'OpenEuler123!'
}

# HTML模板
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>VocabSlayer - openGauss数据库可视化</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: #2c3e50; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
        .card { background: white; padding: 20px; margin: 10px 0; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .stats { display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 20px; }
        .stat-card { background: #3498db; color: white; padding: 20px; border-radius: 5px; text-align: center; min-width: 150px; }
        .stat-value { font-size: 36px; font-weight: bold; }
        .stat-label { font-size: 14px; margin-top: 5px; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #f2f2f2; }
        tr:hover { background-color: #f5f5f5; }
        .nav { margin-bottom: 20px; }
        .nav button { margin-right: 10px; padding: 10px 20px; border: none; background: #3498db; color: white; cursor: pointer; border-radius: 3px; }
        .nav button:hover { background: #2980b9; }
        .nav button.active { background: #e74c3c; }
        .chart-container { margin: 20px 0; }
        .pagination { margin: 20px 0; text-align: center; }
        .pagination button { margin: 0 5px; padding: 5px 10px; cursor: pointer; }
        .info { color: #666; font-size: 14px; margin-top: 10px; }
        .error { color: #e74c3c; padding: 10px; background: #ffe6e6; border-radius: 3px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 VocabSlayer - openGauss数据库可视化</h1>
            <p>数据库: {{ db_name }} | 用户: {{ db_user }} | 连接时间: {{ connect_time }}</p>
        </div>

        {% if error %}
        <div class="card error">
            <h3>连接错误</h3>
            <p>{{ error }}</p>
        </div>
        {% else %}

        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{{ stats.total_users }}</div>
                <div class="stat-label">总用户数</div>
            </div>
            <div class="stat-card" style="background: #2ecc71;">
                <div class="stat-value">{{ stats.total_vocab }}</div>
                <div class="stat-label">词汇总数</div>
            </div>
            <div class="stat-card" style="background: #e74c3c;">
                <div class="stat-value">{{ stats.total_records }}</div>
                <div class="stat-label">学习记录</div>
            </div>
            <div class="stat-card" style="background: #f39c12;">
                <div class="stat-value">{{ stats.total_custom_banks }}</div>
                <div class="stat-label">自定义题库</div>
            </div>
        </div>

        <div class="nav">
            <button onclick="showTable('users')" class="{% if active_table == 'users' %}active{% endif %}">用户表</button>
            <button onclick="showTable('vocabulary')" class="{% if active_table == 'vocabulary' %}active{% endif %}">词汇表</button>
            <button onclick="showTable('learning_records')" class="{% if active_table == 'learning_records' %}active{% endif %}">学习记录</button>
            <button onclick="showTable('review_list')" class="{% if active_table == 'review_list' %}active{% endif %}">复习列表</button>
            <button onclick="showTable('custom_banks')" class="{% if active_table == 'custom_banks' %}active{% endif %}">自定义题库</button>
            <button onclick="showChart()" class="{% if active_table == 'chart' %}active{% endif %}">数据图表</button>
        </div>

        {% if active_table == 'chart' %}
        <div class="card">
            <h2>📈 数据可视化图表</h2>
            <div class="chart-container">
                {{ chart_html|safe }}
            </div>
        </div>
        {% else %}
        <div class="card">
            <h2>📋 {{ table_name }} - 数据预览</h2>
            <div class="info">总记录数: {{ total_records }} | 显示前100条记录</div>
            <div style="overflow-x: auto;">
                {{ table_html|safe }}
            </div>
        </div>
        {% endif %}

        {% endif %}
    </div>

    <script>
        function showTable(tableName) {
            window.location.href = `/?table=${tableName}`;
        }

        function showChart() {
            window.location.href = '/?table=chart';
        }

        // 自动刷新
        setTimeout(() => {
            window.location.reload();
        }, 60000);  // 60秒刷新一次
    </script>
</body>
</html>
"""

def get_db_connection():
    """获取数据库连接"""
    try:
        # 尝试使用py-opengauss
        conn = py_opengauss.connect(**DB_CONFIG)
        return conn
    except:
        try:
            # 降级到psycopg2
            conn = psycopg2.connect(**DB_CONFIG)
            return conn
        except Exception as e:
            return None

def get_database_stats():
    """获取数据库统计信息"""
    conn = get_db_connection()
    if not conn:
        return None

    stats = {}
    try:
        cur = conn.cursor()

        # 用户数
        cur.execute("SELECT COUNT(*) FROM users")
        stats['total_users'] = cur.fetchone()[0]

        # 词汇数
        cur.execute("SELECT COUNT(*) FROM vocabulary")
        stats['total_vocab'] = cur.fetchone()[0]

        # 学习记录数
        cur.execute("SELECT COUNT(*) FROM user_learning_records")
        stats['total_records'] = cur.fetchone()[0]

        # 自定义题库数
        try:
            cur.execute("SELECT COUNT(*) FROM user_custom_banks")
            stats['total_custom_banks'] = cur.fetchone()[0]
        except:
            stats['total_custom_banks'] = 0

        cur.close()
    except Exception as e:
        print(f"获取统计信息失败: {e}")
    finally:
        conn.close()

    return stats

def get_table_data(table_name, limit=100):
    """获取表数据"""
    conn = get_db_connection()
    if not conn:
        return None, None, None

    try:
        # 获取表结构
        cur = conn.cursor()

        # 表映射
        table_mapping = {
            'users': ('users', ['user_id', 'username', 'created_at', 'last_login'], '用户表'),
            'vocabulary': ('vocabulary', ['vocab_id', 'english', 'chinese', 'japanese', 'level'], '词汇表'),
            'learning_records': ('user_learning_records', ['record_id', 'user_id', 'vocab_id', 'star', 'review_count', 'last_reviewed'], '学习记录表'),
            'review_list': ('user_review_list', ['review_id', 'user_id', 'vocab_id', 'weight', 'next_review_time'], '复习列表'),
            'custom_banks': ('user_custom_banks', ['bank_id', 'user_id', 'bank_name', 'question_count', 'created_at'], '自定义题库')
        }

        if table_name not in table_mapping:
            return None, None, None

        actual_table, columns, display_name = table_mapping[table_name]

        # 获取数据
        query = f"SELECT {', '.join(columns)} FROM {actual_table}"
        if table_name != 'vocabulary':
            query += f" ORDER BY created_at DESC"
        query += f" LIMIT {limit}"

        cur.execute(query)
        rows = cur.fetchall()

        # 生成HTML表格
        table_html = '<table>\n<tr>'
        for col in columns:
            table_html += f'<th>{col}</th>'
        table_html += '</tr>\n'

        for row in rows:
            table_html += '<tr>'
            for i, value in enumerate(row):
                # 格式化时间
                if isinstance(value, datetime):
                    value = value.strftime('%Y-%m-%d %H:%M:%S')
                # 截断长文本
                if isinstance(value, str) and len(value) > 100:
                    value = value[:100] + '...'
                table_html += f'<td>{value or "-"}</td>'
            table_html += '</tr>\n'

        table_html += '</table>'

        # 获取总数
        cur.execute(f"SELECT COUNT(*) FROM {actual_table}")
        total = cur.fetchone()[0]

        cur.close()
        return display_name, table_html, total

    except Exception as e:
        print(f"获取表数据失败: {e}")
        return None, None, None
    finally:
        conn.close()

def create_chart():
    """创建数据图表"""
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cur = conn.cursor()

        # 1. 用户学习进度分布
        cur.execute("""
            SELECT u.username, COUNT(lr.record_id) as study_count
            FROM users u
            LEFT JOIN user_learning_records lr ON u.user_id = lr.user_id
            GROUP BY u.username
            ORDER BY study_count DESC
            LIMIT 10
        """)
        user_progress = cur.fetchall()

        # 2. 词汇难度分布
        cur.execute("""
            SELECT level, COUNT(*) as count
            FROM vocabulary
            GROUP BY level
            ORDER BY level
        """)
        vocab_levels = cur.fetchall()

        cur.close()

        # 创建图表HTML
        chart_html = """
        <div style="display: flex; gap: 20px; flex-wrap: wrap;">
            <div style="flex: 1; min-width: 400px;">
                <h3>用户学习进度TOP10</h3>
        """

        # 用户学习进度柱状图
        if user_progress:
            chart_html += '<table style="width: 100%;">'
            chart_html += '<tr><th>用户名</th><th>学习数量</th><th>进度条</th></tr>'
            max_count = max([x[1] for x in user_progress]) if user_progress else 1
            for username, count in user_progress:
                width = (count / max_count * 100) if max_count > 0 else 0
                chart_html += f'''
                <tr>
                    <td>{username}</td>
                    <td>{count}</td>
                    <td>
                        <div style="background: #ecf0f1; border-radius: 3px; overflow: hidden;">
                            <div style="background: #3498db; width: {width}%; height: 20px;"></div>
                        </div>
                    </td>
                </tr>
                '''
            chart_html += '</table>'

        chart_html += '</div><div style="flex: 1; min-width: 400px;"><h3>词汇难度分布</h3>'

        # 词汇难度饼图（简单文本版）
        if vocab_levels:
            chart_html += '<table style="width: 100%;">'
            chart_html += '<tr><th>难度等级</th><th>词汇数量</th><th>占比</th></tr>'
            total_vocab = sum([x[1] for x in vocab_levels])
            for level, count in vocab_levels:
                percentage = (count / total_vocab * 100) if total_vocab > 0 else 0
                color = ['#2ecc71', '#f39c12', '#e74c3c'][level-1] if level <= 3 else '#95a5a6'
                chart_html += f'''
                <tr>
                    <td><span style="display: inline-block; width: 12px; height: 12px; background: {color}; border-radius: 50%; margin-right: 5px;"></span>Level {level}</td>
                    <td>{count}</td>
                    <td>{percentage:.1f}%</td>
                </tr>
                '''
            chart_html += '</table>'

        chart_html += '</div></div>'

        # 3. 数据库表大小信息
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
            """)
            table_sizes = cur.fetchall()
            cur.close()
            conn.close()

            chart_html += '''
            <div style="margin-top: 30px;">
                <h3>数据库表存储大小</h3>
                <table style="width: 100%;">
                    <tr><th>表名</th><th>存储大小</th></tr>
            '''
            for schema, table, size in table_sizes:
                chart_html += f'<tr><td>{table}</td><td>{size}</td></tr>'
            chart_html += '</table></div>'

        return chart_html

    except Exception as e:
        print(f"创建图表失败: {e}")
        return None

@app.route('/')
def index():
    """主页"""
    if not HAS_DEPS:
        return render_template_string(HTML_TEMPLATE,
            error="缺少必要的依赖包，请安装: pip install py-opengauss psycopg2-binary pandas flask plotly")

    table_name = request.args.get('table', 'users')
    error = None
    stats = None
    table_html = None
    total_records = 0
    table_display = '用户表'
    chart_html = None

    try:
        # 获取统计信息
        stats = get_database_stats()

        if table_name == 'chart':
            chart_html = create_chart()
        else:
            # 获取表数据
            result = get_table_data(table_name)
            if result:
                table_display, table_html, total_records = result
    except Exception as e:
        error = str(e)

    return render_template_string(HTML_TEMPLATE,
        db_name=DB_CONFIG['database'],
        db_user=DB_CONFIG['user'],
        connect_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        error=error,
        stats=stats or {},
        active_table=table_name,
        table_name=table_display,
        table_html=table_html or '',
        total_records=total_records or 0,
        chart_html=chart_html or ''
    )

@app.route('/api/stats')
def api_stats():
    """API - 获取统计信息"""
    stats = get_database_stats()
    return jsonify(stats or {})

@app.route('/api/table/<table_name>')
def api_table(table_name):
    """API - 获取表数据"""
    _, table_html, total = get_table_data(table_name)
    return jsonify({
        'table_html': table_html,
        'total_records': total
    })

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 VocabSlayer openGauss数据库可视化工具")
    print("=" * 60)
    print(f"数据库: {DB_CONFIG['database']}")
    print(f"地址: {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    print("=" * 60)
    print("访问地址: http://localhost:5000")
    print("按 Ctrl+C 停止服务")
    print("=" * 60)

    app.run(host='0.0.0.0', port=5000, debug=False)