# backend/its_knowledge/utils/document_converter.py
import os
import re
from typing import List

from langchain_core.documents import Document


class DocumentConverter:
    """
    文档转换器
    将不同格式解析后的内容统一转换为 Markdown 格式
    """

    @staticmethod
    def to_markdown(documents: List[Document], file_ext: str) -> str:
        """
        将 Document 列表转换为 Markdown 格式

        Args:
            documents: Document 列表（由 Loader 解析后的结果）
            file_ext: 文件扩展名（如 .md, .pdf, .docx, .csv）

        Returns:
            str: 转换后的 Markdown 内容
        """
        if not documents:
            return ""

        ext = file_ext.lower()

        if ext in ['.md', '.txt']:
            # Markdown 和文本文件直接返回原始内容
            return DocumentConverter._convert_text(documents)
        elif ext == '.pdf':
            # PDF 合并多页，添加分页标记
            return DocumentConverter._convert_pdf(documents)
        elif ext == '.docx':
            # Word 文档直接返回内容
            return DocumentConverter._convert_text(documents)
        elif ext == '.csv':
            # CSV 转换为 Markdown 表格
            return DocumentConverter._convert_csv(documents)
        else:
            # 未知格式，尝试返回原始内容
            return DocumentConverter._convert_text(documents)

    @staticmethod
    def extract_title(file_path: str) -> str:
        """
        从文件路径提取标题

        支持格式：
        - "编号-标题.扩展名" -> "标题"
        - 普通文件名 -> 去除扩展名

        Args:
            file_path: 文件路径

        Returns:
            str: 提取的标题
        """
        filename = os.path.basename(file_path)
        # 匹配格式：编号-标题.扩展名（如 "001-常见问题汇总.md"）
        # 编号可以是任意字符直到第一个短横线
        pattern = re.compile(r'^(.+?)-(.*?)\.(\w+)$')
        match = pattern.match(filename)
        if match:
            # 提取标题部分（第2个分组）
            return match.group(2).strip()
        else:
            # 普通文件名，去除扩展名
            return os.path.splitext(filename)[0].strip()

    @staticmethod
    def _convert_text(documents: List[Document]) -> str:
        """转换文本类文档（.md, .txt）"""
        return "\n\n".join(doc.page_content for doc in documents)

    @staticmethod
    def _convert_pdf(documents: List[Document]) -> str:
        """转换 PDF 文档，添加分页标记"""
        if len(documents) == 1:
            # 单页不添加分页标记
            return documents[0].page_content

        # 多页添加分页标记
        parts = []
        for i, doc in enumerate(documents):
            page_num = i + 1
            parts.append(f"## Page {page_num}\n\n{doc.page_content}")
        return "\n\n".join(parts)

    @staticmethod
    def _convert_csv(documents: List[Document]) -> str:
        """
        转换 CSV 文档为 Markdown 表格

        CSVLoader 每行生成一个 Document，格式为 "col1: val1, col2: val2"
        """
        if not documents:
            return ""

        # 解析所有行
        all_rows = []
        columns = []

        for doc in documents:
            row_data = DocumentConverter._parse_csv_row(doc.page_content)
            if row_data:
                # 收集所有列名（保持顺序）
                for col in row_data.keys():
                    if col not in columns:
                        columns.append(col)
                all_rows.append(row_data)

        if not columns or not all_rows:
            return ""

        # 构建 Markdown 表格
        lines = []

        # 表头
        header = "| " + " | ".join(columns) + " |"
        lines.append(header)

        # 分隔行
        separator = "| " + " | ".join(["---"] * len(columns)) + " |"
        lines.append(separator)

        # 数据行
        for row_data in all_rows:
            values = [str(row_data.get(col, "")) for col in columns]
            row_line = "| " + " | ".join(values) + " |"
            lines.append(row_line)

        return "\n".join(lines)

    @staticmethod
    def _parse_csv_row(content: str) -> dict:
        """
        解析 CSVLoader 生成的行内容
        格式: "col1: val1, col2: val2"

        Args:
            content: 行内容

        Returns:
            dict: {列名: 值}
        """
        result = {}
        # 分割键值对
        parts = content.split(", ")
        for part in parts:
            if ": " in part:
                key, value = part.split(": ", 1)
                result[key.strip()] = value.strip()
        return result