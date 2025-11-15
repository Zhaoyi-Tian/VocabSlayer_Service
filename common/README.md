# VocabSlayer 文档处理模块

这个模块为 VocabSlayer 应用提供了 PDF 和 Word 文档的自定义题库生成功能。

## 功能特性

- 📄 **文档解析**: 支持 PDF 和 Word (.docx) 文档
- 🧹 **智能清洗**: 自动去除页码、页眉页脚等干扰信息
- ✂️ **智能分块**: 多种分块策略，保持语义完整性
- 🤖 **AI 驱动**: 使用 DeepSeek API 生成高质量题目
- 🎯 **多种题型**: 概念题、应用题、分析题等
- ✅ **答案验证**: 确保生成内容的准确性
- 📊 **进度跟踪**: 实时显示处理进度
- 🗄️ **数据库集成**: 与 VocabSlayer 数据库无缝集成

## 模块结构

```
common/
├── document_parser.py     # 文档解析器（PDF/Word）
├── text_processor.py      # 文本处理器（清洗/分块）
├── question_generator.py  # AI题目生成器
├── batch_processor.py     # 批处理管理器
├── database_adapter.py    # 数据库适配器
├── custom_bank_manager.py # 统一管理接口
├── test_document_processing.py # 测试脚本
└── README.md             # 本文档
```

## 安装依赖

```bash
# 激活虚拟环境
source /home/openEuler/openGauss/VocabSlayer_servier/VocabSlayer_update_servier/common/.venv/bin/activate

# 安装依赖
pip install PyMuPDF==1.24.0
pip install python-docx==1.1.0
pip install chardet==5.2.0
pip install openai
```

## 快速开始

### 1. 基本使用

```python
from custom_bank_manager import CustomBankManager

# 初始化管理器
manager = CustomBankManager(
    db_manager=your_db_manager,
    api_key="your-deepseek-api-key",
    chunk_size=1000,
    questions_per_chunk=3
)

# 异步创建题库（推荐）
worker = manager.create_bank_from_document(
    file_path="/path/to/document.pdf",
    bank_name="我的题库",
    user_id=123,
    progress_callback=lambda p, s: print(f"进度: {p}% - {s}"),
    log_callback=lambda m: print(f"日志: {m}")
)
worker.start()

# 同步创建题库（测试用）
result = manager.generate_questions_sync(
    file_path="/path/to/document.docx",
    bank_name="我的题库",
    user_id=123
)
```

### 2. 前端集成示例

```python
# 在 VocabSlayer 前端中使用
from server.custom_bank_manager import CustomBankManager
from PyQt5.QtCore import QThread

class CustomBankWidget(QWidget):
    def __init__(self):
        super().__init__()
        # 获取数据库管理器和API密钥
        self.db_manager = DatabaseManager()
        self.api_key = self.get_user_api_key()

        # 初始化管理器
        self.manager = CustomBankManager(
            db_manager=self.db_manager,
            api_key=self.api_key
        )
        self.current_worker = None

    def generate_bank(self, file_path, bank_name):
        """生成题库"""
        try:
            # 创建处理线程
            self.current_worker = self.manager.create_bank_from_document(
                file_path=file_path,
                bank_name=bank_name,
                user_id=self.user_id,
                progress_callback=self.on_progress,
                log_callback=self.on_log
            )

            # 连接完成信号
            self.current_worker.processing_completed.connect(self.on_completed)
            self.current_worker.error_occurred.connect(self.on_error)

            # 开始处理
            self.current_worker.start()
            self.progress_bar.show()

        except Exception as e:
            QMessageBox.critical(self, "错误", str(e))

    def on_progress(self, percentage, status):
        """更新进度"""
        self.progress_bar.setValue(percentage)
        self.status_label.setText(status)

    def on_completed(self, result):
        """处理完成"""
        self.progress_bar.hide()
        QMessageBox.information(
            self,
            "成功",
            f"生成完成！共 {result['success_questions']} 道题目"
        )
```

## 配置说明

### 文本处理配置

```python
# TextProcessor 参数
processor = TextProcessor(
    chunk_size=1000,      # 块大小（字符数）
    chunk_overlap=200,    # 重叠大小
    min_chunk_size=100    # 最小块大小
)

# 分块方法
chunks = processor.chunk_text(
    text=clean_text,
    method="recursive"    # 可选: recursive, paragraph, sentence, fixed
)
```

### 题目生成配置

```python
# QuestionGenerator 参数
generator = QuestionGenerator(
    api_key="your-api-key",
    base_url="https://api.deepseek.com",
    model="deepseek-chat",
    max_retries=3,
    timeout=30
)
```

## API 参考

### CustomBankManager 主要方法

| 方法 | 描述 | 参数 | 返回 |
|------|------|------|------|
| `create_bank_from_document` | 异步创建题库 | file_path, bank_name, user_id | DocumentProcessorWorker |
| `generate_questions_sync` | 同步生成题目 | file_path, bank_name, user_id | Dict |
| `get_user_banks` | 获取用户题库 | user_id | List[Dict] |
| `get_bank_questions` | 获取题库题目 | bank_id, limit | List[Dict] |
| `delete_bank` | 删除题库 | bank_id, user_id | bool |
| `search_questions` | 搜索题目 | user_id, keyword | List[Dict] |
| `validate_document` | 验证文档 | file_path | Dict |

### DatabaseAdapter 主要方法

| 方法 | 描述 | 参数 | 返回 |
|------|------|------|------|
| `create_custom_bank` | 创建题库记录 | user_id, bank_name, ... | int |
| `add_custom_question` | 添加题目 | bank_id, question_text, ... | int |
| `update_bank_status` | 更新题库状态 | bank_id, status, ... | None |
| `save_custom_answer` | 保存答题记录 | user_id, question_id, ... | None |
| `get_user_answer_stats` | 获取答题统计 | user_id | Dict |

## 数据库表结构

### user_custom_banks（题库表）

| 字段 | 类型 | 描述 |
|------|------|------|
| bank_id | SERIAL | 主键 |
| user_id | INTEGER | 用户ID |
| bank_name | VARCHAR(200) | 题库名称 |
| source_file | VARCHAR(500) | 源文件路径 |
| description | TEXT | 描述 |
| question_count | INTEGER | 题目数量 |
| file_hash | VARCHAR(64) | 文件哈希 |
| processing_status | VARCHAR(20) | 处理状态 |
| total_chunks | INTEGER | 文本块数 |

### user_custom_questions（题目表）

| 字段 | 类型 | 描述 |
|------|------|------|
| question_id | SERIAL | 主键 |
| bank_id | INTEGER | 题库ID |
| question_text | TEXT | 问题文本 |
| answer_text | TEXT | 答案文本 |
| question_type | VARCHAR(50) | 题目类型 |
| difficulty | INTEGER | 难度等级 |
| source_chunk_index | INTEGER | 来源块索引 |
| ai_generated | BOOLEAN | 是否AI生成 |
| confidence_score | DECIMAL(3,2) | 置信度 |

## 测试

运行测试脚本：

```bash
cd /home/openEuler/openGauss/VocabSlayer_servier/VocabSlayer_update_servier/common
source .venv/bin/activate

# 设置API密钥
export DEEPSEEK_API_KEY="your-api-key"

# 运行测试
python test_document_processing.py
```

测试选项：
1. 测试文档解析
2. 测试文本处理
3. 测试题目生成（需要API密钥）
4. 端到端测试
5. 运行所有测试

## 性能优化建议

1. **文本分块大小**
   - 推荐值：800-1500 字符
   - 较大的文本：1200-2000 字符
   - 短文本：500-800 字符

2. **并发控制**
   - 同时处理文档数：1-2 个
   - API 调用间隔：0.5-1 秒
   - 使用后台线程避免阻塞UI

3. **缓存策略**
   - 文件哈希避免重复处理
   - 文本清洗结果可缓存
   - 题目生成结果可复用

## 错误处理

常见错误及解决方案：

1. **文件解析失败**
   - 检查文件是否损坏
   - 确认文件格式正确
   - 尝试另存为新文件

2. **API 调用失败**
   - 检查 API 密钥是否有效
   - 确认网络连接正常
   - 检查 API 配额是否充足

3. **数据库错误**
   - 检查数据库连接
   - 确认表结构正确
   - 查看详细错误日志

## 注意事项

1. **API 成本控制**
   - 设置合理的题目生成数量
   - 使用文本分块避免超限
   - 监控 Token 使用情况

2. **隐私安全**
   - 不要处理敏感文档
   - 本地处理优先
   - 及时删除临时文件

3. **用户体验**
   - 提供详细的进度反馈
   - 支持取消处理
   - 保存中间结果

## 更新日志

### v1.0.0 (2025-01-14)
- 初始版本发布
- 支持 PDF 和 Word 文档解析
- 集成 DeepSeek API 题目生成
- 完整的数据库集成
- 异步处理支持

## 支持

如有问题，请查看：
1. 日志文件：`/var/log/vocabslayer/`
2. 错误码：参考异常信息
3. 测试用例：查看 `test_document_processing.py`

## 许可证

本项目遵循 VocabSlayer 主项目许可证。