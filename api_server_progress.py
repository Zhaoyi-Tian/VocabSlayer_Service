#!/usr/bin/env python3
"""
带进度推送的VocabSlayer自定义题库API服务器
"""
import os
import sys
import json
import hashlib
import tempfile
from datetime import datetime
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from werkzeug.utils import secure_filename
import logging
import threading
import uuid
from queue import Queue, Empty

# 设置路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
sys.path.insert(0, os.path.join(current_dir, 'common'))

# 导入进度管理器
from progress_manager import progress_manager

# 配置
app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB
UPLOAD_FOLDER = tempfile.mkdtemp(prefix='vocabslayer_')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 配置日志
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
    """获取数据库连接"""
    try:
        import psycopg2
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = True
        return conn
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        return None

# 导入文档处理模块
ParserFactory = None
TextProcessor = None
QuestionGenerator = None

try:
    from common.document_parser import ParserFactory
    logger.info("✓ 导入文档解析器")
except ImportError as e:
    logger.warning(f"✗ 无法导入文档解析器: {e}")

try:
    from common.text_processor import TextProcessor
    logger.info("✓ 导入文本处理器")
except ImportError as e:
    logger.warning(f"✗ 无法导入文本处理器: {e}")

try:
    from common.question_generator import QuestionGenerator
    logger.info("✓ 导入题目生成器")
except ImportError as e:
    logger.warning(f"✗ 无法导入题目生成器: {e}")

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    modules = {
        'document_parser': ParserFactory is not None,
        'text_processor': TextProcessor is not None,
        'question_generator': QuestionGenerator is not None,
        'database': get_db_connection() is not None
    }

    return jsonify({
        'status': 'ok',
        'message': 'VocabSlayer API Server is running',
        'timestamp': datetime.now().isoformat(),
        'modules': modules
    })

@app.route('/api/progress/<task_id>', methods=['GET'])
def progress_stream(task_id: str):
    """SSE进度流"""
    def generate():
        queue = progress_manager.get_task_queue(task_id)
        if not queue:
            yield f"data: {json.dumps({'error': 'Task not found'})}\n\n"
            return

        try:
            while True:
                try:
                    # 从队列获取消息
                    message = queue.get(timeout=1)  # 1秒超时

                    # 转换为SSE格式
                    yield f"data: {json.dumps(message)}\n\n"

                    # 如果任务完成或出错，结束流
                    if message.get('status') in ['completed', 'error']:
                        yield f"event: close\ndata: {json.dumps({'status': message['status']})}\n\n"
                        break

                except Empty:
                    # 发送心跳
                    yield f": heartbeat\n\n"

        except Exception as e:
            logger.error(f"进度流错误: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Cache-Control'
        }
    )

@app.route('/api/upload', methods=['POST'])
def upload_document():
    """上传文档并生成题库"""
    try:
        # 检查文件
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400

        # 获取参数
        user_id = request.form.get('user_id', type=int)
        bank_name = request.form.get('bank_name', '未命名题库')
        description = request.form.get('description', '')
        api_key = request.form.get('api_key', '')
        chunk_size = request.form.get('chunk_size', 500, type=int)
        questions_per_chunk = request.form.get('questions_per_chunk', 2, type=int)

        # 生成任务ID
        task_id = str(uuid.uuid4())

        # 创建任务
        progress_manager.create_task(task_id, file.filename, user_id)

        # 保存文件
        filename = secure_filename(file.filename)
        logger.info(f"原始文件名: {file.filename}, 安全文件名: {filename}")

        # 如果文件名被过滤掉了扩展名，保留原始扩展名
        if '.' in file.filename and '.' not in filename:
            ext = os.path.splitext(file.filename)[1]
            filename = filename + ext
            logger.info(f"添加扩展名后: {filename}")

        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        logger.info(f"文件上传成功: {filename}, 用户ID: {user_id}")

        # 异步处理文档
        def process_document_async():
            try:
                # 更新进度：开始解析
                progress_manager.update_progress(
                    task_id=task_id,
                    status='processing',
                    progress=5,
                    message='开始解析文档...',
                    current_step='parsing'
                )

                # 解析文档
                text_content = ""
                if ParserFactory:
                    parser = ParserFactory.get_parser(file_path)
                    text_content = parser.extract_text(file_path)
                    logger.info(f"文档解析完成，提取文本: {len(text_content)} 字符")

                # 更新进度：解析完成
                progress_manager.update_progress(
                    task_id=task_id,
                    status='processing',
                    progress=15,
                    message=f'解析完成，文档长度: {len(text_content)} 字符',
                    current_step='parsing_complete'
                )

                # 检查重复
                file_hash = hashlib.md5(text_content.encode()).hexdigest()

                # 更新进度：处理中
                progress_manager.update_progress(
                    task_id=task_id,
                    status='processing',
                    progress=20,
                    message='检查文档是否已处理...',
                    current_step='checking'
                )

                # 处理文档
                if ParserFactory and TextProcessor and QuestionGenerator and api_key and api_key != 'test_key' and text_content:
                    # 数据库连接
                    conn = get_db_connection()
                    if not conn:
                        progress_manager.error_task(task_id, "数据库连接失败")
                        return

                    cur = conn.cursor()

                    # 创建题库
                    cur.execute(f"""
                        INSERT INTO user_custom_banks
                        (user_id, bank_name, source_file, description, file_hash, processing_status, question_count)
                        VALUES ({user_id}, '{bank_name}', '{filename}', '{description}', '{file_hash}', 'processing', 0)
                        RETURNING bank_id
                    """)
                    bank_id = cur.fetchone()[0]

                    # 更新进度：开始生成题目
                    progress_manager.update_progress(
                        task_id=task_id,
                        status='processing',
                        progress=25,
                        message='开始生成题目...',
                        current_step='generating',
                        details={'bank_id': bank_id}
                    )

                    # 处理文本
                    text_processor = TextProcessor(chunk_size=500, chunk_overlap=100)
                    text_content = text_processor.clean_text(text_content)
                    text_chunks = text_processor.smart_chunk_with_context(text_content)

                    if text_chunks:
                        question_generator = QuestionGenerator(api_key=api_key)
                        all_questions = []

                        for i, chunk in enumerate(text_chunks):
                            # 更新进度
                            progress = 30 + (65 * i // len(text_chunks))
                            progress_manager.update_progress(
                                task_id=task_id,
                                status='processing',
                                progress=progress,
                                message=f'处理第 {i+1}/{len(text_chunks)} 个文本块...',
                                current_step='processing_chunk',
                                details={'chunk_index': i+1, 'total_chunks': len(text_chunks)}
                            )

                            # 生成题目
                            questions = question_generator.generate_questions(
                                chunk_text=chunk.content,
                                chunk_index=i,
                                num_questions=min(3, max(1, questions_per_chunk))
                            )

                            # 保存题目
                            for q in questions:
                                original_text = chunk.content[:500] + "..." if len(chunk.content) > 500 else chunk.content
                                answer_text = f"【AI答案】\n{q.answer}\n\n【原文参考】\n{original_text}"

                                cur.execute(
                                    """
                                    INSERT INTO user_custom_questions
                                    (bank_id, question_text, answer_text, question_type)
                                    VALUES (%s, %s, %s, %s)
                                    """,
                                    (bank_id, q.question, answer_text, 'Q&A')
                                )

                                all_questions.append(q)

                    # 更新题库状态
                    cur.execute(
                        f"UPDATE user_custom_banks SET processing_status = 'completed', question_count = {len(all_questions)} WHERE bank_id = {bank_id}"
                    )

                    conn.close()

                    # 完成
                    progress_manager.complete_task(task_id, {
                        'bank_id': bank_id,
                        'question_count': len(all_questions),
                        'message': f'处理完成，共生成 {len(all_questions)} 道题目'
                    })
                else:
                    # 示例题目模式
                    progress_manager.complete_task(task_id, {
                        'message': '文档已接收，但需要API密钥来生成题目'
                    })

                # 清理文件
                if os.path.exists(file_path):
                    os.remove(file_path)

            except Exception as e:
                logger.error(f"处理文档失败: {e}")
                progress_manager.error_task(task_id, str(e))
                if os.path.exists(file_path):
                    os.remove(file_path)

        # 启动异步处理
        thread = threading.Thread(target=process_document_async)
        thread.daemon = True
        thread.start()

        # 返回任务ID
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '文件已上传，正在处理中...',
            'progress_url': f'/api/progress/{task_id}'
        })

    except Exception as e:
        logger.error(f"上传失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# 其他端点保持不变...

if __name__ == '__main__':
    print("=" * 60)
    print("VocabSlayer 自定义题库API服务器")
    print("=" * 60)
    print("支持实时进度推送")
    print("=" * 60)

    # 测试数据库连接
    if get_db_connection():
        print("✓ 数据库连接成功")
    else:
        print("✗ 数据库连接失败")

    # 创建上传目录
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # 启动服务器
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True, use_reloader=True)