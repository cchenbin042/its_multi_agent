import  os
import re
from typing import List,Dict,Any


class MarkDownUtils:
    """
     MarkDown文档处理工具
    """

    @staticmethod
    def collect_md_metadata(folder_path: str) -> List[Dict[str, Any]]:
        """
        收集Markdown文件元数据

        遍历指定目录，提取所有Markdown文件的路径和标题信息。

        Args:
            folder_path: Markdown文件所在目录

        Returns:
            List[Dict[str, Any]]: 包含路径和标题的元数据列表
        """
        md_metadata = []
        if not os.path.exists(folder_path):
            return md_metadata

        # 正则匹配文件名格式：编号-标题.md
        filename_pattern = re.compile(r'^(.+?)-(.*?)\.md$')

        for filename in os.listdir(folder_path):
            if filename.endswith('.md'):
                match = filename_pattern.match(filename)
                if match:
                    title = match.group(2).strip()
                else:
                    title = os.path.splitext(filename)[0].strip()

                md_metadata.append({
                    "path": os.path.join(folder_path, filename),
                    "title": title
                })
        return md_metadata

    @staticmethod
    def extract_title(file_path: str) -> str:
        """
        辅助方法：从文件名中提取标题
        逻辑与 MarkDownUtils 保持一致
        """
        filename = os.path.basename(file_path)
        filename_pattern = re.compile(r'^(.+?)-(.*?)\.md$')
        match = filename_pattern.match(filename)
        if match:
            # 提取正则分组的第2部分作为标题
            return match.group(2).strip()
        else:
            # 匹配失败则使用文件名（去后缀）
            return os.path.splitext(filename)[0].strip()
