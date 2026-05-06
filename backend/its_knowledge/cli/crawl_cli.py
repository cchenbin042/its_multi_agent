import os
import time
from tqdm import tqdm
from backend.its_knowledge.services.crawler.client import KnowledgeApiClient
from backend.its_knowledge.services.crawler.parser import HtmlParser
from backend.its_knowledge.utils.text_utils import TextUtils
from backend.its_knowledge.config.settings import settings
from backend.its_knowledge.repositories.file_repository import FileRepository


def main():
    """
    爬取知识库内容并保存为MarkDown文件
    Returns:

    """
    success = 0
    fail = 0
    failed_items = []

    total = 1001
    with tqdm(total=total, desc="爬取进度", unit="条", ncols=100) as pbar:
        for i in range(total):
            knowledge_no = i + 1
            pbar.set_postfix_str(f"获取 #{knowledge_no:04d}")

            knowledge_content = KnowledgeApiClient.fetch_knowledge_content(knowledge_no=knowledge_no)

            if knowledge_content and knowledge_content.get('content'):
                # 1.创建HTML解析器
                parser = HtmlParser()

                # 2.解析HTML为MarkDown
                md_content = parser.parse_html_to_markdown(i, knowledge_content)

                # 3.生成语义化文件名 {KnowledgeNo}1-{title}.md
                # 3.1 获取文件名
                md_title = knowledge_content.get('title', "无标题")

                # 3.2 清洗文件名（非法字符处理）
                clean_title = TextUtils.clean_filename(md_title.strip())

                # 3.3 限制文件名长度
                if len(clean_title) > 50:
                    clean_title = clean_title[:50].rstrip("_")

                # 4.构建MarkDown文件名
                file_name = f"{knowledge_no:04d}-{clean_title}.md"

                # 5.构建文件路径
                file_path = os.path.join(settings.CRAWL_OUTPUT_DIR, file_name)

                # 6.保存文件到指定目录
                FileRepository.save_file(md_content, file_path)
                success += 1
                pbar.write(f"✓ {knowledge_no:04d} -> {file_name}")
            else:
                fail += 1
                failed_items.append(knowledge_no)
                pbar.write(f"✗ {knowledge_no:04d} -> 无内容")

            pbar.update(1)
            time.sleep(0.5)

    print(f"\n{'='*50}")
    print(f"爬取完成! 成功: {success}, 失败: {fail}")
    if failed_items:
        print(f"失败条目: {failed_items[:20]}{'...' if len(failed_items) > 20 else ''}")



if __name__ == '__main__':
    main()


















































