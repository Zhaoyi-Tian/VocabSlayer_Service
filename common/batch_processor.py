"""
批处理管理器模块
负责文档处理的后台任务管理和进度跟踪
"""
import os
import hashlib
import logging
import json
import time
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum

# PyQt5 for threading
from PyQt5.QtCore import QThread, pyqtSignal, QObject

# 导入其他模块
from document_parser import ParserFactory
from text_processor import TextProcessor, TextChunk
from question_generator import QuestionGenerator, GeneratedQuestion

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ProcessingStatus(Enum):
    """处理状态枚举"""
    PENDING = "pending"          # 等待处理
    PROCESSING = "processing"    # 正在处理
    COMPLETED = "completed"      # 处理完成
    FAILED = "failed"           # 处理失败
    CANCELLED = "cancelled"      # 已取消


@dataclass
class ProcessingResult:
    """处理结果数据类"""
    status: ProcessingStatus
    bank_id: Optional[int] = None
    total_chunks: int = 0
    total_questions: int = 0
    success_questions: int = 0
    error_message: Optional[str] = None
    processing_time: float = 0.0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict:
        """转换为字典格式"""
        result = asdict(self)
        result['status'] = self.status.value
        return result


class DocumentProcessorWorker(QThread):
    """
    文档处理后台线程
    使用QThread实现非阻塞的文档处理
    """
    # 定义信号
    progress_updated = pyqtSignal(int, str)      # 进度更新 (百分比, 状态描述)
    chunk_processed = pyqtSignal(int, int)        # 块处理完成 (当前块, 总块数)
    question_generated = pyqtSignal(dict)         # 单个题目生成
    processing_completed = pyqtSignal(dict)       # 处理完成
    error_occurred = pyqtSignal(str)              # 错误发生
    log_message = pyqtSignal(str)                 # 日志消息

    def __init__(self,
                 file_path: str,
                 bank_name: str,
                 user_id: int,
                 api_key: str,
                 chunk_size: int = 1000,
                 questions_per_chunk: int = 3,
                 database_adapter=None):
        """
        初始化处理器

        Args:
            file_path: 文档文件路径
            bank_name: 题库名称
            user_id: 用户ID
            api_key: DeepSeek API密钥
            chunk_size: 文本块大小
            questions_per_chunk: 每块生成的题目数
            database_adapter: 数据库适配器
        """
        super().__init__()
        self.file_path = file_path
        self.bank_name = bank_name
        self.user_id = user_id
        self.api_key = api_key
        self.chunk_size = chunk_size
        self.questions_per_chunk = questions_per_chunk
        self.database_adapter = database_adapter

        # 处理控制标志
        self._cancelled = False
        self._pause_requested = False

        # 初始化组件
        self.parser = None
        self.text_processor = TextProcessor(chunk_size=chunk_size)
        self.question_generator = QuestionGenerator(api_key=api_key)

        # 计时器
        self.start_time = 0

    def run(self):
        """主处理逻辑"""
        self.start_time = time.time()
        result = ProcessingResult(status=ProcessingStatus.FAILED)

        try:
            self.log_message.emit(f"开始处理文档: {os.path.basename(self.file_path)}")
            self.progress_updated.emit(5, "验证文件...")

            # 1. 验证文件
            if not os.path.exists(self.file_path):
                raise FileNotFoundError(f"文件不存在: {self.file_path}")

            # 2. 计算文件哈希
            file_hash = self._calculate_file_hash()
            self.log_message.emit(f"文件哈希: {file_hash[:16]}...")

            # 3. 检查是否已处理过
            if self.database_adapter:
                existing_bank = self._check_existing_bank(file_hash)
                if existing_bank:
                    self.log_message.emit("文档已处理过，跳过生成")
                    result = ProcessingResult(
                        status=ProcessingStatus.COMPLETED,
                        bank_id=existing_bank['bank_id'],
                        total_questions=existing_bank['question_count'],
                        processing_time=time.time() - self.start_time,
                        metadata={'skipped': True, 'reason': 'already_processed'}
                    )
                    self.processing_completed.emit(result.to_dict())
                    return

            # 4. 创建题库记录
            self.progress_updated.emit(10, "创建题库记录...")
            bank_id = self._create_bank_record(file_hash)
            result.bank_id = bank_id

            # 5. 解析文档
            self.progress_updated.emit(15, "解析文档内容...")
            self.parser = ParserFactory.get_parser(self.file_path)
            raw_text = self.parser.extract_text(self.file_path)

            if not raw_text or len(raw_text.strip()) < 100:
                raise ValueError("文档内容为空或过短")

            self.log_message.emit(f"文档解析成功，提取文本长度: {len(raw_text)} 字符")

            # 6. 文本清洗和分块
            self.progress_updated.emit(25, "处理文本内容...")
            clean_text = self.text_processor.clean_text(raw_text)
            chunks = self.text_processor.chunk_text(clean_text, method="recursive")
            result.total_chunks = len(chunks)

            self.log_message.emit(f"文本分块完成，共 {len(chunks)} 块")

            # 7. 更新题库记录中的块数
            if self.database_adapter:
                self.database_adapter.update_bank_chunks(bank_id, len(chunks))

            # 8. 生成题目
            self.progress_updated.emit(35, "开始生成题目...")
            all_questions = []
            success_count = 0

            for i, chunk in enumerate(chunks):
                # 检查是否取消
                if self._cancelled:
                    self.log_message.emit("处理已取消")
                    result.status = ProcessingStatus.CANCELLED
                    break

                # 等待暂停恢复
                while self._pause_requested and not self._cancelled:
                    self.msleep(100)

                # 处理单个文本块
                self.chunk_processed.emit(i + 1, len(chunks))

                try:
                    # 生成题目
                    questions = self.question_generator.generate_questions(
                        chunk_text=chunk.content,
                        chunk_index=i,
                        num_questions=self.questions_per_chunk
                    )

                    # 保存题目
                    for q in questions:
                        if self.database_adapter:
                            question_id = self.database_adapter.add_custom_question(
                                bank_id=bank_id,
                                question_text=q.question,
                                answer_text=q.answer,
                                difficulty=q.difficulty,
                                source_chunk_index=i
                            )
                            q.metadata['question_id'] = question_id

                        all_questions.append(q)
                        success_count += 1

                        # 发送题目生成信号
                        self.question_generated.emit(q.to_dict())

                    # 更新进度
                    progress = 35 + int((i + 1) / len(chunks) * 60)
                    self.progress_updated.emit(progress, f"已处理 {i + 1}/{len(chunks)} 块")

                    # 避免API限流
                    self.msleep(500)

                except Exception as e:
                    self.log_message.emit(f"处理第 {i + 1} 块失败: {str(e)}")
                    continue

            # 9. 更新题库统计
            result.total_questions = len(all_questions)
            result.success_questions = success_count

            if not self._cancelled:
                if self.database_adapter:
                    self.database_adapter.update_bank_stats(
                        bank_id=bank_id,
                        question_count=success_count,
                        status='completed'
                    )

                result.status = ProcessingStatus.COMPLETED
                self.log_message.emit(f"处理完成，生成 {success_count} 道题目")

            # 10. 完成
            result.processing_time = time.time() - self.start_time
            self.progress_updated.emit(100, "处理完成")
            self.processing_completed.emit(result.to_dict())

        except Exception as e:
            # 错误处理
            error_msg = f"处理失败: {str(e)}"
            logger.error(error_msg)
            self.log_message.emit(error_msg)
            self.error_occurred.emit(error_msg)

            result.status = ProcessingStatus.FAILED
            result.error_message = str(e)
            result.processing_time = time.time() - self.start_time

            # 更新数据库状态
            if result.bank_id and self.database_adapter:
                self.database_adapter.update_bank_stats(
                    result.bank_id,
                    question_count=0,
                    status='failed',
                    error_message=str(e)
                )

            self.processing_completed.emit(result.to_dict())

    def _calculate_file_hash(self) -> str:
        """计算文件MD5哈希值"""
        hash_md5 = hashlib.md5()
        with open(self.file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _check_existing_bank(self, file_hash: str) -> Optional[dict]:
        """检查文件是否已处理过"""
        if not self.database_adapter:
            return None

        try:
            return self.database_adapter.get_bank_by_file_hash(self.user_id, file_hash)
        except:
            return None

    def _create_bank_record(self, file_hash: str) -> int:
        """创建题库记录"""
        if not self.database_adapter:
            return 0

        try:
            return self.database_adapter.create_custom_bank(
                user_id=self.user_id,
                bank_name=self.bank_name,
                source_file=self.file_path,
                description=f"自动生成于 {os.path.basename(self.file_path)}",
                file_hash=file_hash,
                processing_status='processing'
            )
        except Exception as e:
            logger.error(f"创建题库记录失败: {e}")
            raise

    def cancel(self):
        """取消处理"""
        self._cancelled = True
        self.log_message.emit("收到取消请求...")

    def pause(self):
        """暂停处理"""
        self._pause_requested = True
        self.log_message.emit("处理已暂停")

    def resume(self):
        """恢复处理"""
        self._pause_requested = False
        self.log_message.emit("处理已恢复")


class BatchProcessingManager(QObject):
    """
    批处理管理器
    管理多个文档处理任务
    """
    # 任务状态信号
    task_started = pyqtSignal(str)                 # 任务开始
    task_completed = pyqtSignal(str, dict)         # 任务完成
    task_failed = pyqtSignal(str, str)             # 任务失败
    all_tasks_completed = pyqtSignal()             # 所有任务完成

    def __init__(self, max_concurrent_tasks: int = 1):
        """
        初始化管理器

        Args:
            max_concurrent_tasks: 最大并发任务数
        """
        super().__init__()
        self.max_concurrent_tasks = max_concurrent_tasks
        self.active_tasks = {}                      # 活动任务
        self.pending_tasks = []                     # 待处理任务
        self.completed_tasks = []                   # 已完成任务

    def add_task(self, task_id: str, worker: DocumentProcessorWorker):
        """
        添加处理任务

        Args:
            task_id: 任务ID
            worker: 处理器线程
        """
        # 连接信号
        worker.processing_completed.connect(
            lambda result: self._on_task_completed(task_id, result)
        )
        worker.error_occurred.connect(
            lambda error: self._on_task_failed(task_id, error)
        )
        worker.log_message.connect(
            lambda msg: self._on_task_log(task_id, msg)
        )

        # 添加到待处理队列
        self.pending_tasks.append((task_id, worker))

        # 尝试启动任务
        self._try_start_next_task()

    def _try_start_next_task(self):
        """尝试启动下一个任务"""
        # 检查是否可以启动新任务
        if len(self.active_tasks) >= self.max_concurrent_tasks:
            return

        if not self.pending_tasks:
            return

        # 取出下一个任务
        task_id, worker = self.pending_tasks.pop(0)

        # 启动任务
        self.active_tasks[task_id] = worker
        self.task_started.emit(task_id)
        worker.start()

    def _on_task_completed(self, task_id: str, result: dict):
        """任务完成回调"""
        if task_id in self.active_tasks:
            del self.active_tasks[task_id]

        self.completed_tasks.append((task_id, result))
        self.task_completed.emit(task_id, result)

        # 尝试启动下一个任务
        self._try_start_next_task()

        # 检查是否所有任务都完成
        if not self.pending_tasks and not self.active_tasks:
            self.all_tasks_completed.emit()

    def _on_task_failed(self, task_id: str, error: str):
        """任务失败回调"""
        if task_id in self.active_tasks:
            del self.active_tasks[task_id]

        self.task_failed.emit(task_id, error)

        # 尝试启动下一个任务
        self._try_start_next_task()

    def _on_task_log(self, task_id: str, message: str):
        """任务日志回调"""
        logger.info(f"[Task {task_id}] {message}")

    def cancel_task(self, task_id: str):
        """取消指定任务"""
        # 检查活动任务
        if task_id in self.active_tasks:
            self.active_tasks[task_id].cancel()
            return True

        # 检查待处理任务
        for i, (tid, _) in enumerate(self.pending_tasks):
            if tid == task_id:
                del self.pending_tasks[i]
                return True

        return False

    def get_task_status(self, task_id: str) -> Optional[str]:
        """获取任务状态"""
        if task_id in self.active_tasks:
            return "running"
        elif any(tid == task_id for tid, _ in self.pending_tasks):
            return "pending"
        elif any(tid == task_id for tid, _ in self.completed_tasks):
            return "completed"
        else:
            return None

    def clear_completed(self):
        """清除已完成的任务记录"""
        self.completed_tasks.clear()


# 测试代码
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QPushButton, QTextEdit, QProgressBar
    from PyQt5.QtCore import Qt

    class TestWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("文档处理测试")
            self.setGeometry(100, 100, 600, 400)

            # 创建中央部件
            central_widget = QWidget()
            self.setCentralWidget(central_widget)

            # 布局
            layout = QVBoxLayout()
            central_widget.setLayout(layout)

            # 进度条
            self.progress_bar = QProgressBar()
            layout.addWidget(self.progress_bar)

            # 状态标签
            self.status_label = QLabel("准备就绪")
            layout.addWidget(self.status_label)

            # 日志文本框
            self.log_text = QTextEdit()
            self.log_text.setReadOnly(True)
            layout.addWidget(self.log_text)

            # 测试按钮
            self.test_btn = QPushButton("开始测试处理")
            self.test_btn.clicked.connect(self.start_test)
            layout.addWidget(self.test_btn)

            self.worker = None

        def start_test(self):
            # 测试文件路径（需要替换为实际路径）
            test_file = "/path/to/test/document.pdf"
            if not os.path.exists(test_file):
                self.log_text.append("请设置有效的测试文件路径")
                return

            # 创建处理器
            self.worker = DocumentProcessorWorker(
                file_path=test_file,
                bank_name="测试题库",
                user_id=1,
                api_key="your-api-key",
                chunk_size=500,
                questions_per_chunk=2
            )

            # 连接信号
            self.worker.progress_updated.connect(self.on_progress)
            self.worker.chunk_processed.connect(self.on_chunk_processed)
            self.worker.question_generated.connect(self.on_question_generated)
            self.worker.processing_completed.connect(self.on_completed)
            self.worker.error_occurred.connect(self.on_error)
            self.worker.log_message.connect(self.on_log)

            # 开始处理
            self.test_btn.setEnabled(False)
            self.worker.start()

        def on_progress(self, value, status):
            self.progress_bar.setValue(value)
            self.status_label.setText(status)

        def on_chunk_processed(self, current, total):
            self.log_text.append(f"处理进度: {current}/{total}")

        def on_question_generated(self, question):
            self.log_text.append(f"生成题目: {question['question'][:50]}...")

        def on_completed(self, result):
            self.test_btn.setEnabled(True)
            self.log_text.append(f"\n处理完成!\n结果: {json.dumps(result, indent=2, ensure_ascii=False)}")

        def on_error(self, error):
            self.test_btn.setEnabled(True)
            self.log_text.append(f"\n错误: {error}")

        def on_log(self, message):
            self.log_text.append(message)

    # 运行测试
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec_())