"""
文档处理功能测试脚本
测试PDF/Word文档解析、文本分块和题目生成功能
"""
import os
import sys
import json
import time
import logging
from pathlib import Path

# 添加父目录到路径，以便导入模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入模块
from common.document_parser import ParserFactory, extract_document_text
from common.text_processor import TextProcessor
from common.question_generator import QuestionGenerator

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_document_parser():
    """测试文档解析功能"""
    print("\n" + "="*60)
    print("测试文档解析功能")
    print("="*60)

    # 测试文件路径（需要替换为实际路径）
    test_files = {
        'pdf': "/path/to/test/document.pdf",
        'docx': "/path/to/test/document.docx"
    }

    for file_type, file_path in test_files.items():
        print(f"\n测试 {file_type.upper()} 解析...")

        if not os.path.exists(file_path):
            print(f"  跳过：文件不存在 - {file_path}")
            continue

        try:
            # 获取解析器
            parser = ParserFactory.get_parser(file_path)
            print(f"  解析器类型: {type(parser).__name__}")

            # 提取文本
            start_time = time.time()
            text = parser.extract_text(file_path)
            elapsed = time.time() - start_time

            print(f"  解析成功: {len(text)} 字符, 耗时: {elapsed:.2f} 秒")

            # 显示前200字符
            print(f"  文本预览: {text[:200]}...")

        except Exception as e:
            print(f"  解析失败: {e}")


def test_text_processor():
    """测试文本处理功能"""
    print("\n" + "="*60)
    print("测试文本处理功能")
    print("="*60)

    # 测试文本
    test_text = """
    # Python编程基础

    Python是一种高级编程语言，由Guido van Rossum于1991年创建。
    Python的设计哲学强调代码的可读性，使用缩进来定义代码块。

    ## 主要特点

    1. 简洁易学：语法简单，适合初学者入门。
    2. 跨平台：可以在Windows、Linux、Mac等系统上运行。
    3. 丰富的库：拥有大量的第三方库和模块。
    4. 动态类型：不需要声明变量类型，变量类型会自动推断。

    ## 应用领域

    Python广泛应用于以下领域：
    - Web开发：使用Django、Flask等框架
    - 数据科学：使用NumPy、Pandas、Matplotlib等库
    - 人工智能：使用TensorFlow、PyTorch等框架
    - 自动化脚本：编写各种自动化工具

    Python解释器的工作方式是逐行执行代码。
    这使得Python非常适合交互式编程和快速原型开发。
    """

    # 创建处理器
    processor = TextProcessor(chunk_size=200, chunk_overlap=50)

    print(f"原始文本长度: {len(test_text)} 字符")

    # 清洗文本
    clean_text = processor.clean_text(test_text)
    print(f"\n清洗后长度: {len(clean_text)} 字符")
    print("清洗后预览:")
    print(clean_text[:300] + "...")

    # 测试不同的分块方法
    methods = ["recursive", "paragraph", "sentence"]
    for method in methods:
        print(f"\n测试 {method} 分块方法:")
        chunks = processor.chunk_text(clean_text, method=method)
        print(f"  生成块数: {len(chunks)}")
        for i, chunk in enumerate(chunks[:3]):  # 只显示前3块
            print(f"  块 {i+1}: {len(chunk.content)} 字符")
            print(f"    内容: {chunk.content[:80]}...")

    # 提取关键点
    key_points = processor.extract_key_points(clean_text)
    print(f"\n提取的关键点 ({len(key_points)} 个):")
    for point in key_points[:5]:
        print(f"  - {point}")

    # 获取统计信息
    stats = processor.get_text_statistics(clean_text)
    print(f"\n文本统计:")
    for key, value in stats.items():
        print(f"  {key}: {value}")


def test_question_generation():
    """测试题目生成功能"""
    print("\n" + "="*60)
    print("测试题目生成功能")
    print("="*60)

    # 检查API密钥
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("错误: 请设置 DEEPSEEK_API_KEY 环境变量")
        print("  export DEEPSEEK_API_KEY='your-api-key'")
        return

    # 测试文本
    test_chunks = [
        """
        人工智能（Artificial Intelligence, AI）是计算机科学的一个分支，
        致力于创建能够执行通常需要人类智能的任务的系统。
        这些任务包括学习、推理、问题解决、感知和语言理解。
        """,
        """
        机器学习是人工智能的一个子集，它使计算机系统能够从数据中学习
        和改进，而无需明确编程。机器学习算法通过训练数据来构建模型，
        然后使用这些模型对新数据进行预测或决策。
        """,
        """
        深度学习是机器学习的一个更深层次的子集，它使用人工神经网络
        来模拟人脑的工作方式。深度神经网络具有多个隐藏层，
        可以学习数据的复杂模式和表示。深度学习在图像识别、
        自然语言处理和语音识别等领域取得了突破性进展。
        """
    ]

    # 创建生成器
    generator = QuestionGenerator(
        api_key=api_key,
        model="deepseek-chat"
    )

    print("开始生成题目...")

    for i, chunk in enumerate(test_chunks, 1):
        print(f"\n--- 处理文本块 {i} ---")
        print(f"文本内容: {chunk.strip()[:100]}...")

        try:
            # 生成题目
            start_time = time.time()
            questions = generator.generate_questions(
                chunk_text=chunk,
                chunk_index=i-1,
                num_questions=2
            )
            elapsed = time.time() - start_time

            print(f"生成成功: {len(questions)} 道题目, 耗时: {elapsed:.2f} 秒")

            # 显示生成的题目
            for j, q in enumerate(questions, 1):
                print(f"\n题目 {j}:")
                print(f"  问题: {q.question}")
                print(f"  答案: {q.answer[:200]}...")
                print(f"  难度: {q.difficulty}")
                print(f"  类型: {q.question_type}")
                print(f"  置信度: {q.confidence_score}")

        except Exception as e:
            print(f"生成失败: {e}")

    # 显示统计信息
    stats = generator.get_statistics()
    print(f"\n生成器统计:")
    print(f"  API调用次数: {stats['api_calls']}")
    print(f"  总Token使用: {stats['total_tokens']}")
    print(f"  平均每次调用Token: {stats['avg_tokens_per_call']}")
    print(f"  估算成本: ${stats['estimated_cost']:.4f}")


def test_end_to_end():
    """端到端测试"""
    print("\n" + "="*60)
    print("端到端测试")
    print("="*60)

    # 检查是否有测试文件
    test_file = input("请输入测试文档路径 (PDF或DOCX): ").strip()

    if not test_file or not os.path.exists(test_file):
        print("文件不存在，使用模拟文本测试")
        return test_text_processor() and test_question_generation()

    # 检查API密钥
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("错误: 请设置 DEEPSEEK_API_KEY 环境变量")
        return False

    try:
        # 1. 解析文档
        print("\n1. 解析文档...")
        text = extract_document_text(test_file)
        print(f"   提取文本长度: {len(text)} 字符")

        # 2. 文本处理
        print("\n2. 文本处理...")
        processor = TextProcessor(chunk_size=500, chunk_overlap=100)
        clean_text = processor.clean_text(text)
        chunks = processor.chunk_text(clean_text, method="recursive")
        print(f"   文本分块: {len(chunks)} 块")

        # 3. 生成题目
        print("\n3. 生成题目...")
        generator = QuestionGenerator(api_key=api_key)
        all_questions = []

        for i, chunk in enumerate(chunks[:3]):  # 只处理前3块
            print(f"   处理块 {i+1}/{min(3, len(chunks))}")
            questions = generator.generate_questions(
                chunk_text=chunk.content,
                chunk_index=i,
                num_questions=2
            )
            all_questions.extend(questions)

        print(f"\n✅ 测试完成!")
        print(f"   总共生成: {len(all_questions)} 道题目")

        # 保存结果
        if all_questions:
            output_file = "generated_questions.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump([q.to_dict() for q in all_questions], f, ensure_ascii=False, indent=2)
            print(f"   结果已保存到: {output_file}")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("VocabSlayer 文档处理功能测试")
    print("=" * 60)

    # 测试菜单
    print("\n请选择测试项目:")
    print("1. 测试文档解析")
    print("2. 测试文本处理")
    print("3. 测试题目生成")
    print("4. 端到端测试")
    print("5. 运行所有测试")

    choice = input("\n请输入选项 (1-5): ").strip()

    if choice == "1":
        test_document_parser()
    elif choice == "2":
        test_text_processor()
    elif choice == "3":
        test_question_generation()
    elif choice == "4":
        test_end_to_end()
    elif choice == "5":
        test_document_parser()
        test_text_processor()
        test_question_generation()
        test_end_to_end()
    else:
        print("无效选项")

    print("\n测试完成!")


if __name__ == "__main__":
    main()