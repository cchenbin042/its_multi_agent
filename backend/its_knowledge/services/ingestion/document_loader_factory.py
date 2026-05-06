# backend/its_knowledge/services/ingestion/document_loader_factory.py
import os
from typing import List

from langchain_community.document_loaders import TextLoader, PyPDFLoader, Docx2txtLoader, CSVLoader
from langchain_core.document_loaders import BaseLoader


class DocumentLoaderFactory:
    """
    文档 Loader 工厂类
    根据文件扩展名返回对应的 LangChain Loader
    """
    SUPPORTED_EXTENSIONS: List[str] = ['.md', '.txt', '.pdf', '.docx', '.csv']

    @staticmethod
    def get_loader(file_path: str) -> BaseLoader:
        """
        根据文件扩展名获取对应的 Loader

        Args:
            file_path: 文件路径

        Returns:
            BaseLoader: 对应的 LangChain Loader

        Raises:
            ValueError: 不支持的文件格式
        """
        ext = os.path.splitext(file_path)[1].lower()

        if ext in ['.md', '.txt']:
            return TextLoader(file_path, encoding='utf-8')
        elif ext == '.pdf':
            return PyPDFLoader(file_path)
        elif ext == '.docx':
            return Docx2txtLoader(file_path)
        elif ext == '.csv':
            return CSVLoader(file_path)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")

    @staticmethod
    def is_supported(file_path: str) -> bool:
        """
        检查文件格式是否支持

        Args:
            file_path: 文件路径

        Returns:
            bool: 是否支持该格式
        """
        ext = os.path.splitext(file_path)[1].lower()
        return ext in DocumentLoaderFactory.SUPPORTED_EXTENSIONS

    @staticmethod
    def get_supported_extensions() -> List[str]:
        """
        获取支持的扩展名列表

        Returns:
            List[str]: 支持的扩展名列表
        """
        return DocumentLoaderFactory.SUPPORTED_EXTENSIONS.copy()