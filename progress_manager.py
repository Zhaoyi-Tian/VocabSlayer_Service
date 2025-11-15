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

        # logger.debug(f"创建任务: {task_id}, 文件: {filename}")  # 改为debug级别
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

            # logger.debug(f"进度更新 [{task_id}]: {progress}% - {message}")  # 改为debug级别

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
            # logger.debug(f"清理过期任务: {task_id}")  # 改为debug级别

# 全局进度管理器实例
progress_manager = ProgressManager()