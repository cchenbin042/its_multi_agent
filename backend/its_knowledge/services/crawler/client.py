import os.path

from backend.its_knowledge.config import settings
import requests

from backend.its_knowledge.services.crawler.parser import HtmlParser


class KnowledgeApiClient:
    """提供方法，获取网络知识"""

    @staticmethod
    def fetch_knowledge_content(knowledge_no: int) -> str:
        """根据知识库编号，获取联想知识库内容"""  # https://iknow.lenovo.com.cn/detail/430569
        try:
           # url = 'https://iknow.lenovo.com.cn/knowledgeapi/api/knowledge/knowledgeDetails'
            url = f'{settings.KNOWLEDGE_BASE_URL}/knowledgeapi/api/knowledge/knowledgeDetails'
            params = {'knowledgeNo': knowledge_no}
            response = requests.get(url=url, params=params, timeout=20)
            response.raise_for_status()
                
            data = response.json().get('data', {})
            if not data:
                print(f"知识库 {knowledge_no} 返回数据为空")
                return {}
            return data
                
        except requests.exceptions.Timeout:
            print(f"请求超时：知识库 {knowledge_no}")
            return ""
        except requests.exceptions.HTTPError as e:
            print(f"HTTP 错误 {response.status_code}: {e}")
            return ""
        except requests.exceptions.RequestException as e:
            print(f"网络请求异常：{e}")
            return ""
        except (KeyError, ValueError) as e:
            print(f"响应数据解析失败：{e}")
            return ""

if __name__ == "__main__":
    html_data = KnowledgeApiClient.fetch_knowledge_content(1000)
    print(html_data)
    # md_data = HtmlParser.parse_html_to_markdown(1, html_data)
    # # 写入文件
    # file_name_path = os.path.dirname(__file__) # 获取当前文件所在目录
    # file_name = os.path.join(file_name_path, "test.md")
    # with open(file_name, 'w', encoding='utf-8') as f:
    #     f.write(md_data)
        