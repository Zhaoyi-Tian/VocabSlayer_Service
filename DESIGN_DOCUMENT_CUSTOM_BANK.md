# 自定义题库功能设计文档

## 1. 功能概述

### 1.1 功能描述
自定义题库功能允许用户上传PDF、DOCX等文档，系统自动解析文档内容，使用AI生成相关的词汇练习题，并将生成的题库保存到数据库中供后续练习使用。

### 1.2 核心特性
- 支持多种文档格式（PDF、DOCX、DOC）
- 智能文本分块处理
- AI驱动的问题生成
- 实时进度推送
- 题库去重检测

## 2. 系统架构

### 2.1 整体架构图
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   前端UI    │────▶│  API服务器  │────▶│  PostgreSQL │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐     ┌─────────────┐
                    │  进度管理器  │     │  DeepSeek    │
                    └─────────────┘     │    API       │
                                         └─────────────┘
```

### 2.2 模块划分

#### 2.2.1 API层 (api_server.py)
- **文件上传处理**：接收并保存上传文件
- **任务调度**：创建异步处理任务
- **进度推送**：SSE实时进度通知
- **题库管理**：CRUD操作

#### 2.2.2 进度管理层 (progress_manager.py)
- **任务创建**：分配唯一任务ID
- **进度追踪**：更新任务状态和进度
- **消息队列**：管理进度消息传递
- **资源清理**：自动清理过期任务

#### 2.2.3 文档处理层 (common/parsers/)
- **PDF解析器** (pdf_parser.py)：使用PyMuPDF解析PDF
- **Word解析器** (docx_parser.py)：使用python-docx解析Word文档
- **解析器工厂** (parser_factory.py)：根据文件类型选择解析器

#### 2.2.4 文本处理层 (common/text_processor.py)
- **文本清洗**：去除特殊字符、格式化
- **智能分块**：按语义切分文本
- **重叠处理**：保留上下文信息

#### 2.2.5 题目生成层 (common/question_generator.py)
- **API集成**：与DeepSeek API交互
- **题目生成**：根据文本生成不同类型题目
- **结果验证**：确保题目质量

#### 2.2.6 批处理器 (common/batch_processor.py)
- **协调各模块**：管理整个处理流程
- **错误处理**：捕获并记录处理异常
- **进度报告**：向上层反馈处理状态

## 3. 接口定义

### 3.1 文件上传接口

**接口路径**: `POST /api/upload`

**请求参数**:
```python
{
    'file': File,           # 上传的文件
    'user_id': int,         # 用户ID
    'bank_name': str,       # 题库名称
    'description': str,     # 题库描述
    'api_key': str,         # DeepSeek API密钥（可选）
    'chunk_size': int,      # 文本块大小（默认500）
    'questions_per_chunk': int  # 每块生成的题目数（默认2）
}
```

**响应示例**:
```json
{
    "success": true,
    "task_id": "uuid-string",
    "message": "文件已上传，正在处理中...",
    "progress_url": "/api/progress/uuid-string"
}
```

### 3.2 进度查询接口（SSE）

**接口路径**: `GET /api/progress/<task_id>`

**响应格式**: Server-Sent Events

**数据格式**:
```json
{
    "task_id": "uuid-string",
    "status": "processing|completed|error",
    "progress": 0-100,
    "message": "进度描述",
    "current_step": "当前步骤",
    "details": {
        "page_count": 10,
        "chunk_index": 5,
        "total_chunks": 20
    }
}
```

### 3.3 题库管理接口

#### 获取用户题库列表
`GET /api/banks/<user_id>`

#### 删除题库
`DELETE /api/banks/<bank_id>?user_id=<user_id>`

#### 获取题库题目
`GET /api/banks/<bank_id>/questions_with_answers`

## 4. 数据结构

### 4.1 数据库表结构

#### user_custom_banks 表
```sql
CREATE TABLE user_custom_banks (
    bank_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    bank_name VARCHAR(255) NOT NULL,
    source_file VARCHAR(255) NOT NULL,
    description TEXT,
    question_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    file_hash VARCHAR(64) UNIQUE,
    processing_status VARCHAR(20) DEFAULT 'processing'
);
```

#### custom_questions 表
```sql
CREATE TABLE custom_questions (
    question_id SERIAL PRIMARY KEY,
    bank_id INTEGER REFERENCES user_custom_banks(bank_id),
    question_text TEXT NOT NULL,
    question_type VARCHAR(20) NOT NULL,  -- 'choice', 'fill_blank'
    options JSONB,                       -- 选择题选项
    correct_answer TEXT NOT NULL,
    explanation TEXT,
    difficulty INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.2 内部数据结构

#### ProgressUpdate
```python
@dataclass
class ProgressUpdate:
    task_id: str
    status: str
    progress: int
    message: str
    current_step: str
    details: Optional[dict] = None
    timestamp: float
```

#### Question
```python
@dataclass
class Question:
    question_text: str
    question_type: str
    options: List[str]  # 选择题选项
    correct_answer: str
    explanation: str
    difficulty: int
```

## 5. 处理流程

### 5.1 文档处理流程图
```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ 文件上传 │────▶│ 创建任务 │────▶│ 保存文件 │
└──────────┘     └──────────┘     └──────────┘
                                       │
                                       ▼
┌──────────┐     ┌──────────┐     ┌──────────┐
│ 完成通知 │◀────│ 异步处理 │◀────│ SSE连接  │
└──────────┘     └──────────┘     └──────────┘
```

### 5.2 异步处理流程
```
1. 解析文档
   ├─ PDF → 文本提取
   └─ DOCX → 文本提取

2. 文本清洗
   ├─ 去除特殊字符
   └─ 格式化处理

3. 智能分块
   ├─ 500字符/块
   └─ 100字符重叠

4. 题目生成
   ├─ 调用AI API
   ├─ 生成题目
   └─ 验证质量

5. 保存结果
   ├─ 写入数据库
   └─ 更新统计
```

### 5.3 进度更新流程
```
5%  - 开始解析文档
7%  - 显示PDF页数（如果适用）
15% - 解析完成，显示文档长度
25% - 创建数据库记录
26% - 开始文本处理
27% - 文本清洗完成
30% - 分块完成
35% - 开始生成题目
70% - 题目生成中（动态更新）
90% - 保存到数据库
100%- 处理完成
```

## 6. 错误处理

### 6.1 错误类型
- **文件格式错误**：不支持的文件类型
- **文件损坏**：无法解析的文件
- **API错误**：DeepSeek API调用失败
- **数据库错误**：存储失败
- **网络错误**：上传或下载失败

### 6.2 错误响应
```json
{
    "success": false,
    "error": "错误描述",
    "error_code": "ERROR_CODE",
    "details": {
        "step": "发生错误的步骤",
        "retry_able": true
    }
}
```

### 6.3 重试机制
- API调用失败：自动重试3次
- 数据库操作：事务回滚
- 文件处理：记录错误日志


## 7. 扩展计划

### 7.1 短期扩展
- 支持更多文档格式（TXT、EPUB）
- 题目难度自动分级
- 批量导入功能
- 题目预览和编辑

### 7.2 长期扩展
- 多语言支持
- 智能题目推荐
- 协作编辑功能
- 题库分享机制

## 8. 附录

### 8.1 配置参数
```python
# 文件处理配置
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
SUPPORTED_TYPES = ['.pdf', '.docx', '.doc']

# AI生成配置
DEFAULT_CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
MAX_RETRIES = 3

# 性能配置
WORKER_THREADS = 4
QUEUE_SIZE = 100
CLEANUP_INTERVAL = 300  # 5分钟
```

### 8.2 部署要求
- Python 3.8+
- PostgreSQL 12+
- 4GB+ RAM
- 50GB+ 存储空间

---

*文档版本: v1.0*
*最后更新: 2025-11-15*