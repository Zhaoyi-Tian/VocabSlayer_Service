#!/bin/bash

echo "启动 VocabSlayer openGauss 数据库可视化工具..."
echo "================================================"

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 Python3"
    exit 1
fi

# 安装必要的依赖（如果未安装）
echo "检查并安装依赖..."
pip3 install -q flask py-opengauss psycopg2-binary pandas plotly 2>/dev/null

# 检查数据库连接
echo -n "测试数据库连接..."
python3 -c "
import py_opengauss
try:
    conn = py_opengauss.connect(
        host='10.129.211.118',
        port='5432',
        database='vocabulary_db',
        user='vocabuser',
        password='OpenEuler123!'
    )
    conn.close()
    print(' ✓ 成功')
except Exception as e:
    print(f' ✗ 失败: {e}')
    exit(1)
"

echo ""
echo "================================================"
echo "启动Web服务器..."
echo "访问地址: http://localhost:5000"
echo "如果从其他机器访问，请使用: http://$(hostname -I | awk '{print $1}'):5000"
echo "================================================"

# 启动服务
cd /home/openEuler/openGauss/VocabSlayer_servier/VocabSlayer_update_servier/visualizer
python3 db_visualizer.py