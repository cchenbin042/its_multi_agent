from importlib.metadata import metadata
from typing import Any

from backend.its_knowledge.utils.text_utils import TextUtils


class HtmlParser:
    """负责将HTML格式解析为MarkDow的数据格式"""
    @staticmethod
    def parse_html_to_markdown(knowledge_no: int, html_data: dict[str,Any]) -> str:
        """
        将html格式的数据转为markdown格式的数据
        :param html_data: html格式的数据
        :return: markdown格式的数据
        """
        # 判断html数据是否为空
        if not html_data or not html_data.get("content"):
            raise ValueError("html数据为空")
        # 1、从 html_data 中提供 md 格式的数据
        # 1.1、提取知识库的编号
        items = []
        items.append(f'# 知识库 {knowledge_no}\n')
        # 2、提供知识库的标题
        html_data_title = html_data.get("title", "暂无标题")
        items.append(f'## 标题\n{html_data_title.strip()}\n')
        # 2.1、提取知识库的digest（摘要）
        html_data_digest = html_data.get("digest")
        if html_data_digest and html_data_digest.strip():
            items.append(f'## 问题描述\n{html_data_digest.strip()}\n')

        # 2.2、提取知识库的分类（分类系）
        # firstTopicName（主分类）、subTopicName（子分类）| questionCategoryName（问题对应的分类）
        first_topic_name = html_data.get("firstTopicName")
        sub_topic_name = html_data.get("subTopicName")
        question_category_name = html_data.get("questionCategoryName")
        categories = []

        if first_topic_name and first_topic_name.strip():
            categories.append(f'主分类：\n{first_topic_name.strip()}')

        if sub_topic_name and sub_topic_name.strip():
            categories.append(f'子分类：\n{sub_topic_name.strip()}')
        elif question_category_name and question_category_name.strip():
            categories.append(f'问题对应的分类：\n{question_category_name.strip()}')

        if categories:
            items.append(f'## 分类\n'+"\n".join(categories)+'\n')

        # 2.3、提取知识库关键词：打散、清洗在组合【用途：1、在相似性检索中作为关键字；2、提高召回率】
        html_data_key_words = html_data["keyWords"]
        key_words_lists = []
        if html_data_key_words:
            for key_word in html_data_key_words:
                if isinstance(key_word, str):
                    # 过滤掉空字符串  ['U盘装系统,U盘系统盘,安装,win7,U盘']
                    key_words_lists.extend([key_word.strip() for key_word in key_word.split(",") if key_word.strip()])

            if key_words_lists:
                key_word_str = ",".join(key_words_lists)
                items.append(f'## 关键词\n{(key_word_str)}\n')

        # 2.4、构建元信息（时效性、版本）
        metadata_data = []
        create_time = html_data.get("createTime")
        version_no = html_data.get("versionNo")
        if create_time and create_time.strip():
            metadata_data.append(f'创建时间:{create_time.strip()}')
        if version_no and version_no.strip():
            metadata_data.append(f'版本:{version_no.strip()}')

        if metadata_data:
            items.append(f'## 元信息\n{" | ".join(metadata_data)}\n')
        # 2.5、构建知识库内容
        html_data_content = html_data.get("content")
        if html_data_content:
            # 1、调用工具将html数据清洗和解析成md
            # 2、清洗的本质是将html格式的数据进行压缩，并去除无用的标签
            md_content = TextUtils.html_to_markdown(html_data_content)
            items.append(f'## 解决方案\n' +md_content +'\n')

        # 2.6、构建标题作为知识库的注释（防止切块后导致上下文丢失）
        items.append(f'<!-- 文档主题: {html_data_title.strip()} （知识库编号: {knowledge_no}） -->\n')

        return "\n".join(items)