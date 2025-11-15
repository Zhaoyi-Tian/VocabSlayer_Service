"""
文本处理器模块
负责文本清洗、智能分块和关键信息提取
"""
import re
import logging
from typing import List, Optional, Tuple
from dataclasses import dataclass

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TextChunk:
    """文本块数据类"""
    content: str                # 文本内容
    index: int                   # 块索引
    start_pos: int              # 在原文中的起始位置
    end_pos: int                # 在原文中的结束位置
    metadata: dict = None       # 额外元数据

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class TextProcessor:
    """文本处理器类"""

    def __init__(self,
                 chunk_size: int = 500,
                 chunk_overlap: int = 100,
                 min_chunk_size: int = 100):
        """
        初始化文本处理器

        Args:
            chunk_size: 目标文本块大小（字符数），默认500
            chunk_overlap: 块之间的重叠大小（上下文），默认100
            min_chunk_size: 最小块大小
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def clean_text(self, text: str) -> str:
        """
        清洗文本，移除不必要的格式和噪音

        Args:
            text: 原始文本

        Returns:
            清洗后的文本
        """
        if not text:
            return ""

        # 保存原始长度用于日志
        original_length = len(text)

        # 1. 替换特殊空白字符
        text = re.sub(r'[\u00A0\u2002-\u200B\uFEFF]', ' ', text)  # 特殊空格
        text = re.sub(r'\r\n', '\n', text)  # 统一换行符
        text = re.sub(r'\r', '\n', text)

        # 2. 移除控制字符（但保留换行符和制表符）
        text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)

        # 3. 清理多余的空格和换行
        text = re.sub(r' {2,}', ' ', text)  # 多个空格替换为单个
        text = re.sub(r'\n{3,}', '\n\n', text)  # 最多保留两个换行
        text = re.sub(r'(\n\s*){3,}', '\n\n', text)  # 清理带空格的空行

        # 4. 移除页眉页脚常见模式
        patterns_to_remove = [
            r'^第\s*\d+\s*页.*$',          # 中文页码
            r'^Page\s*\d+.*$',              # 英文页码
            r'^\d+\s*/\s*\d+$',             # 页码格式 1/10
            r'^-\s*\d+\s*-$',               # - 1 - 格式
            r'^\s*\d+\s*$',                 # 独立数字行
            r'^_{10,}$',                    # 长下划线
            r'^-{10,}$',                    # 长横线
            r'^={10,}$',                    # 长等号线
        ]

        lines = text.split('\n')
        cleaned_lines = []

        for line in lines:
            # 检查是否匹配任何要移除的模式
            should_remove = False
            for pattern in patterns_to_remove:
                if re.match(pattern, line.strip(), re.IGNORECASE):
                    should_remove = True
                    break

            if not should_remove:
                cleaned_lines.append(line)

        text = '\n'.join(cleaned_lines)

        # 5. 移除首尾空白
        text = text.strip()

        logger.info(f"文本清洗完成: {original_length} -> {len(text)} 字符")
        return text

    def chunk_text(self, text: str,
                   method: str = "recursive") -> List[TextChunk]:
        """
        将文本分割成块

        Args:
            text: 要分割的文本
            method: 分割方法 ('recursive', 'paragraph', 'sentence', 'fixed')

        Returns:
            文本块列表
        """
        if not text:
            return []

        if method == "recursive":
            return self._recursive_chunk(text)
        elif method == "paragraph":
            return self._paragraph_chunk(text)
        elif method == "sentence":
            return self._sentence_chunk(text)
        elif method == "fixed":
            return self._fixed_chunk(text)
        else:
            raise ValueError(f"不支持的分块方法: {method}")

    def _recursive_chunk(self, text: str) -> List[TextChunk]:
        """
        递归分块：优先按段落，然后按句子，最后按字符

        Args:
            text: 要分割的文本

        Returns:
            文本块列表
        """
        chunks = []
        current_pos = 0

        # 分割符优先级
        separators = [
            "\n\n",  # 双换行（段落）
            "\n",    # 单换行
            "。",    # 中文句号
            ".",     # 英文句号
            "！",    # 中文感叹号
            "!",     # 英文感叹号
            "？",    # 中文问号
            "?",     # 英文问号
            "；",    # 中文分号
            ";",     # 英文分号
            " ",     # 空格
        ]

        def split_text(text: str, separators: List[str]) -> List[str]:
            """递归使用分隔符分割文本"""
            if not separators:
                # 没有更多分隔符，按固定长度分割
                return self._split_by_size(text, self.chunk_size)

            separator = separators[0]
            parts = text.split(separator)

            if len(parts) == 1:
                # 当前分隔符无效，尝试下一个
                return split_text(text, separators[1:])

            result = []
            current_chunk = ""

            for i, part in enumerate(parts):
                # 添加分隔符（除了最后一个部分）
                if i < len(parts) - 1:
                    part = part + separator

                if len(current_chunk) + len(part) <= self.chunk_size:
                    current_chunk += part
                else:
                    if current_chunk:
                        result.append(current_chunk)

                    # 如果单个部分超过块大小，递归分割
                    if len(part) > self.chunk_size:
                        sub_parts = split_text(part, separators[1:])
                        result.extend(sub_parts[:-1])
                        current_chunk = sub_parts[-1] if sub_parts else ""
                    else:
                        current_chunk = part

            if current_chunk:
                result.append(current_chunk)

            return result

        # 执行分割
        text_parts = split_text(text, separators)

        # 创建带重叠的块
        for i, part in enumerate(text_parts):
            # 添加前一个块的结尾作为重叠
            if i > 0 and self.chunk_overlap > 0:
                overlap_text = text_parts[i-1][-self.chunk_overlap:]
                part = overlap_text + part

            chunk = TextChunk(
                content=part.strip(),
                index=i,
                start_pos=current_pos,
                end_pos=current_pos + len(part),
                metadata={'method': 'recursive'}
            )

            if len(chunk.content) >= self.min_chunk_size:
                chunks.append(chunk)
                current_pos += len(part)

        logger.info(f"递归分块完成: {len(text)} 字符 -> {len(chunks)} 块")
        return chunks

    def _paragraph_chunk(self, text: str) -> List[TextChunk]:
        """
        按段落分块

        Args:
            text: 要分割的文本

        Returns:
            文本块列表
        """
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""
        current_pos = 0
        chunk_index = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # 如果当前块加上新段落不超过限制，就合并
            if len(current_chunk) + len(para) + 2 <= self.chunk_size:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
            else:
                # 保存当前块
                if current_chunk and len(current_chunk) >= self.min_chunk_size:
                    chunk = TextChunk(
                        content=current_chunk,
                        index=chunk_index,
                        start_pos=current_pos,
                        end_pos=current_pos + len(current_chunk),
                        metadata={'method': 'paragraph'}
                    )
                    chunks.append(chunk)
                    chunk_index += 1
                    current_pos += len(current_chunk) + 2

                # 如果段落本身超过块大小，需要进一步分割
                if len(para) > self.chunk_size:
                    sub_chunks = self._split_large_paragraph(para, chunk_index, current_pos)
                    chunks.extend(sub_chunks)
                    chunk_index += len(sub_chunks)
                    current_pos += len(para) + 2
                    current_chunk = ""
                else:
                    current_chunk = para

        # 保存最后一个块
        if current_chunk and len(current_chunk) >= self.min_chunk_size:
            chunk = TextChunk(
                content=current_chunk,
                index=chunk_index,
                start_pos=current_pos,
                end_pos=current_pos + len(current_chunk),
                metadata={'method': 'paragraph'}
            )
            chunks.append(chunk)

        logger.info(f"段落分块完成: {len(text)} 字符 -> {len(chunks)} 块")
        return chunks

    def _sentence_chunk(self, text: str) -> List[TextChunk]:
        """
        按句子分块

        Args:
            text: 要分割的文本

        Returns:
            文本块列表
        """
        # 句子分割正则表达式
        sentence_pattern = r'([。．.!?！？;；])\s*'
        sentences = re.split(sentence_pattern, text)

        # 重组句子（包含标点符号）
        full_sentences = []
        for i in range(0, len(sentences)-1, 2):
            if i+1 < len(sentences):
                full_sentences.append(sentences[i] + sentences[i+1])
            else:
                full_sentences.append(sentences[i])

        chunks = []
        current_chunk = ""
        current_pos = 0
        chunk_index = 0

        for sent in full_sentences:
            sent = sent.strip()
            if not sent:
                continue

            if len(current_chunk) + len(sent) + 1 <= self.chunk_size:
                if current_chunk:
                    current_chunk += " " + sent
                else:
                    current_chunk = sent
            else:
                if current_chunk and len(current_chunk) >= self.min_chunk_size:
                    chunk = TextChunk(
                        content=current_chunk,
                        index=chunk_index,
                        start_pos=current_pos,
                        end_pos=current_pos + len(current_chunk),
                        metadata={'method': 'sentence'}
                    )
                    chunks.append(chunk)
                    chunk_index += 1
                    current_pos += len(current_chunk) + 1

                current_chunk = sent

        # 保存最后一个块
        if current_chunk and len(current_chunk) >= self.min_chunk_size:
            chunk = TextChunk(
                content=current_chunk,
                index=chunk_index,
                start_pos=current_pos,
                end_pos=current_pos + len(current_chunk),
                metadata={'method': 'sentence'}
            )
            chunks.append(chunk)

        logger.info(f"句子分块完成: {len(text)} 字符 -> {len(chunks)} 块")
        return chunks

    def _fixed_chunk(self, text: str) -> List[TextChunk]:
        """
        固定大小分块

        Args:
            text: 要分割的文本

        Returns:
            文本块列表
        """
        chunks = []
        chunk_index = 0

        for i in range(0, len(text), self.chunk_size - self.chunk_overlap):
            chunk_text = text[i:i + self.chunk_size]

            if len(chunk_text) >= self.min_chunk_size:
                chunk = TextChunk(
                    content=chunk_text,
                    index=chunk_index,
                    start_pos=i,
                    end_pos=min(i + self.chunk_size, len(text)),
                    metadata={'method': 'fixed'}
                )
                chunks.append(chunk)
                chunk_index += 1

        logger.info(f"固定分块完成: {len(text)} 字符 -> {len(chunks)} 块")
        return chunks

    def _split_large_paragraph(self, para: str, start_index: int, start_pos: int) -> List[TextChunk]:
        """
        分割超大段落

        Args:
            para: 段落文本
            start_index: 起始块索引
            start_pos: 起始位置

        Returns:
            文本块列表
        """
        # 尝试按句子分割
        sentence_pattern = r'([。．.!?！？;；])\s*'
        sentences = re.split(sentence_pattern, para)

        chunks = []
        current_chunk = ""
        chunk_index = start_index

        for i in range(0, len(sentences)-1, 2):
            sent = sentences[i]
            if i+1 < len(sentences):
                sent += sentences[i+1]

            if len(current_chunk) + len(sent) <= self.chunk_size:
                current_chunk += sent
            else:
                if current_chunk:
                    chunk = TextChunk(
                        content=current_chunk,
                        index=chunk_index,
                        start_pos=start_pos,
                        end_pos=start_pos + len(current_chunk),
                        metadata={'method': 'split_paragraph'}
                    )
                    chunks.append(chunk)
                    chunk_index += 1
                    start_pos += len(current_chunk)

                current_chunk = sent

        if current_chunk:
            chunk = TextChunk(
                content=current_chunk,
                index=chunk_index,
                start_pos=start_pos,
                end_pos=start_pos + len(current_chunk),
                metadata={'method': 'split_paragraph'}
            )
            chunks.append(chunk)

        return chunks

    def _split_by_size(self, text: str, size: int) -> List[str]:
        """
        按固定大小分割文本

        Args:
            text: 文本
            size: 块大小

        Returns:
            文本列表
        """
        return [text[i:i+size] for i in range(0, len(text), size)]

    def extract_key_points(self, text: str) -> List[str]:
        """
        提取文本中的关键点

        Args:
            text: 文本内容

        Returns:
            关键点列表
        """
        key_points = []

        # 1. 提取标题（以#开头或数字编号开头）
        title_patterns = [
            r'^#+\s+(.+)$',                    # Markdown标题
            r'^(\d+\.?\s+.+)$',                 # 数字编号
            r'^([一二三四五六七八九十]+、.+)$',  # 中文编号
            r'^([A-Z]\.?\s+.+)$',               # 字母编号
        ]

        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            for pattern in title_patterns:
                match = re.match(pattern, line)
                if match:
                    key_points.append(match.group(1) if match.group(1) else match.group(0))
                    break

        # 2. 提取列表项（以-、*、·开头）
        list_patterns = [
            r'^[-*·•]\s+(.+)$',
            r'^（\d+）\s*(.+)$',
            r'^\(\d+\)\s*(.+)$',
        ]

        for line in lines:
            line = line.strip()
            for pattern in list_patterns:
                match = re.match(pattern, line)
                if match:
                    key_points.append(match.group(1))
                    break

        # 3. 提取重要术语（加粗、引号等）
        # 查找加粗文本
        bold_pattern = r'\*\*([^*]+)\*\*'
        bold_matches = re.findall(bold_pattern, text)
        key_points.extend(bold_matches)

        # 查找引号内容
        quote_pattern = r'["""](.*?)["""]'
        quote_matches = re.findall(quote_pattern, text)
        key_points.extend([m for m in quote_matches if len(m) < 50])  # 只保留较短的引用

        # 去重并返回
        return list(set(key_points))

    def get_text_statistics(self, text: str) -> dict:
        """
        获取文本统计信息

        Args:
            text: 文本内容

        Returns:
            统计信息字典
        """
        stats = {
            'total_chars': len(text),
            'total_words': len(text.split()),
            'total_lines': len(text.split('\n')),
            'total_paragraphs': len(text.split('\n\n')),
            'avg_paragraph_length': 0,
            'has_chinese': bool(re.search(r'[\u4e00-\u9fff]', text)),
            'has_english': bool(re.search(r'[a-zA-Z]', text)),
        }

        paragraphs = [p for p in text.split('\n\n') if p.strip()]
        if paragraphs:
            stats['avg_paragraph_length'] = sum(len(p) for p in paragraphs) / len(paragraphs)

        return stats

    def smart_chunk_with_context(self, text: str) -> List[TextChunk]:
        """
        智能分块，保留上下文并使用省略号

        Args:
            text: 原文本

        Returns:
            文本块列表，每块500字，保留100字上下文
        """
        if not text or len(text) <= self.chunk_size:
            return [TextChunk(content=text, index=0, start_pos=0, end_pos=len(text))]

        chunks = []
        start = 0
        index = 0

        while start < len(text):
            # 计算块的结束位置
            end = start + self.chunk_size

            # 获取主块内容
            if end >= len(text):
                chunk_text = text[start:]
            else:
                chunk_text = text[start:end]

            # 添加前置上下文
            if index > 0:
                context_start = max(0, start - self.chunk_overlap)
                context_text = text[context_start:start]
                # 检查是否需要省略号
                if context_start > 0:
                    # 在第一个标点或换行处截断
                    first_punct = self._find_first_punctuation_or_newline(context_text)
                    if first_punct > 0:
                        chunk_text = "..." + context_text[first_punct+1:] + chunk_text
                    else:
                        chunk_text = "..." + context_text + chunk_text
                else:
                    chunk_text = context_text + chunk_text

            # 添加后置上下文
            if end < len(text):
                context_end = min(len(text), end + self.chunk_overlap)
                context_text = text[end:context_end]
                # 检查是否需要省略号
                if context_end < len(text):
                    # 在第一个标点或换行处截断
                    first_punct = self._find_first_punctuation_or_newline(context_text)
                    if first_punct > 0:
                        chunk_text = chunk_text + context_text[:first_punct] + "..."
                    else:
                        chunk_text = chunk_text + context_text[:50] + "..."
                else:
                    chunk_text = chunk_text + context_text

            # 创建文本块
            chunk = TextChunk(
                content=chunk_text,
                index=index,
                start_pos=start,
                end_pos=min(end, len(text)),
                metadata={"has_context": index > 0 or end < len(text)}
            )

            chunks.append(chunk)

            # 计算下一个块的起始位置（考虑重叠）
            start = end - self.chunk_overlap if end < len(text) else end
            index += 1

        logger.info(f"智能分块完成：{len(text)} 字符 -> {len(chunks)} 块")
        return chunks

    def _find_first_punctuation_or_newline(self, text: str) -> int:
        """
        查找第一个标点符号或换行符的位置

        Args:
            text: 要搜索的文本

        Returns:
            第一个标点或换行符的位置，如果找不到返回-1
        """
        punctuations = ['。', '！', '？', '；', '：', '，', '、', '\n', '\r\n']

        min_pos = -1
        for punct in punctuations:
            pos = text.find(punct)
            if pos != -1 and (min_pos == -1 or pos < min_pos):
                min_pos = pos

        return min_pos


if __name__ == "__main__":
    # 测试代码
    sample_text = """
    第一章 介绍

    这是一个测试文档的第一段。这段包含了一些基本信息，用于测试文本处理功能。
    文本处理是自然语言处理中的重要步骤。

    第二章 方法

    我们使用了多种方法来处理文本：
    - 文本清洗：移除无用字符
    - 文本分块：将长文本分成合适的块
    - 关键点提取：识别重要信息

    这些方法可以有效提高后续处理的效率。
    """

    # 创建处理器
    processor = TextProcessor(chunk_size=200, chunk_overlap=50)

    # 清洗文本
    clean_text = processor.clean_text(sample_text)
    print("清洗后的文本:")
    print(clean_text)
    print("\n" + "="*50 + "\n")

    # 分块
    chunks = processor.chunk_text(clean_text, method="recursive")
    print(f"文本分块 (共{len(chunks)}块):")
    for chunk in chunks:
        print(f"块 {chunk.index}: {len(chunk.content)} 字符")
        print(f"内容: {chunk.content[:100]}...")
        print()

    # 提取关键点
    key_points = processor.extract_key_points(clean_text)
    print("关键点:")
    for point in key_points:
        print(f"- {point}")

    # 获取统计信息
    stats = processor.get_text_statistics(clean_text)
    print("\n统计信息:")
    for key, value in stats.items():
        print(f"{key}: {value}")