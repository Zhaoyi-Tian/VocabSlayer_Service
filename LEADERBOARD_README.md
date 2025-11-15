# VocabSlayer 排行榜服务

## 📋 概述

VocabSlayer 排行榜服务是一个使用 C++ 编写的高性能实时排行榜系统，直接连接 openGauss 数据库，提供多维度的学习统计和排名。

## ✨ 功能特性

### 排行榜类型

1. **📅 今日学习排行榜**
   - 统计当天的答题数量
   - 显示正确率
   - 实时更新

2. **📊 本周学习排行榜**
   - 统计最近7天的答题数量
   - 显示平均正确率
   - 激励短期学习

3. **📈 本月学习排行榜**
   - 统计本月累计答题数量
   - 显示平均正确率
   - 月度竞争榜单

4. **🏆 历史总排行榜**
   - 统计所有时间的累计答题数
   - 显示平均正确率
   - 长期学习榜单

5. **🎯 正确率排行榜**
   - 按正确率排序
   - 需要最少50题门槛（可配置）
   - 鼓励质量优先

6. **📚 学习单词数排行榜**
   - 统计学习过的不重复单词数量
   - 显示平均掌握程度
   - 词汇量竞赛

### 技术特性

- ✅ 使用 C++11 标准编写
- ✅ 使用 libpq 直接连接 openGauss 数据库
- ✅ 定时自动刷新（默认60秒）
- ✅ 内存高效，性能优异
- ✅ 支持多种排序规则
- ✅ 命令行友好输出
- ✅ 易于扩展为 Web API

## 🛠️ 编译和安装

### 系统要求

- openEuler 操作系统
- GCC 10.3.1 或更高版本
- libpq 开发库（PostgreSQL 客户端库）
- openGauss 数据库运行中

### 检查环境

```bash
# 进入服务目录
cd /home/openEuler/openGauss/VocabSlayer_update/server

# 检查编译环境
make check
```

### 编译

```bash
# 编译排行榜服务
make

# 编译完成后会生成 leaderboard_service 可执行文件
```

### 清理

```bash
# 清理编译产物
make clean
```

## 🚀 使用方法

### 方式一：直接运行

```bash
# 使用默认配置运行（localhost, port 5432, vocabulary_db）
./leaderboard_service

# 使用自定义配置运行
./leaderboard_service <host> <port> <dbname> <user> <password>

# 示例
./leaderboard_service localhost 5432 vocabulary_db openEuler Qq13896842746
```

### 方式二：使用管理脚本（推荐）

```bash
# 启动服务（后台运行）
./leaderboard.sh start

# 停止服务
./leaderboard.sh stop

# 重启服务
./leaderboard.sh restart

# 查看服务状态
./leaderboard.sh status

# 查看实时日志
./leaderboard.sh logs
```

## 📊 输出示例

```
============================================================
  📅 今日学习排行榜 (答题数)
============================================================
排名  用户名           得分         正确率
------------------------------------------------------------
1       tianzhaoyi          43             37.1           %
2       tianzhaoyi2         6              50.0           %
3       zhaoyi              0              0.0            %
============================================================
```

## 🔧 配置说明

### 数据库连接配置

编辑 `leaderboard.sh` 中的数据库配置：

```bash
DB_HOST="localhost"      # 数据库主机
DB_PORT="5432"           # 数据库端口
DB_NAME="vocabulary_db"  # 数据库名称
DB_USER="openEuler"      # 数据库用户
DB_PASS="Qq13896842746"  # 数据库密码
```

### 刷新间隔配置

编辑 `leaderboard_service.cpp` 中的刷新间隔：

```cpp
int refreshInterval = 60; // 刷新间隔（秒），默认60秒
```

修改后需要重新编译：

```bash
make clean
make
```

### 排行榜显示数量

修改各个排行榜函数的 `limit` 参数（默认显示前10名）：

```cpp
auto todayBoard = getTodayLeaderboard(20);  // 显示前20名
```

## 📁 文件结构

```
server/
├── leaderboard_service.cpp  # C++ 主程序源码
├── leaderboard_service      # 编译后的可执行文件
├── Makefile                 # 编译脚本
├── leaderboard.sh           # 服务管理脚本
└── LEADERBOARD_README.md    # 本文档
```

## 🔍 数据源说明

排行榜数据来自以下数据库表：

1. **users** - 用户基本信息
2. **user_daily_stats** - 用户每日统计数据
   - `total_questions` - 答题总数
   - `correct_answers` - 答对数量
   - `accuracy` - 正确率（自动计算）
   - `date` - 日期

3. **user_learning_records** - 用户学习记录
   - `vocab_id` - 学习的单词ID
   - `star` - 掌握程度（0-3星）

## 🌐 扩展为 Web 服务

当前版本是命令行工具，未来可以扩展为 Web API：

### 方案1：使用 cpp-httplib

添加 HTTP 服务器功能，提供 RESTful API：

```cpp
GET /api/leaderboard/today      # 今日排行榜
GET /api/leaderboard/weekly     # 本周排行榜
GET /api/leaderboard/monthly    # 本月排行榜
GET /api/leaderboard/all-time   # 历史总榜
GET /api/leaderboard/accuracy   # 正确率榜
GET /api/leaderboard/vocabulary # 单词数榜
```

### 方案2：使用 Python Flask

创建 Python Web 服务调用 C++ 程序或直接查询数据库。

### 方案3：使用 Go/Rust

重写为 Go 或 Rust Web 服务，性能更好。

## 🐛 故障排除

### 编译错误：找不到 libpq

```bash
# 安装 PostgreSQL 开发库
sudo yum install postgresql-devel
# 或
sudo yum install libpq-devel
```

### 运行时错误：连接数据库失败

1. 检查 openGauss 是否运行：
   ```bash
   ps aux | grep gaussdb
   ```

2. 检查数据库端口：
   ```bash
   netstat -tlnp | grep 5432
   ```

3. 检查数据库连接参数是否正确

### 运行时警告：no version information available

这是库版本兼容性警告，不影响功能，可以忽略。

## 📈 性能优化建议

1. **数据库索引**
   - 已在 `user_daily_stats` 表的 `user_id` 和 `date` 字段建立索引
   - 已在 `user_learning_records` 表建立复合索引

2. **查询优化**
   - 使用了 `LEFT JOIN` 确保显示所有用户
   - 使用 `COALESCE` 处理 NULL 值
   - 限制返回行数（LIMIT）

3. **缓存策略**（未来）
   - 可以将排行榜结果缓存到 Redis
   - 减少数据库查询频率
   - 实现秒级更新

## 🔒 安全建议

1. **不要在代码中硬编码密码**
   - 使用环境变量或配置文件
   - 生产环境使用密钥管理系统

2. **限制数据库权限**
   - 排行榜服务只需要 SELECT 权限
   - 不需要 INSERT/UPDATE/DELETE 权限

3. **网络安全**
   - 如果对外提供服务，使用 HTTPS
   - 实现访问频率限制（Rate Limiting）
   - 添加身份验证

## 📝 更新日志

### v1.0.0 (2025-10-29)

- ✅ 初始版本发布
- ✅ 实现6种排行榜类型
- ✅ 支持定时自动刷新
- ✅ 提供服务管理脚本
- ✅ 使用 openEuler GCC 编译

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

---

**VocabSlayer 排行榜服务** - 让学习更有动力！🚀
