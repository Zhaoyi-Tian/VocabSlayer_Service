#!/usr/bin/env python3
"""
VocabSlayer 自定义题库API服务器
完整功能版本 - 支持文档解析、AI生成题目、实时进度推送
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

"""
进度管理器 - 管理文件处理任务的进度
"""
import json
import time
from typing import Dict, Optional
from dataclasses import dataclass, asdict
from queue import Queue, Empty
import logging

logger = logging.getLogger(__name__)

@dataclass
class ProgressUpdate:
    """进度更新消息"""
    task_id: str
    status: str  # 'processing', 'completed', 'error'
    progress: int  # 0-100
    message: str
    current_step: str
    details: Optional[dict] = None
    timestamp: float = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()

class ProgressManager:
    """进度管理器"""

    def __init__(self):
        self.task_queues: Dict[str, Queue] = {}
        self.tasks: Dict[str, dict] = {}
        self.cleanup_interval = 300  # 5分钟清理一次过期任务

    def create_task(self, task_id: str, filename: str, user_id: int) -> dict:
        """创建新任务"""
        self.tasks[task_id] = {
            'task_id': task_id,
            'filename': filename,
            'user_id': user_id,
            'created_at': time.time(),
            'updated_at': time.time()
        }

        # 创建任务的消息队列
        if task_id not in self.task_queues:
            self.task_queues[task_id] = Queue(maxsize=100)

        logger.info(f"创建任务: {task_id}, 文件: {filename}")
        return self.tasks[task_id]

    def update_progress(self, task_id: str, status: str, progress: int,
                      message: str, current_step: str = "", details: dict = None):
        """更新任务进度"""
        if task_id not in self.task_queues:
            logger.warning(f"任务不存在: {task_id}")
            return

        try:
            update = ProgressUpdate(
                task_id=task_id,
                status=status,
                progress=progress,
                message=message,
                current_step=current_step,
                details=details
            )

            # 发送更新到队列
            self.task_queues[task_id].put_nowait(asdict(update))

            # 更新任务信息
            if task_id in self.tasks:
                self.tasks[task_id]['updated_at'] = time.time()
                self.tasks[task_id]['status'] = status

            logger.info(f"进度更新 [{task_id}]: {progress}% - {message}")

        except Exception as e:
            logger.error(f"更新进度失败 [{task_id}]: {e}")

    def complete_task(self, task_id: str, result: dict = None):
        """完成任务"""
        self.update_progress(
            task_id=task_id,
            status='completed',
            progress=100,
            message='处理完成',
            details=result
        )

    def error_task(self, task_id: str, error_message: str):
        """任务出错"""
        self.update_progress(
            task_id=task_id,
            status='error',
            progress=0,
            message=f'处理失败: {error_message}'
        )

    def get_task_queue(self, task_id: str) -> Optional[Queue]:
        """获取任务的消息队列"""
        return self.task_queues.get(task_id)

    def cleanup_old_tasks(self):
        """清理过期任务（超过5分钟）"""
        current_time = time.time()
        expired_tasks = []

        for task_id, task in self.tasks.items():
            if current_time - task.get('updated_at', 0) > self.cleanup_interval:
                expired_tasks.append(task_id)

        for task_id in expired_tasks:
            if task_id in self.task_queues:
                del self.task_queues[task_id]
            if task_id in self.tasks:
                del self.tasks[task_id]
            logger.info(f"清理过期任务: {task_id}")

# 全局进度管理器实例
progress_manager = ProgressManager()


# API端点
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

@app.route('/api/test-sse', methods=['GET'])
def test_sse():
    """测试SSE端点"""
    logger.info("测试SSE端点被调用")

    def generate():
        import time
        for i in range(5):
            data = {
                'progress': (i + 1) * 20,
                'message': f'测试消息 {i+1}',
                'status': 'processing' if i < 4 else 'completed'
            }
            yield f"data: {json.dumps(data)}\n\n"
            time.sleep(1)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*'
        }
    )

@app.route('/api/progress/<task_id>', methods=['GET'])
def progress_stream(task_id: str):
    """SSE进度流"""
    logger.info(f"SSE连接请求: task_id={task_id}")

    queue = progress_manager.get_task_queue(task_id)
    if not queue:
        logger.warning(f"Task not found: {task_id}")
        return Response(
            f"data: {json.dumps({'error': 'Task not found'})}\n\n",
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Access-Control-Allow-Origin': '*'
            }
        )

    logger.info(f"找到任务队列: {task_id}")

    def generate():
        try:
            logger.info(f"开始SSE流: {task_id}")

            # 发送连接确认消息
            connection_msg = {
                'task_id': task_id,
                'status': 'connected',
                'progress': 0,
                'message': '已连接到进度监控',
                'timestamp': time.time()
            }
            yield f"data: {json.dumps(connection_msg)}\n\n"
            logger.info(f"SSE连接已建立: {task_id}")

            while True:
                try:
                    # 从队列获取消息
                    message = queue.get(timeout=0.1)  # 减少超时时间
                    if not message:
                        continue

                    # logger.debug(f"SSE发送消息: {task_id} - {message.get('message', '')[:50]}...")  # 改为debug级别，减少日志

                    # 转换为SSE格式并立即发送
                    data_str = json.dumps(message, ensure_ascii=False)
                    yield f"data: {data_str}\n\n"

                    # 如果任务完成或出错，结束流
                    if message.get('status') in ['completed', 'error']:
                        logger.info(f"任务结束: {task_id} - {message.get('status')}")
                        yield f"event: close\ndata: {json.dumps({'status': message['status']}, ensure_ascii=False)}\n\n"
                        break

                except Empty:
                    # 队列为空时不发送心跳，减少网络流量
                    # 客户端会保持连接直到收到完成或错误消息
                    continue
                except Exception as e:
                    logger.error(f"SSE生成器错误: {e}")
                    break

        except GeneratorExit:
            logger.info(f"SSE客户端断开连接: {task_id}")
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
            'Access-Control-Allow-Headers': 'Cache-Control',
            'X-Accel-Buffering': 'no'  # 禁用nginx缓冲
        }
    )

@app.route('/api/banks/<int:user_id>', methods=['GET'])
def get_banks(user_id):
    """获取用户的所有题库"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500

        cur = conn.cursor()
        cur.execute(f"SELECT * FROM user_custom_banks WHERE user_id = {user_id} ORDER BY created_at DESC")
        banks = cur.fetchall()
        conn.close()

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

@app.route('/api/banks/<int:bank_id>/info', methods=['GET'])
def get_bank_info(bank_id):
    """获取单个题库的信息"""
    user_id = request.args.get('user_id', type=int)

    if not user_id:
        return jsonify({'success': False, 'error': 'user_id is required'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500

    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM user_custom_banks WHERE bank_id = {bank_id} AND user_id = {user_id}")
        row = cur.fetchone()

        if row:
            bank_info = {
                'bank_id': row[0],
                'user_id': row[1],
                'bank_name': row[2],
                'source_file': row[3],
                'description': row[4],
                'question_count': row[5],
                'created_at': row[6].isoformat() if row[6] else None,
                'file_hash': row[7],
                'processing_status': row[8]
            }
            return jsonify({'success': True, 'bank_info': bank_info})
        else:
            return jsonify({'success': False, 'error': 'Bank not found'}), 404
    except Exception as e:
        logger.error(f"获取题库信息失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banks/<int:bank_id>/unmastered_questions', methods=['GET'])
def get_unmastered_questions(bank_id):
    """获取题库中未掌握的题目"""
    user_id = request.args.get('user_id', type=int)
    limit = request.args.get('limit', 20, type=int)

    if not user_id:
        return jsonify({'success': False, 'error': 'user_id is required'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500

    try:
        cur = conn.cursor()
        # 获取未掌握的题目（包括从未答过的题目）
        cur.execute(f"""
            SELECT q.question_id, q.question_text, q.question_type,
                   COALESCE(a.is_mastered, FALSE) as is_mastered
            FROM user_custom_questions q
            LEFT JOIN user_custom_answers a
                ON q.question_id = a.question_id AND a.user_id = {user_id}
            WHERE q.bank_id = {bank_id}
            AND (a.is_mastered IS NULL OR a.is_mastered = FALSE)
            ORDER BY q.question_id
            LIMIT {limit}
        """)
        questions = []
        rows = cur.fetchall()
        for row in rows:
            questions.append({
                'question_id': row[0],
                'question_text': row[1],
                'question_type': row[2],
                'bank_id': bank_id
            })

        return jsonify({'success': True, 'questions': questions})
    except Exception as e:
        logger.error(f"获取未掌握题目失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

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

        if not user_id:
            return jsonify({
                'success': False,
                'error': 'user_id is required'
            }), 400

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
                # 给客户端时间连接SSE流
                import time
                time.sleep(1.0)

                # 更新进度：开始解析
                progress_manager.update_progress(
                    task_id=task_id,
                    status='processing',
                    progress=5,
                    message='开始解析文档...',
                    current_step='parsing'
                )

                # 添加小延迟，让前端能看到第一步
                time.sleep(0.5)

                # 解析文档
                text_content = ""
                if ParserFactory:
                    parser = ParserFactory.get_parser(file_path)

                    # 如果是PDF，先获取页数
                    if file_path.lower().endswith('.pdf'):
                        try:
                            import fitz
                            with fitz.open(file_path) as doc:
                                page_count = len(doc)
                                progress_manager.update_progress(
                                    task_id=task_id,
                                    status='processing',
                                    progress=7,
                                    message=f'开始解析PDF文档，共 {page_count} 页...',
                                    current_step='parsing_pdf',
                                    details={'page_count': page_count}
                                )
                                time.sleep(0.5)  # 延迟显示
                        except:
                            pass

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
                time.sleep(0.5)  # 延迟显示

                # 数据库连接
                conn = get_db_connection()
                if not conn:
                    progress_manager.error_task(task_id, "数据库连接失败")
                    return

                cur = conn.cursor()

                # 检查是否已存在
                file_hash = hashlib.md5(text_content.encode()).hexdigest()
                cur.execute(
                    f"SELECT bank_id FROM user_custom_banks WHERE user_id = {user_id} AND file_hash = '{file_hash}'"
                )
                existing = cur.fetchone()

                if existing:
                    # 返回已存在的题库
                    progress_manager.complete_task(task_id, {
                        'bank_id': existing[0],
                        'message': '该文档已经处理过',
                        'already_exists': True
                    })
                    conn.close()
                    os.remove(file_path)
                    return

                # 插入新题库
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

                # 处理文档
                if ParserFactory and TextProcessor and QuestionGenerator and api_key and api_key != 'test_key' and text_content:
                    # 处理文本 - 使用智能分块，每块500字，保留100字上下文
                    progress_manager.update_progress(
                        task_id=task_id,
                        status='processing',
                        progress=26,
                        message='正在清洗和分块文本...',
                        current_step='text_processing'
                    )
                    time.sleep(0.5)  # 延迟显示

                    text_processor = TextProcessor(chunk_size=500, chunk_overlap=100)
                    original_length = len(text_content)
                    text_content = text_processor.clean_text(text_content)
                    cleaned_length = len(text_content)

                    progress_manager.update_progress(
                        task_id=task_id,
                        status='processing',
                        progress=27,
                        message=f'文本清洗完成: {original_length} -> {cleaned_length} 字符',
                        current_step='text_cleaned',
                        details={'original_length': original_length, 'cleaned_length': cleaned_length}
                    )
                    time.sleep(0.5)  # 延迟显示

                    text_chunks = text_processor.smart_chunk_with_context(text_content)
                    chunk_count = len(text_chunks)

                    progress_manager.update_progress(
                        task_id=task_id,
                        status='processing',
                        progress=28,
                        message=f'智能分块完成：{cleaned_length} 字符 -> {chunk_count} 块',
                        current_step='text_chunked',
                        details={'chunk_count': chunk_count}
                    )
                    time.sleep(0.5)  # 延迟显示

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
                            # 注意：generate_questions内部会打印日志
                            questions = question_generator.generate_questions(
                                chunk_text=chunk.content,
                                chunk_index=i,
                                num_questions=min(3, max(1, questions_per_chunk))
                            )

                            # 生成完成后更新进度
                            if questions:
                                progress_manager.update_progress(
                                    task_id=task_id,
                                    status='processing',
                                    progress=progress,
                                    message=f'成功生成 {len(questions)} 道题目',
                                    current_step='generated_questions',
                                    details={'questions_generated': len(questions), 'chunk_index': i+1}
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

# 其他端点（保持原样）
@app.route('/api/banks/<int:bank_id>/questions_with_answers', methods=['GET'])
def get_bank_questions_with_answers(bank_id):
    """获取题库的题目（含答案）"""
    user_id = request.args.get('user_id', type=int)

    if not user_id:
        return jsonify({'success': False, 'error': 'user_id is required'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500

    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT q.question_id, q.question_text, q.answer_text, q.question_type
            FROM user_custom_questions q
            WHERE q.bank_id = {bank_id}
            ORDER BY q.question_id
        """)
        questions = []

        rows = cur.fetchall()
        for row in rows:
            questions.append({
                'question_id': row[0],
                'question_text': row[1],
                'answer_text': row[2],
                'question_type': row[3],
                'bank_id': bank_id
            })

        return jsonify({'success': True, 'questions': questions})
    except Exception as e:
        logger.error(f"获取题目失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banks/<int:bank_id>/questions', methods=['GET'])
def get_bank_questions(bank_id):
    """获取题库的题目（不含答案）"""
    user_id = request.args.get('user_id', type=int)
    limit = request.args.get('limit', 20, type=int)

    if not user_id:
        return jsonify({'success': False, 'error': 'user_id is required'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500

    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT question_id, question_text, question_type
            FROM user_custom_questions
            WHERE bank_id = {bank_id}
            ORDER BY question_id
            LIMIT {limit}
        """)
        questions = []

        rows = cur.fetchall()
        for row in rows:
            questions.append({
                'question_id': row[0],
                'question_text': row[1],
                'question_type': row[2],
                'bank_id': bank_id
            })

        return jsonify({'success': True, 'questions': questions})
    except Exception as e:
        logger.error(f"获取题目失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banks/<int:bank_id>', methods=['DELETE'])
def delete_bank(bank_id):
    """删除题库"""
    user_id = request.args.get('user_id', type=int)

    if not user_id:
        return jsonify({
            'success': False,
            'error': 'user_id is required'
        }), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500

    try:
        cur = conn.cursor()
        # 删除相关题目和题库
        cur.execute(f"DELETE FROM user_custom_questions WHERE bank_id = {bank_id}")
        cur.execute(f"DELETE FROM user_custom_banks WHERE bank_id = {bank_id} AND user_id = {user_id}")

        logger.info(f"删除题库: bank_id={bank_id}, user_id={user_id}")
        return jsonify({'success': True, 'message': '题库已删除'})
    except Exception as e:
        logger.error(f"删除题库失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/answers', methods=['POST'])
def save_answer():
    """保存答题记录"""
    data = request.get_json()
    user_id = data.get('user_id')
    question_id = data.get('question_id')
    is_correct = data.get('is_correct')
    answer_time = data.get('answer_time', 0)

    if None in [user_id, question_id] or is_correct is None:
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500

    try:
        cur = conn.cursor()

        # 获取答题历史以判断是否掌握
        cur.execute(
            f"""
            SELECT is_correct, review_count
            FROM user_custom_answers
            WHERE user_id = {user_id} AND question_id = {question_id}
            """
        )
        existing = cur.fetchone()

        # 计算掌握状态：连续答对3次认为掌握
        is_mastered = False
        if is_correct:
            if existing and existing[0]:  # 之前也答对了
                review_count = existing[1] + 1
                if review_count >= 3:
                    is_mastered = True
            else:
                review_count = 1
        else:
            review_count = 0  # 答错重置计数

        # 更新或插入记录
        if existing:
            # 更新现有记录
            cur.execute(
                """
                UPDATE user_custom_answers
                SET is_correct = %s, answer_time = %s, is_mastered = %s,
                    review_count = %s, last_review_at = CURRENT_TIMESTAMP
                WHERE user_id = %s AND question_id = %s
                """,
                (is_correct, answer_time, is_mastered, review_count, user_id, question_id)
            )
        else:
            # 插入新记录
            cur.execute(
                """
                INSERT INTO user_custom_answers
                (user_id, question_id, is_correct, answer_time, is_mastered, review_count, last_review_at)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (user_id, question_id, is_correct, answer_time, is_mastered, review_count)
            )

        logger.info(f"保存答案: user_id={user_id}, question_id={question_id}, correct={is_correct}")
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"保存答案失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/stats/<int:user_id>', methods=['GET'])
def get_user_stats(user_id):
    """获取用户统计信息"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500

    try:
        cur = conn.cursor()

        # 获取题库数
        cur.execute(f"SELECT COUNT(*) FROM user_custom_banks WHERE user_id = {user_id}")
        total_banks = cur.fetchone()[0]

        # 获取总题目数
        cur.execute(f"""
            SELECT COUNT(*) FROM user_custom_questions
            WHERE bank_id IN (SELECT bank_id FROM user_custom_banks WHERE user_id = {user_id})
        """)
        total_questions = cur.fetchone()[0]

        # 获取答题记录
        cur.execute(f"""
            SELECT COUNT(*), SUM(CASE WHEN is_correct THEN 1 ELSE 0 END)
            FROM user_custom_answers
            WHERE user_id = {user_id}
        """)
        row = cur.fetchone() if cur else (0, 0)
        total_answers, correct_answers = row if row else (0, 0)

        accuracy = 0
        if total_answers and total_answers > 0:
            accuracy = round((correct_answers / total_answers) * 100, 2)

        stats = {
            'total_banks': total_banks,
            'total_questions': total_questions,
            'total_answers': total_answers,
            'correct_answers': correct_answers,
            'accuracy': f"{accuracy}%",
        }

        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 启动服务器
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
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
