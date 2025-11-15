"""
数据库适配器模块
负责自定义题库的数据库操作
"""
import logging
import os
import json
from typing import List, Dict, Optional, Any
from datetime import datetime

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseAdapter:
    """
    数据库适配器类
    提供自定义题库相关的数据库操作
    """

    def __init__(self, db_manager):
        """
        初始化适配器

        Args:
            db_manager: VocabSlayer的数据库管理器实例
        """
        self.db = db_manager
        self._ensure_tables_exist()

    def _ensure_tables_exist(self):
        """确保自定义题库相关的表存在"""
        try:
            # 检查表是否存在，如果不存在则创建
            self.db.conn.execute("""
                CREATE TABLE IF NOT EXISTS user_custom_banks (
                    bank_id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(user_id),
                    bank_name VARCHAR(200) NOT NULL,
                    source_file VARCHAR(500),
                    description TEXT,
                    question_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    file_hash VARCHAR(64),
                    processing_status VARCHAR(20) DEFAULT 'pending',
                    processing_error TEXT,
                    total_chunks INTEGER DEFAULT 0
                )
            """)

            self.db.conn.execute("""
                CREATE TABLE IF NOT EXISTS user_custom_questions (
                    question_id SERIAL PRIMARY KEY,
                    bank_id INTEGER REFERENCES user_custom_banks(bank_id),
                    question_text TEXT NOT NULL,
                    answer_text TEXT NOT NULL,
                    question_type VARCHAR(50) DEFAULT 'Q&A',
                    difficulty INTEGER DEFAULT 1 CHECK (difficulty >= 1 AND difficulty <= 3),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_generated BOOLEAN DEFAULT TRUE,
                    source_chunk_index INTEGER,
                    ai_generated BOOLEAN DEFAULT TRUE,
                    confidence_score DECIMAL(3,2)
                )
            """)

            self.db.conn.execute("""
                CREATE TABLE IF NOT EXISTS user_custom_answers (
                    answer_id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(user_id),
                    question_id INTEGER REFERENCES user_custom_questions(question_id),
                    user_answer TEXT,
                    is_correct BOOLEAN,
                    answer_time INTEGER,
                    answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建索引以提高查询性能
            self.db.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_custom_banks_user_id ON user_custom_banks(user_id)
            """)

            self.db.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_custom_questions_bank_id ON user_custom_questions(bank_id)
            """)

            self.db.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_custom_answers_user_id ON user_custom_answers(user_id)
            """)

            self.db.conn.commit()
            logger.info("自定义题库表已准备就绪")

        except Exception as e:
            logger.error(f"初始化数据库表失败: {e}")
            raise

    def create_custom_bank(self,
                          user_id: int,
                          bank_name: str,
                          source_file: str,
                          description: str = "",
                          file_hash: str = None,
                          processing_status: str = 'pending',
                          total_chunks: int = 0) -> int:
        """
        创建自定义题库

        Args:
            user_id: 用户ID
            bank_name: 题库名称
            source_file: 源文件路径
            description: 题库描述
            file_hash: 文件哈希值
            processing_status: 处理状态
            total_chunks: 总文本块数

        Returns:
            题库ID
        """
        try:
            query = self.db.conn.prepare("""
                INSERT INTO user_custom_banks
                (user_id, bank_name, source_file, description, file_hash,
                 processing_status, total_chunks)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING bank_id
            """)

            result = query(
                user_id,
                bank_name,
                source_file,
                description,
                file_hash,
                processing_status,
                total_chunks
            )

            bank_id = result[0]['bank_id']
            self.db.conn.commit()
            logger.info(f"创建自定义题库成功，ID: {bank_id}")
            return bank_id

        except Exception as e:
            self.db.conn.rollback()
            logger.error(f"创建自定义题库失败: {e}")
            raise

    def update_bank_status(self,
                          bank_id: int,
                          status: str,
                          question_count: int = None,
                          error_message: str = None):
        """
        更新题库状态

        Args:
            bank_id: 题库ID
            status: 新状态
            question_count: 题目数量
            error_message: 错误信息
        """
        try:
            update_fields = ["processing_status = $2", "updated_at = CURRENT_TIMESTAMP"]
            params = [bank_id, status]
            param_index = 3

            if question_count is not None:
                update_fields.append(f"question_count = ${param_index}")
                params.append(question_count)
                param_index += 1

            if error_message is not None:
                update_fields.append(f"processing_error = ${param_index}")
                params.append(error_message)
                param_index += 1

            query_str = f"""
                UPDATE user_custom_banks
                SET {', '.join(update_fields)}
                WHERE bank_id = $1
            """

            query = self.db.conn.prepare(query_str)
            query(*params)
            self.db.conn.commit()
            logger.debug(f"更新题库 {bank_id} 状态为 {status}")

        except Exception as e:
            self.db.conn.rollback()
            logger.error(f"更新题库状态失败: {e}")

    def update_bank_chunks(self, bank_id: int, total_chunks: int):
        """更新题库的文本块数量"""
        try:
            query = self.db.conn.prepare("""
                UPDATE user_custom_banks
                SET total_chunks = $2
                WHERE bank_id = $1
            """)
            query(bank_id, total_chunks)
            self.db.conn.commit()

        except Exception as e:
            logger.error(f"更新题库块数失败: {e}")

    def update_bank_stats(self,
                         bank_id: int,
                         question_count: int,
                         status: str = None,
                         error_message: str = None):
        """
        更新题库统计信息

        Args:
            bank_id: 题库ID
            question_count: 题目数量
            status: 处理状态
            error_message: 错误信息
        """
        self.update_bank_status(bank_id, status or 'completed', question_count, error_message)

    def get_bank_by_file_hash(self, user_id: int, file_hash: str) -> Optional[Dict]:
        """
        根据文件哈希查找题库

        Args:
            user_id: 用户ID
            file_hash: 文件哈希

        Returns:
            题库信息字典
        """
        try:
            query = self.db.conn.prepare("""
                SELECT bank_id, bank_name, question_count, created_at, processing_status
                FROM user_custom_banks
                WHERE user_id = $1 AND file_hash = $2
            """)
            result = query(user_id, file_hash)

            if result:
                bank = dict(result[0])
                logger.debug(f"找到已存在的题库: {bank['bank_name']}")
                return bank

            return None

        except Exception as e:
            logger.error(f"查找题库失败: {e}")
            return None

    def add_custom_question(self,
                           bank_id: int,
                           question_text: str,
                           answer_text: str,
                           difficulty: int = 1,
                           question_type: str = 'explanation',
                           source_chunk_index: int = 0,
                           confidence_score: float = 0.9) -> int:
        """
        添加自定义题目

        Args:
            bank_id: 题库ID
            question_text: 问题文本
            answer_text: 答案文本
            difficulty: 难度等级
            question_type: 题目类型
            source_chunk_index: 来源文本块索引
            confidence_score: 置信度

        Returns:
            题目ID
        """
        try:
            query = self.db.conn.prepare("""
                INSERT INTO user_custom_questions
                (bank_id, question_text, answer_text, difficulty,
                 question_type, source_chunk_index, ai_generated, confidence_score)
                VALUES ($1, $2, $3, $4, $5, $6, TRUE, $7)
                RETURNING question_id
            """)

            result = query(
                bank_id,
                question_text,
                answer_text,
                difficulty,
                question_type,
                source_chunk_index,
                confidence_score
            )

            question_id = result[0]['question_id']
            self.db.conn.commit()
            logger.debug(f"添加题目成功，ID: {question_id}")
            return question_id

        except Exception as e:
            self.db.conn.rollback()
            logger.error(f"添加题目失败: {e}")
            raise

    def batch_add_questions(self, questions: List[Dict]) -> List[int]:
        """
        批量添加题目

        Args:
            questions: 题目列表

        Returns:
            题目ID列表
        """
        question_ids = []
        try:
            # 使用事务批量插入
            for q in questions:
                question_id = self.add_custom_question(
                    bank_id=q.get('bank_id'),
                    question_text=q.get('question_text'),
                    answer_text=q.get('answer_text'),
                    difficulty=q.get('difficulty', 1),
                    question_type=q.get('question_type', 'explanation'),
                    source_chunk_index=q.get('source_chunk_index', 0),
                    confidence_score=q.get('confidence_score', 0.9)
                )
                question_ids.append(question_id)

            self.db.conn.commit()
            logger.info(f"批量添加 {len(question_ids)} 道题目成功")
            return question_ids

        except Exception as e:
            self.db.conn.rollback()
            logger.error(f"批量添加题目失败: {e}")
            raise

    def get_user_custom_banks(self, user_id: int) -> List[Dict]:
        """
        获取用户的自定义题库列表

        Args:
            user_id: 用户ID

        Returns:
            题库列表
        """
        try:
            query = self.db.conn.prepare("""
                SELECT bank_id, bank_name, source_file, description,
                       question_count, processing_status, created_at,
                       total_chunks, processing_error
                FROM user_custom_banks
                WHERE user_id = $1
                ORDER BY created_at DESC
            """)
            result = query(user_id)
            return [dict(r) for r in result]

        except Exception as e:
            logger.error(f"获取用户题库列表失败: {e}")
            return []

    def get_custom_questions(self, bank_id: int, limit: int = None) -> List[Dict]:
        """
        获取题库的所有题目

        Args:
            bank_id: 题库ID
            limit: 限制返回数量

        Returns:
            题目列表
        """
        try:
            limit_str = f"LIMIT {limit}" if limit else ""
            query = self.db.conn.prepare(f"""
                SELECT question_id, question_text, answer_text, difficulty,
                       question_type, source_chunk_index, confidence_score
                FROM user_custom_questions
                WHERE bank_id = $1
                ORDER BY question_id
                {limit_str}
            """)
            result = query(bank_id)
            return [dict(r) for r in result]

        except Exception as e:
            logger.error(f"获取题目列表失败: {e}")
            return []

    def get_question_for_quiz(self, bank_id: int, question_ids: List[int] = None) -> List[Dict]:
        """
        获取用于答题的题目（不包含答案）

        Args:
            bank_id: 题库ID
            question_ids: 指定题目ID列表

        Returns:
            题目列表（不含答案）
        """
        try:
            if question_ids:
                placeholders = ','.join(['$' + str(i+2) for i in range(len(question_ids))])
                query = self.db.conn.prepare(f"""
                    SELECT question_id, question_text, difficulty, question_type
                    FROM user_custom_questions
                    WHERE bank_id = $1 AND question_id IN ({placeholders})
                    ORDER BY question_id
                """)
                params = [bank_id] + question_ids
                result = query(*params)
            else:
                query = self.db.conn.prepare("""
                    SELECT question_id, question_text, difficulty, question_type
                    FROM user_custom_questions
                    WHERE bank_id = $1
                    ORDER BY question_id
                """)
                result = query(bank_id)

            return [dict(r) for r in result]

        except Exception as e:
            logger.error(f"获取答题题目失败: {e}")
            return []

    def save_custom_answer(self,
                          user_id: int,
                          question_id: int,
                          user_answer: str,
                          is_correct: bool,
                          answer_time: int = 0):
        """
        保存用户答题记录

        Args:
            user_id: 用户ID
            question_id: 题目ID
            user_answer: 用户答案
            is_correct: 是否正确
            answer_time: 答题时间（秒）
        """
        try:
            query = self.db.conn.prepare("""
                INSERT INTO user_custom_answers
                (user_id, question_id, user_answer, is_correct, answer_time)
                VALUES ($1, $2, $3, $4, $5)
            """)
            query(user_id, question_id, user_answer, is_correct, answer_time)
            self.db.conn.commit()
            logger.debug(f"保存答题记录成功: question_id={question_id}, correct={is_correct}")

        except Exception as e:
            self.db.conn.rollback()
            logger.error(f"保存答题记录失败: {e}")

    def get_user_answer_stats(self, user_id: int) -> Dict:
        """
        获取用户答题统计

        Args:
            user_id: 用户ID

        Returns:
            统计信息字典
        """
        try:
            query = self.db.conn.prepare("""
                SELECT
                    COUNT(*) as total_answers,
                    SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) as correct_answers,
                    AVG(answer_time) as avg_time,
                    COUNT(DISTINCT question_id) as unique_questions
                FROM user_custom_answers
                WHERE user_id = $1
            """)
            result = query(user_id)

            if result:
                stats = dict(result[0])
                if stats['total_answers'] > 0:
                    stats['accuracy'] = stats['correct_answers'] / stats['total_answers'] * 100
                else:
                    stats['accuracy'] = 0
                return stats

            return {
                'total_answers': 0,
                'correct_answers': 0,
                'accuracy': 0,
                'avg_time': 0,
                'unique_questions': 0
            }

        except Exception as e:
            logger.error(f"获取答题统计失败: {e}")
            return {}

    def delete_custom_bank(self, bank_id: int, user_id: int) -> bool:
        """
        删除自定义题库

        Args:
            bank_id: 题库ID
            user_id: 用户ID

        Returns:
            是否成功删除
        """
        try:
            # 检查题库是否属于该用户
            query = self.db.conn.prepare("""
                SELECT bank_id FROM user_custom_banks
                WHERE bank_id = $1 AND user_id = $2
            """)
            result = query(bank_id, user_id)

            if not result:
                logger.warning(f"题库 {bank_id} 不存在或不属于用户 {user_id}")
                return False

            # 删除题库（会级联删除题目和答题记录）
            query = self.db.conn.prepare("""
                DELETE FROM user_custom_banks
                WHERE bank_id = $1
            """)
            query(bank_id)
            self.db.conn.commit()
            logger.info(f"删除题库成功: bank_id={bank_id}")
            return True

        except Exception as e:
            self.db.conn.rollback()
            logger.error(f"删除题库失败: {e}")
            return False

    def search_questions(self,
                        user_id: int,
                        keyword: str,
                        bank_id: int = None) -> List[Dict]:
        """
        搜索题目

        Args:
            user_id: 用户ID
            keyword: 关键词
            bank_id: 可选的题库ID

        Returns:
            匹配的题目列表
        """
        try:
            if bank_id:
                query = self.db.conn.prepare("""
                    SELECT q.question_id, q.question_text, q.difficulty,
                           q.question_type, b.bank_name
                    FROM user_custom_questions q
                    JOIN user_custom_banks b ON q.bank_id = b.bank_id
                    WHERE b.user_id = $1 AND b.bank_id = $2
                      AND (q.question_text ILIKE $3 OR q.answer_text ILIKE $3)
                    ORDER BY q.question_id
                """)
                result = query(user_id, bank_id, f"%{keyword}%")
            else:
                query = self.db.conn.prepare("""
                    SELECT q.question_id, q.question_text, q.difficulty,
                           q.question_type, b.bank_name
                    FROM user_custom_questions q
                    JOIN user_custom_banks b ON q.bank_id = b.bank_id
                    WHERE b.user_id = $1
                      AND (q.question_text ILIKE $2 OR q.answer_text ILIKE $2)
                    ORDER BY q.question_id
                """)
                result = query(user_id, f"%{keyword}%")

            return [dict(r) for r in result]

        except Exception as e:
            logger.error(f"搜索题目失败: {e}")
            return []