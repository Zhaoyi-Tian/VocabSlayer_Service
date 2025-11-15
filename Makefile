# Makefile for VocabSlayer Leaderboard Service
# 使用 clang++ 编译器

# 编译器配置
CXX = clang++
CXXFLAGS = -std=c++11 -Wall -O2
LDFLAGS = -lpq

# 目标文件
TARGET = leaderboard_service
SOURCE = leaderboard_service.cpp

# 默认目标
all: $(TARGET)

# 编译主程序
$(TARGET): $(SOURCE)
	@echo "正在编译 $(TARGET)..."
	$(CXX) $(CXXFLAGS) -o $(TARGET) $(SOURCE) $(LDFLAGS)
	@echo "✓ 编译完成: $(TARGET)"
	@echo ""
	@echo "使用方法:"
	@echo "  ./$(TARGET)                                    # 使用默认配置"
	@echo "  ./$(TARGET) host port dbname user password    # 自定义配置"
	@echo ""

# 清理编译产物
clean:
	@echo "清理编译文件..."
	rm -f $(TARGET)
	@echo "✓ 清理完成"

# 运行程序（使用默认配置）
run: $(TARGET)
	./$(TARGET)

# 运行程序（带参数）
run-custom: $(TARGET)
	./$(TARGET) localhost 5432 vocabulary_db openEuler Qq13896842746

# 检查编译器和依赖
check:
	@echo "检查编译环境..."
	@echo -n "Clang 版本: "
	@$(CXX) --version | head -n 1
	@echo -n "libpq 库: "
	@pkg-config --exists libpq && echo "✓ 已安装" || echo "✗ 未找到"
	@echo ""

# 帮助信息
help:
	@echo "VocabSlayer 排行榜服务 Makefile"
	@echo ""
	@echo "可用目标:"
	@echo "  make          - 编译排行榜服务"
	@echo "  make clean    - 清理编译文件"
	@echo "  make run      - 运行排行榜服务（默认配置）"
	@echo "  make check    - 检查编译环境"
	@echo "  make help     - 显示此帮助信息"
	@echo ""

.PHONY: all clean run run-custom check help
