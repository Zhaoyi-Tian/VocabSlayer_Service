#!/usr/bin/env python3
"""
路径处理工具模块
确保无论从哪里运行都能正确导入模块
"""
import os
import sys
from pathlib import Path

def setup_project_paths():
    """
    设置项目路径，确保可以正确导入所有模块
    """
    # 获取当前文件的目录
    current_dir = Path(__file__).parent.absolute()

    # 项目根目录（VocabSlayer_update_servier）
    project_root = current_dir

    # 将项目根目录添加到Python路径
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

    # 同时将common目录添加到路径
    common_dir = project_root / "common"
    common_dir_str = str(common_dir)
    if common_dir_str not in sys.path:
        sys.path.insert(0, common_dir_str)

    return project_root, common_dir

def get_project_root():
    """获取项目根目录"""
    return Path(__file__).parent.absolute()

def get_common_dir():
    """获取common目录"""
    return get_project_root() / "common"

def get_server_dir():
    """获取server目录"""
    return get_project_root() / "server"

# 自动设置路径
_project_root, _common_dir = setup_project_paths()

# 测试导入
def test_imports():
    """测试关键模块是否可以导入"""
    print("测试模块导入...")
    print(f"项目根目录: {_project_root}")
    print(f"Common目录: {_common_dir}")
    print(f"Python路径: {sys.path[:3]}...")  # 只显示前3个

    modules = [
        ("database_manager", "common.database_manager"),
        ("document_parser", "common.document_parser"),
        ("text_processor", "common.text_processor"),
        ("question_generator", "common.question_generator"),
        ("database_adapter", "common.database_adapter"),
    ]

    success = True
    for name, module_path in modules:
        try:
            __import__(module_path)
            print(f"  ✓ {name}")
        except ImportError as e:
            print(f"  ✗ {name}: {e}")
            success = False

    return success

if __name__ == "__main__":
    test_imports()