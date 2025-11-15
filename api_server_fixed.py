#!/usr/bin/env python3
"""
VocabSlayer 自定义题库API服务器
完整功能版本 - 支持文档解析、AI生成题目
"""
import os
import sys
import json
import hashlib
import tempfile
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import logging

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
    """每次创建新的数据库连接"""
    try:
        import psycopg2
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = True
        return conn
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        return None

def sql_escape(s):
    """转义SQL字符串"""
    if s is None:
        return "NULL"
    s = str(s)
    s = s.replace("'", "''")
    return f"'{s}'"

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
        chunk_size = request.form.get('chunk_size', 1000, type=int)
        questions_per_chunk = request.form.get('questions_per_chunk', 3, type=int)

        # 初始化文本内容变量
        text_content = ""

        if not user_id:
            return jsonify({
                'success': False,
                'error': 'user_id is required'
            }), 400

        # 保存文件（获取原始文件名）
        filename = secure_filename(file.filename)
        logger.info(f"原始文件名: {file.filename}, 安全文件名: {filename}")

        # 如果文件名被过滤掉了扩展名，保留原始扩展名
        if '.' in file.filename and '.' not in filename:
            # 获取原始文件的扩展名
            ext = os.path.splitext(file.filename)[1]
            filename = filename + ext
            logger.info(f"添加扩展名后: {filename}")

        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)

        logger.info(f"文件上传成功: {filename}, 用户ID: {user_id}")
        logger.info(f"文件路径: {file_path}")

        # 检查文件类型（使用保存后的文件路径）
        if ParserFactory and not ParserFactory.is_supported(filename):
            os.remove(file_path)  # 删除不支持的文件
            return jsonify({
                'success': False,
                'error': f'不支持的文件类型。支持的类型: {list(ParserFactory.SUPPORTED_EXTENSIONS.keys())}'
            }), 400

        # 获取数据库连接
        conn = get_db_connection()
        if not conn:
            os.remove(file_path)
            return jsonify({
                'success': False,
                'error': 'Database connection failed'
            }), 500

        # 计算文件哈希
        file_hash = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                file_hash.update(chunk)
        file_hash = file_hash.hexdigest()

        # 检查是否已存在
        cur = conn.cursor()
        cur.execute(
            f"SELECT bank_id FROM user_custom_banks WHERE user_id = {user_id} AND file_hash = {sql_escape(file_hash)}"
        )
        existing = cur.fetchone() if cur else None

        if existing:
            # 返回已存在的题库
            cur.execute(
                f"SELECT COUNT(*) FROM user_custom_questions WHERE bank_id = {existing[0]}"
            )
            count = cur.fetchone()[0] if cur else 0

            os.remove(file_path)  # 清理文件

            return jsonify({
                'success': True,
                'status': 'skipped',
                'bank_id': existing[0],
                'question_count': count,
                'message': '该文档已经处理过'
            })

        # 创建题库记录
        cur.execute(f"""
            INSERT INTO user_custom_banks
            (user_id, bank_name, source_file, description, file_hash, processing_status, question_count)
            VALUES ({user_id}, {sql_escape(bank_name)}, {sql_escape(filename)}, {sql_escape(description)}, {sql_escape(file_hash)}, 'processing', 0)
            RETURNING bank_id
        """)

        # 获取刚插入的ID
        bank_id = cur.fetchone()[0] if cur else 1

        all_questions = []

        # 处理文档
        # 首先解析文档获取文本内容
        text_content = ""
        if ParserFactory:
            try:
                parser = ParserFactory.get_parser(file_path)
                text_content = parser.extract_text(file_path)
                logger.info(f"文档解析完成，提取文本: {len(text_content)} 字符")
            except Exception as e:
                logger.error(f"文档解析失败: {e}")

        if ParserFactory and TextProcessor and QuestionGenerator and api_key and api_key != 'test_key' and text_content:
            logger.info("开始处理文档...")

            if text_content and len(text_content.strip()) > 100:
                # 处理文本 - 使用智能分块，每块500字，保留100字上下文
                text_processor = TextProcessor(chunk_size=500, chunk_overlap=100)
                text_content = text_processor.clean_text(text_content)
                text_chunks = text_processor.smart_chunk_with_context(text_content)

                if text_chunks:
                    # 生成题目
                    question_generator = QuestionGenerator(api_key=api_key)

                    for i, chunk in enumerate(text_chunks):
                        try:
                            logger.info(f"处理第 {i+1}/{len(text_chunks)} 个文本块...")

                            # 每个文本块生成1-3个问题
                            num_questions = min(3, max(1, questions_per_chunk))
                            questions = question_generator.generate_questions(
                                chunk_text=chunk.content,
                                chunk_index=i,
                                num_questions=num_questions
                            )

                            # 保存题目（使用AI生成的答案）
                            for q in questions:
                                # 准备答案文本（AI生成的答案 + 原文参考）
                                # 限制原文长度，避免过长
                                original_text = chunk.content[:500] + "..." if len(chunk.content) > 500 else chunk.content
                                answer_text = f"【AI答案】\n{q.answer}\n\n【原文参考】\n{original_text}"

                                # 保存到数据库
                                sql = """
                                    INSERT INTO user_custom_questions
                                    (bank_id, question_text, answer_text, question_type)
                                    VALUES (%s, %s, %s, %s)
                                """
                                logger.info(f"执行SQL插入题目: {q.question[:50]}...")

                                # 使用参数化查询
                                cur.execute(sql, (bank_id, q.question, answer_text, 'Q&A'))

                                all_questions.append(q)

                            logger.info(f"第 {i+1} 个文本块处理完成，生成 {len(questions)} 道题目")

                        except Exception as e:
                            logger.error(f"处理文本块失败: {e}")
                            import traceback
                            traceback.print_exc()
                            continue

                    # 所有题目处理完成
                    if len(all_questions) > 0:
                        logger.info(f"成功生成 {len(all_questions)} 道题目")

                        # 更新题库状态
                        cur.execute(
                            f"UPDATE user_custom_banks SET processing_status = 'completed', question_count = {len(all_questions)} WHERE bank_id = {bank_id}"
                        )
            else:
                logger.warning("文档内容太少")
                cur.execute(
                    f"UPDATE user_custom_banks SET processing_status = 'failed', processing_error = {sql_escape('文档内容太少')} WHERE bank_id = {bank_id}"
                )
        else:
            # 如果没有完整功能，创建示例题目
            logger.warning("使用示例题目模式（缺少处理模块或API密钥）")

            # 从文档内容创建示例问题
            if text_content and len(text_content.strip()) > 100:
                # 取前几个句子创建示例问题
                sentences = text_content.split('。')[:3]
                for i, sentence in enumerate(sentences, 1):
                    if len(sentence.strip()) > 20:
                        q_text = f"根据以上内容，请解释：{sentence.strip()[:50]}..."
                        answer_content = "【原文】\n" + sentence.strip() + "\n\n【学习提示】\n1. 请仔细阅读原文，理解其含义\n2. 思考这个句子在文档中的作用\n3. 尝试用自己的话来解释"

                        cur.execute(
                            """
                            INSERT INTO user_custom_questions
                            (bank_id, question_text, answer_text, question_type)
                            VALUES (%s, %s, %s, %s)
                            """,
                            (bank_id, q_text, answer_content, 'Q&A')
                        )
                        all_questions.append({'question': q_text})
            else:
                # 默认示例问题
                sample_questions = [
                    ("请概括文档的主要内容", "请仔细阅读文档，找出核心观点和关键信息。"),
                    ("文档中提到了哪些重要概念？", "回到原文，找出定义和解释性的句子。"),
                    ("你如何理解文档中的核心观点？", "阅读原文，形成自己的理解和总结。")
                ]

                for q_text, hint in sample_questions:
                    hint_text = "【学习提示】\n" + hint
                    cur.execute(
                        """
                        INSERT INTO user_custom_questions
                        (bank_id, question_text, answer_text, question_type)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (bank_id, q_text, hint_text, 'Q&A')
                    )
                    all_questions.append({'question': q_text})

            cur.execute(
                f"UPDATE user_custom_banks SET processing_status = 'completed', question_count = {len(all_questions)} WHERE bank_id = {bank_id}"
            )

        # 清理文件
        try:
            os.remove(file_path)
        except:
            pass

        logger.info(f"文档处理完成，共生成 {len(all_questions)} 道题目")

        return jsonify({
            'success': True,
            'status': 'completed',
            'bank_id': bank_id,
            'question_count': len(all_questions),
            'bank_name': bank_name,
            'message': f'题库 "{bank_name}" 已成功创建，共 {len(all_questions)} 道题目'
        })

    except Exception as e:
        logger.error(f"处理文档失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/banks/<int:user_id>', methods=['GET'])
def get_user_banks(user_id):
    """获取用户的题库列表"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500

    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT * FROM user_custom_banks WHERE user_id = {user_id} ORDER BY created_at DESC"
        )
        banks = []

        rows = cur.fetchall()
        for row in rows:
                banks.append({
                    'bank_id': row[0],
                    'user_id': row[1],
                    'bank_name': row[2],
                    'source_file': row[3],
                    'description': row[4],
                    'question_count': row[5],
                    'created_at': row[6].isoformat() if row[6] else None,
                    'processing_status': row[10] if len(row) > 10 else 'completed'
                })

        return jsonify({'success': True, 'banks': banks})
    except Exception as e:
        logger.error(f"获取题库列表失败: {e}")
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
        cur.execute(
            f"SELECT question_id, question_text, question_type FROM user_custom_questions WHERE bank_id = {bank_id} LIMIT {limit}"
        )
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
        cur.execute(f"SELECT * FROM user_custom_questions WHERE bank_id = {bank_id}")
        questions = []

        rows = cur.fetchall()
        for row in rows:
                questions.append({
                    'question_id': row[0],
                    'question_text': row[2],
                    'answer_text': row[3],
                    'question_type': row[4],
                    'difficulty': 1,  # 默认难度
                    'bank_id': bank_id
                })

        return jsonify({'success': True, 'questions': questions})
    except Exception as e:
        logger.error(f"获取题目（含答案）失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banks/<int:bank_id>', methods=['DELETE'])
def delete_bank(bank_id):
    """删除题库"""
    data = request.get_json()
    user_id = data.get('user_id')

    if not user_id:
        return jsonify({'success': False, 'error': 'user_id is required'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500

    try:
        # 删除相关题目和题库
        cur = conn.cursor()
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
            """
            SELECT is_correct, review_count
            FROM user_custom_answers
            WHERE user_id = %s AND question_id = %s
            """,
            (user_id, question_id)
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
    """获取用户答题统计"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500

    try:
        cur = conn.cursor()
        # 获取题库数
        cur.execute(f"SELECT COUNT(*) FROM user_custom_banks WHERE user_id = {user_id}")
        total_banks = cur.fetchone()[0] if cur else 0

        # 获取总题目数
        cur.execute(f"""
            SELECT COUNT(*) FROM user_custom_questions
            WHERE bank_id IN (SELECT bank_id FROM user_custom_banks WHERE user_id = {user_id})
        """)
        total_questions = cur.fetchone()[0] if cur else 0

        # 获取答题记录
        cur.execute(f"""
            SELECT COUNT(*), SUM(CASE WHEN is_correct THEN 1 ELSE 0 END)
            FROM user_custom_answers WHERE user_id = {user_id}
        """)
        row = cur.fetchone() if cur else (0, 0)
        total_answers, correct_answers = row if row else (0, 0)

        accuracy = 0
        if total_answers and total_answers > 0:
            accuracy = (correct_answers / total_answers) * 100

        stats = {
            'total_banks': total_banks,
            'total_questions': total_questions,
            'total_answers': total_answers,
            'correct_answers': correct_answers,
            'accuracy': round(accuracy, 2)
        }

        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.errorhandler(413)
def too_large(e):
    """文件过大错误处理"""
    return jsonify({
        'success': False,
        'error': 'File too large. Maximum size is 50MB'
    }), 413

if __name__ == '__main__':
    print("=" * 60)
    print("VocabSlayer 自定义题库API服务器")
    print("=" * 60)
    print(f"上传目录: {UPLOAD_FOLDER}")
    print("服务器运行在 http://0.0.0.0:5000")
    print("=" * 60)

    # 创建上传目录
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # 测试数据库连接
    if get_db_connection():
        print("✓ 数据库连接成功")
    else:
        print("✗ 数据库连接失败")

    # 启动服务器
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)