"""诊断脚本 - 排查 query 接口问题"""
import sys
import os
# 添加项目根目录到 Python 路径 (与 __init__.py 保持一致)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from backend.its_knowledge.config.settings import settings
from backend.its_knowledge.repositories.vector_store_repository import VectorStoreRepository
from backend.its_knowledge.services.retrieval_service import RetrievalService
from backend.its_knowledge.services.query_service import QueryService

def test_config():
    """测试配置是否正确"""
    print("=" * 50)
    print("1. 检查配置")
    print(f"   API_KEY: {settings.API_KEY[:20]}..." if settings.API_KEY else "   API_KEY: 未设置!")
    print(f"   BASE_URL: {settings.BASE_URL}")
    print(f"   MODEL: {settings.MODEL}")
    print(f"   EMBEDDING_MODEL: {settings.EMBEDDING_MODEL}")
    print(f"   VECTOR_STORE_PATH: {settings.VECTOR_STORE_PATH}")
    print(f"   CRAWL_OUTPUT_DIR: {settings.CRAWL_OUTPUT_DIR}")
    return True

def test_vector_store():
    """测试向量数据库"""
    print("=" * 50)
    print("2. 检查向量数据库")
    try:
        repo = VectorStoreRepository()
        # 尝试检索
        results = repo.search_similarity_with_score("电脑黑屏", k=3)
        print(f"   检索结果数量: {len(results)}")
        if results:
            for doc, score in results[:2]:
                print(f"   - 文档标题: {doc.metadata.get('title', '无标题')}")
                print(f"   - 内容片段: {doc.page_content[:100]}...")
                print(f"   - 分数: {score}")
        else:
            print("   [WARN] 向量数据库中没有数据！需要先运行 upload_cli.py 入库")
        return len(results) > 0
    except Exception as e:
        print(f"   [FAIL] 向量数据库错误: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_embedding():
    """测试 embedding 功能"""
    print("=" * 50)
    print("3. 测试 Embedding 模型")
    try:
        repo = VectorStoreRepository()
        embedding = repo.embedd_document("测试文本")
        print(f"   [OK] Embedding 成功，向量长度: {len(embedding)}")
        return True
    except Exception as e:
        print(f"   [FAIL] Embedding 错误: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_retrieval():
    """测试检索服务"""
    print("=" * 50)
    print("4. 测试检索服务")
    try:
        service = RetrievalService()
        question = "电脑黑屏了怎么办"
        results = service.retrieval(question)
        print(f"   检索结果数量: {len(results)}")
        if results:
            for doc in results[:2]:
                print(f"   - 标题: {doc.metadata.get('title', '无标题')}")
                print(f"   - 内容: {doc.page_content[:150]}...")
        return True
    except Exception as e:
        print(f"   [FAIL] 检索服务错误: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_llm():
    """测试 LLM 调用"""
    print("=" * 50)
    print("5. 测试 LLM 调用")
    try:
        service = QueryService()
        from langchain_core.documents import Document
        mock_docs = [Document(page_content="测试内容", metadata={"title": "测试文档"})]
        answer = service.query("测试问题", mock_docs)
        print(f"   [OK] LLM 调用成功")
        print(f"   回答: {answer[:100]}...")
        return True
    except Exception as e:
        print(f"   [FAIL] LLM 错误: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n开始诊断 query 接口问题...\n")

    test_config()
    test_embedding()
    has_data = test_vector_store()

    if has_data:
        test_retrieval()
        test_llm()
    else:
        print("\n" + "=" * 50)
        print("诊断结论: 向量数据库中没有数据")
        print("解决方案: 运行 python cli/upload_cli.py 将文档入库")

if __name__ == "__main__":
    main()