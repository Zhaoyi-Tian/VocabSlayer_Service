"""
自定义题库管理器
整合文档处理功能，提供给前端调用的接口
"""
import os
import logging
from typing import Optional, Callable, Dict, Any, List

from .document_parser import ParserFactory
from .text_processor import TextProcessor
from .question_generator import QuestionGenerator
from .batch_processor import DocumentProcessorWorker
from .database_adapter import DatabaseAdapter

# 设置日志
logger = logging.getLogger(__name__)


class CustomBankManager:
    """
    自定义题库管理器
    提供完整的文档处理和题目生成功能
    """

    def __init__(self,
                 db_manager,
                 api_key: str,
                 chunk_size: int = 1000,
                 questions_per_chunk: int = 3):
        """
        初始化管理器

        Args:
            db_manager: VocabSlayer的数据库管理器
            api_key: DeepSeek API密钥
            chunk_size: 文本块大小
            questions_per_chunk: 每块生成的题目数
        """
        self.db_manager = db_manager
        self.db_adapter = DatabaseAdapter(db_manager)
        self.api_key = api_key
        self.chunk_size = chunk_size
        self.questions_per_chunk = questions_per_chunk

        # 初始化处理器
        self.text_processor = TextProcessor(
            chunk_size=chunk_size,
            chunk_overlap=max(chunk_size // 5, 100),
            min_chunk_size=100
        )
        self.question_generator = QuestionGenerator(api_key=api_key)

    def create_bank_from_document(self,
                                  file_path: str,
                                  bank_name: str,
                                  user_id: int,
                                  progress_callback: Optional[Callable] = None,
                                  log_callback: Optional[Callable] = None) -> DocumentProcessorWorker:
        """
        从文档创建题库（异步处理）

        Args:
            file_path: 文档文件路径
            bank_name: 题库名称
            user_id: 用户ID
            progress_callback: 进度回调函数 (percentage: int, status: str)
            log_callback: 日志回调函数 (message: str)

        Returns:
            处理器线程对象
        """
        # 验证文件
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 检查文件类型
        if not ParserFactory.is_supported(file_path):
            supported = ', '.join(ParserFactory.SUPPORTED_EXTENSIONS.keys())
            raise ValueError(f"不支持的文件类型。支持的类型: {supported}")

        # 创建处理线程
        worker = DocumentProcessorWorker(
            file_path=file_path,
            bank_name=bank_name,
            user_id=user_id,
            api_key=self.api_key,
            chunk_size=self.chunk_size,
            questions_per_chunk=self.questions_per_chunk,
            database_adapter=self.db_adapter
        )

        # 连接回调
        if progress_callback:
            worker.progress_updated.connect(progress_callback)
        if log_callback:
            worker.log_message.connect(log_callback)

        return worker

    def generate_questions_sync(self,
                                file_path: str,
                                bank_name: str,
                                user_id: int,
                                questions_per_chunk: int = None) -> Dict[str, Any]:
        """
        同步生成题目（阻塞式）

        Args:
            file_path: 文档文件路径
            bank_name: 题库名称
            user_id: 用户ID
            questions_per_chunk: 每块生成的题目数

        Returns:
            处理结果字典
        """
        questions_per_chunk = questions_per_chunk or self.questions_per_chunk

        try:
            # 1. 解析文档
            logger.info(f"开始解析文档: {file_path}")
            parser = ParserFactory.get_parser(file_path)
            raw_text = parser.extract_text(file_path)

            if not raw_text or len(raw_text.strip()) < 100:
                raise ValueError("文档内容为空或过短")

            # 2. 文本处理
            logger.info("处理文本内容...")
            clean_text = self.text_processor.clean_text(raw_text)
            chunks = self.text_processor.chunk_text(clean_text, method="recursive")
            logger.info(f"文本分块完成，共 {len(chunks)} 块")

            # 3. 创建题库记录
            file_hash = self._calculate_file_hash(file_path)
            bank_id = self.db_adapter.create_custom_bank(
                user_id=user_id,
                bank_name=bank_name,
                source_file=file_path,
                description=f"自动生成于 {os.path.basename(file_path)}",
                file_hash=file_hash,
                total_chunks=len(chunks)
            )

            # 4. 生成题目
            logger.info(f"开始生成题目，每块 {questions_per_chunk} 道...")
            all_questions = []
            success_count = 0

            for i, chunk in enumerate(chunks):
                try:
                    questions = self.question_generator.generate_questions(
                        chunk_text=chunk.content,
                        chunk_index=i,
                        num_questions=questions_per_chunk
                    )

                    # 保存题目
                    for q in questions:
                        question_id = self.db_adapter.add_custom_question(
                            bank_id=bank_id,
                            question_text=q.question,
                            answer_text=q.answer,
                            difficulty=q.difficulty,
                            question_type=q.question_type,
                            source_chunk_index=i,
                            confidence_score=q.confidence_score
                        )
                        all_questions.append(q.to_dict())
                        success_count += 1

                except Exception as e:
                    logger.error(f"处理第 {i + 1} 块失败: {e}")
                    continue

            # 5. 更新题库状态
            self.db_adapter.update_bank_status(
                bank_id=bank_id,
                status='completed',
                question_count=success_count
            )

            return {
                'success': True,
                'bank_id': bank_id,
                'total_chunks': len(chunks),
                'total_questions': len(all_questions),
                'success_questions': success_count,
                'questions': all_questions
            }

        except Exception as e:
            logger.error(f"同步生成失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def get_user_banks(self, user_id: int) -> List[Dict]:
        """获取用户的自定义题库列表"""
        return self.db_adapter.get_user_custom_banks(user_id)

    def get_bank_questions(self, bank_id: int, limit: int = None) -> List[Dict]:
        """获取题库的题目"""
        return self.db_adapter.get_custom_questions(bank_id, limit)

    def delete_bank(self, bank_id: int, user_id: int) -> bool:
        """删除题库"""
        return self.db_adapter.delete_custom_bank(bank_id, user_id)

    def search_questions(self,
                         user_id: int,
                         keyword: str,
                         bank_id: int = None) -> List[Dict]:
        """搜索题目"""
        return self.db_adapter.search_questions(user_id, keyword, bank_id)

    def get_user_stats(self, user_id: int) -> Dict:
        """获取用户答题统计"""
        return self.db_adapter.get_user_answer_stats(user_id)

    def save_answer(self,
                    user_id: int,
                    question_id: int,
                    user_answer: str,
                    is_correct: bool,
                    answer_time: int = 0):
        """保存用户答案"""
        self.db_adapter.save_custom_answer(
            user_id=user_id,
            question_id=question_id,
            user_answer=user_answer,
            is_correct=is_correct,
            answer_time=answer_time
        )

    def get_questions_for_quiz(self,
                                bank_id: int,
                                question_count: int = 20) -> List[Dict]:
        """
        获取用于答题的题目（不包含答案）

        Args:
            bank_id: 题库ID
            question_count: 题目数量

        Returns:
            题目列表（不含答案）
        """
        questions = self.db_adapter.get_question_for_quiz(bank_id, limit=question_count)

        # 如果题目数量不足，返回所有题目
        if len(questions) < question_count:
            questions = self.db_adapter.get_question_for_quiz(bank_id)

        return questions[:question_count]

    def _calculate_file_hash(self, file_path: str) -> str:
        """计算文件MD5哈希值"""
        import hashlib

        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def validate_document(self, file_path: str) -> Dict[str, Any]:
        """
        验证文档是否适合处理

        Args:
            file_path: 文档路径

        Returns:
            验证结果
        """
        result = {
            'valid': False,
            'error': None,
            'file_size': 0,
            'file_type': None,
            'estimated_time': 0
        }

        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                result['error'] = "文件不存在"
                return result

            # 获取文件信息
            result['file_size'] = os.path.getsize(file_path)
            _, result['file_type'] = os.path.splitext(file_path)

            # 检查文件类型
            if not ParserFactory.is_supported(file_path):
                result['error'] = f"不支持的文件类型: {result['file_type']}"
                return result

            # 检查文件大小（限制50MB）
            max_size = 50 * 1024 * 1024  # 50MB
            if result['file_size'] > max_size:
                result['error'] = "文件过大（最大50MB）"
                return result

            # 快速解析测试
            parser = ParserFactory.get_parser(file_path)
            sample_text = parser.extract_text(file_path)

            # 检查文本长度
            if len(sample_text.strip()) < 100:
                result['error'] = "文档内容过少（至少需要100个字符）"
                return result

            # 估算处理时间（基于文本长度）
            text_length = len(sample_text)
            estimated_chunks = text_length // self.chunk_size
            result['estimated_time'] = estimated_chunks * 5  # 每块约5秒

            result['valid'] = True
            result['text_length'] = text_length
            result['estimated_chunks'] = estimated_chunks

            return result

        except Exception as e:
            result['error'] = str(e)
            return result