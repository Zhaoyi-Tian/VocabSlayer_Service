#!/bin/bash
# VocabSlayer 排行榜服务启动脚本

# 数据库配置
DB_HOST="localhost"
DB_PORT="5432"
DB_NAME="vocabulary_db"
DB_USER="openEuler"
DB_PASS="Qq13896842746"

# 服务配置
SERVICE_NAME="leaderboard_service"
PID_FILE="/tmp/leaderboard_service.pid"
LOG_FILE="/tmp/leaderboard_service.log"

# 切换到服务目录
cd "$(dirname "$0")"

# 函数：启动服务
start_service() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            echo "❌ 排行榜服务已经在运行中 (PID: $PID)"
            return 1
        else
            rm -f "$PID_FILE"
        fi
    fi

    echo "🚀 启动排行榜服务..."
    nohup ./$SERVICE_NAME "$DB_HOST" "$DB_PORT" "$DB_NAME" "$DB_USER" "$DB_PASS" > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "✓ 排行榜服务已启动 (PID: $(cat $PID_FILE))"
    echo "  日志文件: $LOG_FILE"
    echo "  使用 'tail -f $LOG_FILE' 查看实时日志"
}

# 函数：停止服务
stop_service() {
    if [ ! -f "$PID_FILE" ]; then
        echo "❌ 排行榜服务未运行"
        return 1
    fi

    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null 2>&1; then
        echo "🛑 停止排行榜服务 (PID: $PID)..."
        kill $PID
        sleep 2

        if ps -p $PID > /dev/null 2>&1; then
            echo "⚠️  服务未响应，强制终止..."
            kill -9 $PID
        fi

        rm -f "$PID_FILE"
        echo "✓ 排行榜服务已停止"
    else
        echo "❌ 进程不存在，清理 PID 文件"
        rm -f "$PID_FILE"
    fi
}

# 函数：查看服务状态
status_service() {
    if [ ! -f "$PID_FILE" ]; then
        echo "📊 状态: 未运行"
        return 1
    fi

    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null 2>&1; then
        echo "📊 状态: 运行中"
        echo "   PID: $PID"
        echo "   日志: $LOG_FILE"
        echo ""
        echo "最近日志:"
        tail -n 20 "$LOG_FILE"
    else
        echo "📊 状态: 已停止（PID 文件存在但进程不存在）"
        rm -f "$PID_FILE"
    fi
}

# 函数：重启服务
restart_service() {
    echo "🔄 重启排行榜服务..."
    stop_service
    sleep 2
    start_service
}

# 函数：查看日志
view_logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        echo "❌ 日志文件不存在: $LOG_FILE"
    fi
}

# 主逻辑
case "$1" in
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    status)
        status_service
        ;;
    logs)
        view_logs
        ;;
    *)
        echo "VocabSlayer 排行榜服务管理脚本"
        echo ""
        echo "用法: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "命令说明:"
        echo "  start   - 启动排行榜服务"
        echo "  stop    - 停止排行榜服务"
        echo "  restart - 重启排行榜服务"
        echo "  status  - 查看服务状态"
        echo "  logs    - 查看实时日志"
        echo ""
        exit 1
        ;;
esac

exit 0
