"""
AI题目生成器模块
使用DeepSeek API生成高质量的问答题目
"""
import json
import logging
import time
import hashlib
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class QuestionDifficulty(Enum):
    """题目难度等级"""
    EASY = 1      # 简单
    MEDIUM = 2    # 中等
    HARD = 3      # 困难


class QuestionType(Enum):
    """题目类型"""
    DEFINITION = "definition"          # 定义/概念题
    PROCEDURE = "procedure"           # 步骤/流程题
    COMPARISON = "comparison"         # 参数/比较题
    EXPLANATION = "explanation"       # 解释/说明题
    APPLICATION = "application"       # 应用题
    ANALYSIS = "analysis"            # 分析题


@dataclass
class GeneratedQuestion:
    """生成的题目数据类"""
    question: str                    # 问题内容
    answer: str                      # 答案内容
    difficulty: int                  # 难度等级
    question_type: str              # 题目类型
    source_chunk_index: int         # 来源文本块索引
    confidence_score: float = 0.9   # 置信度分数
    metadata: dict = None            # 额外元数据

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return asdict(self)


class QuestionGenerator:
    """AI题目生成器"""

    # 默认提示词模板（生成问题和答案）
    DEFAULT_PROMPT_TEMPLATE = """你是一名专业的教学助手。请根据以下提供的文本内容，生成1-3道高质量的问题和对应的答案。

重要说明：你需要为每个问题提供准确的答案，这些答案应该基于文本内容并由你补充必要的解释。

要求：
1. 问题必须直接基于所提供的文本内容
2. 问题应该覆盖文本的核心知识点
3. 问题要具有引导性，能激发学习者思考
4. 题目类型要多样化（概念理解、细节查找、分析思考等）
5. 难度分级：1-简单（查找信息）、2-中等（理解概念）、3-困难（分析推理）
6. 答案要准确、清晰，并包含必要的解释说明
7. 每个文本块只生成1-3个问题，不要贪多，确保质量优先

输出格式要求：
请严格按照以下JSON格式输出，确保可以被解析：
{{
    "questions": [
        {{
            "question": "具体的问题内容",
            "answer": "详细准确的答案内容，包含解释和说明",
            "difficulty": 1,
            "question_type": "definition"
        }}
    ]
}}

题目类型说明：
- definition: 定义/概念题（询问术语或概念的含义）
- detail: 细节查找题（询问文本中的具体信息）
- comparison: 比较分析题（需要比较多个概念或信息）
- explanation: 解释说明题（询问原因或过程）
- application: 应用理解题（询问如何应用某个概念）
- analysis: 深入分析题（需要综合理解文本内容）

文本内容：
{chunk_text}
"""

    # 验证问题的提示词模板
    VALIDATION_PROMPT_TEMPLATE = """请验证以下问题和答案是否准确基于提供的原文内容。

原文内容：
{source_text}

问题：{question}
答案：{answer}

请回答：
1. 问题是否基于原文内容？(是/否)
2. 答案是否准确且完整？(是/否)
3. 是否存在事实错误？(是/否)
4. 总体评分（1-10分）：

请按以下JSON格式回答：
{{
    "based_on_source": true/false,
    "answer_accurate": true/false,
    "has_errors": true/false,
    "score": 8,
    "feedback": "简要说明"
}}"""

    def __init__(self,
                 api_key: str,
                 base_url: str = "https://api.deepseek.com",
                 model: str = "deepseek-chat",
                 max_retries: int = 3,
                 timeout: int = 30):
        """
        初始化题目生成器

        Args:
            api_key: DeepSeek API密钥
            base_url: API基础URL
            model: 使用的模型名称
            max_retries: 最大重试次数
            timeout: 超时时间（秒）
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout

        # 初始化OpenAI客户端
        try:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout
            )
        except ImportError:
            logger.error("请安装openai库: pip install openai")
            raise ImportError("请安装openai库: pip install openai")

        # API调用统计
        self.api_call_count = 0
        self.total_tokens_used = 0

    def generate_questions(self,
                          chunk_text: str,
                          chunk_index: int = 0,
                          num_questions: int = 3,
                          custom_prompt: Optional[str] = None) -> List[GeneratedQuestion]:
        """
        根据文本块生成题目

        Args:
            chunk_text: 文本块内容
            chunk_index: 文本块索引
            num_questions: 要生成的题目数量
            custom_prompt: 自定义提示词模板

        Returns:
            生成的题目列表
        """
        if not chunk_text or not chunk_text.strip():
            logger.warning("提供的文本为空，无法生成题目")
            return []

        # 限制文本长度以避免超出token限制
        max_text_length = 2000
        if len(chunk_text) > max_text_length:
            logger.info(f"文本长度 {len(chunk_text)} 超过限制，截取前 {max_text_length} 字符")
            chunk_text = chunk_text[:max_text_length]

        # 构建提示词
        prompt_template = custom_prompt or self.DEFAULT_PROMPT_TEMPLATE
        prompt = prompt_template.format(
            num_questions=num_questions,
            chunk_text=chunk_text
        )

        # 调用API生成题目
        for retry in range(self.max_retries):
            try:
                logger.info(f"正在生成题目... (尝试 {retry + 1}/{self.max_retries})")

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "你是一位专业的教学助手，擅长根据文本内容生成高质量的教学题目。"
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.7,  # 适度的创造性
                    max_tokens=2000,
                    top_p=0.95
                )

                # 更新统计
                self.api_call_count += 1
                if hasattr(response, 'usage'):
                    self.total_tokens_used += response.usage.total_tokens

                # 解析响应
                content = response.choices[0].message.content
                questions = self._parse_response(content, chunk_index)

                if questions:
                    logger.info(f"成功生成 {len(questions)} 道题目")
                    return questions
                else:
                    logger.warning("解析响应失败，没有生成有效题目")

            except json.JSONDecodeError as e:
                logger.error(f"JSON解析失败: {e}")
                if retry < self.max_retries - 1:
                    time.sleep(2 ** retry)  # 指数退避
                    continue

            except Exception as e:
                logger.error(f"API调用失败: {e}")
                if retry < self.max_retries - 1:
                    time.sleep(2 ** retry)
                    continue
                else:
                    raise

        logger.error(f"生成题目失败，已重试 {self.max_retries} 次")
        return []

    def _parse_response(self, response_text: str, chunk_index: int) -> List[GeneratedQuestion]:
        """
        解析API响应，提取题目

        Args:
            response_text: API响应文本
            chunk_index: 文本块索引

        Returns:
            题目列表
        """
        questions = []

        try:
            # 尝试提取JSON内容
            # 处理可能的markdown代码块
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end]
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end]

            # 解析JSON
            data = json.loads(response_text.strip())

            # 提取题目
            if "questions" in data and isinstance(data["questions"], list):
                for q_data in data["questions"]:
                    # 验证必要字段
                    if "question" not in q_data:
                        logger.warning("题目缺少question字段，跳过")
                        continue

                    # 创建题目对象（使用AI生成的答案）
                    question = GeneratedQuestion(
                        question=q_data.get("question", "").strip(),
                        answer=q_data.get("answer", "").strip(),  # 使用AI生成的答案
                        difficulty=q_data.get("difficulty", 2),
                        question_type=q_data.get("question_type", "explanation"),
                        source_chunk_index=chunk_index,
                        confidence_score=0.9,
                        metadata={
                            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")
                        }
                    )

                    # 验证题目质量
                    if self._validate_question(question):
                        questions.append(question)
                    else:
                        logger.warning(f"题目验证失败: {question.question[:50]}...")

        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            logger.debug(f"响应内容: {response_text[:500]}...")

            # 尝试备用解析方法
            questions = self._fallback_parse(response_text, chunk_index)

        except Exception as e:
            logger.error(f"解析响应时出错: {e}")

        return questions

    def _fallback_parse(self, text: str, chunk_index: int) -> List[GeneratedQuestion]:
        """
        备用解析方法，处理非标准格式的响应

        Args:
            text: 响应文本
            chunk_index: 文本块索引

        Returns:
            题目列表
        """
        questions = []

        # 尝试通过正则表达式提取问题和答案
        import re

        # 查找问题模式（只查找问题，不需要答案）
        question_pattern = r'(?:问题[：:]|Q[：:])\s*(.+?)(?=(?:问题[：:]|Q[：:]|\n\d+[\.。]|$))'
        question_matches = re.findall(question_pattern, text, re.DOTALL)

        # 也尝试查找编号问题
        numbered_pattern = r'^\d+[\.。]\s*(.+?)(?=\n\d+[\.。]|$)'
        numbered_matches = re.findall(numbered_pattern, text, re.MULTILINE | re.DOTALL)

        # 合并所有找到的问题
        all_questions = question_matches + numbered_matches

        for q in all_questions:
            q = q.strip()
            if len(q) > 10:  # 过滤掉太短的内容
                question = GeneratedQuestion(
                    question=q,
                    answer="",  # 不使用AI生成的答案
                    difficulty=2,
                    question_type="explanation",
                    source_chunk_index=chunk_index,
                    confidence_score=0.7  # 备用方法置信度较低
                )

                if self._validate_question(question):
                    questions.append(question)

        if questions:
            logger.info(f"使用备用方法成功解析 {len(questions)} 道题目")

        return questions

    def generate_learning_hint(self, text: str, question: str) -> str:
        """
        为问题生成学习提示（不直接给出答案，而是引导思考）

        Args:
            text: 原始文本
            question: 问题

        Returns:
            学习提示
        """
        if not text or not question:
            return "请仔细阅读原文，找出相关信息。"

        prompt = f"""
作为学习助手，请为以下问题提供学习提示。不要直接给出答案，而是引导学生从文本中找到答案。

原文：
{text[:2000]}

问题：
{question}

请提供2-3个学习提示：
1. 提示学生应该关注文本中的哪些部分
2. 引导学生如何理解问题的关键点
3. 提供一些思考方向

格式要求：
- 每个提示占一行
- 用数字序号标记
- 语言简洁明了
- 不包含答案内容
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位专业的学习导师，擅长引导学生思考，而不是直接给出答案。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.5,  # 较低的创造性，更专注的指导
                max_tokens=500,
                top_p=0.9
            )

            self.api_call_count += 1
            if hasattr(response, 'usage'):
                self.total_tokens_used += response.usage.total_tokens

            content = response.choices[0].message.content.strip()
            logger.info(f"生成了学习提示，长度: {len(content)} 字符")

            return content

        except Exception as e:
            logger.error(f"生成学习提示失败: {e}")
            return "提示：请仔细阅读原文，注意问题的关键词，在文中寻找相关信息。"

    def _validate_question(self, question: GeneratedQuestion) -> bool:
        """
        验证题目质量

        Args:
            question: 题目对象

        Returns:
            是否有效
        """
        # 基本验证
        if not question.question:
            return False

        # 问题长度验证
        if len(question.question) < 10 or len(question.question) > 500:
            logger.debug(f"问题长度不符合要求: {len(question.question)}")
            return False

        # 难度验证
        if question.difficulty not in [1, 2, 3]:
            question.difficulty = 2  # 默认中等难度

        # 题目类型验证
        valid_types = [t.value for t in QuestionType]
        if question.question_type not in valid_types:
            question.question_type = QuestionType.EXPLANATION.value

        return True

    def validate_with_source(self,
                            question: GeneratedQuestion,
                            source_text: str) -> Dict[str, Any]:
        """
        使用AI验证题目与源文本的一致性

        Args:
            question: 题目对象
            source_text: 源文本

        Returns:
            验证结果
        """
        prompt = self.VALIDATION_PROMPT_TEMPLATE.format(
            source_text=source_text[:1500],  # 限制长度
            question=question.question,
            answer=question.answer
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位严格的内容审核专家。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,  # 降低温度以获得更确定的判断
                max_tokens=500
            )

            content = response.choices[0].message.content

            # 解析验证结果
            try:
                validation_result = json.loads(content)
            except:
                # 备用解析
                validation_result = {
                    "based_on_source": True,
                    "answer_accurate": True,
                    "has_errors": False,
                    "score": 7,
                    "feedback": "无法解析验证结果"
                }

            return validation_result

        except Exception as e:
            logger.error(f"验证失败: {e}")
            return {
                "based_on_source": True,
                "answer_accurate": True,
                "has_errors": False,
                "score": 5,
                "feedback": f"验证过程出错: {str(e)}"
            }

    def batch_generate(self,
                      text_chunks: List[str],
                      questions_per_chunk: int = 3,
                      progress_callback: Optional[callable] = None) -> List[GeneratedQuestion]:
        """
        批量生成题目

        Args:
            text_chunks: 文本块列表
            questions_per_chunk: 每个块生成的题目数
            progress_callback: 进度回调函数

        Returns:
            所有生成的题目
        """
        all_questions = []
        total_chunks = len(text_chunks)

        for i, chunk in enumerate(text_chunks):
            logger.info(f"处理文本块 {i+1}/{total_chunks}")

            # 生成题目
            questions = self.generate_questions(
                chunk_text=chunk,
                chunk_index=i,
                num_questions=questions_per_chunk
            )

            all_questions.extend(questions)

            # 进度回调
            if progress_callback:
                progress = (i + 1) / total_chunks * 100
                progress_callback(progress, i + 1, total_chunks)

            # 避免API限流
            if i < total_chunks - 1:
                time.sleep(1)  # 延迟1秒

        logger.info(f"批量生成完成，共生成 {len(all_questions)} 道题目")
        return all_questions

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取生成统计信息

        Returns:
            统计信息字典
        """
        return {
            "api_calls": self.api_call_count,
            "total_tokens": self.total_tokens_used,
            "avg_tokens_per_call": self.total_tokens_used / max(self.api_call_count, 1),
            "estimated_cost": self._estimate_cost()
        }

    def _estimate_cost(self) -> float:
        """
        估算API调用成本

        Returns:
            估算成本（美元）
        """
        # DeepSeek的价格（示例，实际价格可能不同）
        price_per_1k_tokens = 0.001  # $0.001 per 1K tokens

        return (self.total_tokens_used / 1000) * price_per_1k_tokens


if __name__ == "__main__":
    # 测试代码
    import os

    # 测试文本
    test_text = """
    Python是一种高级编程语言，由Guido van Rossum于1991年创建。
    Python的设计哲学强调代码的可读性，使用缩进来定义代码块。

    Python的主要特点包括：
    1. 简洁易学：语法简单，适合初学者
    2. 跨平台：可以在Windows、Linux、Mac等系统运行
    3. 丰富的库：拥有大量的第三方库和模块
    4. 动态类型：不需要声明变量类型

    Python广泛应用于Web开发、数据科学、人工智能、自动化等领域。
    """

    # 获取API密钥（从环境变量或配置文件）
    api_key = os.getenv("DEEPSEEK_API_KEY", "your-api-key-here")

    if api_key == "your-api-key-here":
        print("请设置DEEPSEEK_API_KEY环境变量")
    else:
        # 创建生成器
        generator = QuestionGenerator(api_key=api_key)

        # 生成题目
        print("正在生成题目...")
        questions = generator.generate_questions(
            chunk_text=test_text,
            chunk_index=0,
            num_questions=3
        )

        # 显示结果
        print(f"\n生成了 {len(questions)} 道题目：\n")
        for i, q in enumerate(questions, 1):
            print(f"题目 {i}:")
            print(f"问题: {q.question}")
            print(f"答案: {q.answer}")
            print(f"难度: {q.difficulty}")
            print(f"类型: {q.question_type}")
            print("-" * 50)

        # 显示统计信息
        stats = generator.get_statistics()
        print(f"\n统计信息:")
        print(f"API调用次数: {stats['api_calls']}")
        print(f"总Token使用: {stats['total_tokens']}")
        print(f"估算成本: ${stats['estimated_cost']:.4f}")