# VocabSlayer API服务器

集成文档处理功能的自定义题库API服务器。

## 功能特点

- 支持PDF和Word文档解析
- 使用DeepSeek API生成智能题目
- 完整的数据库集成
- 每个用户使用自己的API密钥
- 支持文档去重（基于文件哈希）
- RESTful API接口

## 快速启动

### 1. 启动服务器

```bash
cd /home/openEuler/openGauss/VocabSlayer_servier/VocabSlayer_update_servier
python start_server.py
```

或者使用原始脚本：

```bash
./start_vocabslayer_server.sh
```

### 2. 验证服务器运行

```bash
curl http://10.129.211.118:5000/api/health
```

应该返回：

```json
{
  "status": "ok",
  "message": "VocabSlayer API Server is running",
  "timestamp": "2025-01-14T...",
  "modules": {
    "document_parser": true,
    "text_processor": true,
    "question_generator": true,
    "database": true
  }
}
```

## API接口

### 1. 上传文档生成题库

```
POST /api/upload
Content-Type: multipart/form-data

参数：
- file: 上传的PDF或Word文件
- user_id: 用户ID
- bank_name: 题库名称
- description: 描述（可选）
- api_key: 用户的DeepSeek API密钥
- chunk_size: 文本块大小（可选，默认1000）
- questions_per_chunk: 每块题目数（可选，默认3）
```

### 2. 获取用户题库列表

```
GET /api/banks/{user_id}
```

### 3. 获取题目（不含答案）

```
GET /api/banks/{bank_id}/questions?user_id={user_id}&limit={limit}
```

### 4. 获取题目（含答案）

```
GET /api/banks/{bank_id}/questions_with_answers?user_id={user_id}
```

### 5. 删除题库

```
DELETE /api/banks/{bank_id}
Body: {"user_id": 1}
```

### 6. 保存答题记录

```
POST /api/answers
Body: {
    "user_id": 1,
    "question_id": 123,
    "is_correct": true,
    "answer_time": 30
}
```

### 7. 获取用户统计

```
GET /api/stats/{user_id}
```

## 文件结构

```
VocabSlayer_update_servier/
├── common/                     # 核心处理模块
│   ├── document_parser.py     # 文档解析
│   ├── text_processor.py      # 文本处理
│   ├── question_generator.py  # AI题目生成
│   ├── database_manager.py    # 数据库管理
│   ├── database_adapter.py    # 数据库适配器
│   └── ...
├── server/                     # API服务器
│   ├── integrated_api_server.py # 集成版API服务器
│   ├── api_server.py          # 原始API服务器
│   ├── start_api_server.py    # 启动脚本
│   └── ...
├── start_server.py            # 简化的启动脚本
└── config.json                # 数据库配置
```

## Windows客户端配置

确保Windows客户端使用以下地址连接：

```python
server_url = "http://10.129.211.118:5000"
```

客户端需要：
1. 在首次使用时配置DeepSeek API密钥
2. 上传PDF或Word文档
3. 等待服务器处理完成
4. 查看生成的题库和题目

## 注意事项

1. **API密钥**：每个用户在客户端输入自己的API密钥，服务器不存储密钥
2. **文件大小限制**：最大50MB
3. **支持格式**：PDF (.pdf) 和 Word (.docx)
4. **文本要求**：文档至少需要100个字符才能生成题目
5. **数据库**：需要先执行SQL脚本创建自定义题库相关表

## 故障排除

### 1. 模块导入失败
确保虚拟环境激活：
```bash
source common/.venv/bin/activate
pip install flask flask-cors PyMuPDF python-docx openai
```

### 2. 数据库连接失败
检查config.json中的数据库配置是否正确

### 3. 文档处理失败
- 确保文档格式正确
- 检查文档内容是否足够
- 验证DeepSeek API密钥是否有效

## 扩展功能

可以轻松添加：
- 任务队列（Celery + Redis）
- 文件存储（对象存储）
- 用户认证
- 题目难度分级
- 批量处理