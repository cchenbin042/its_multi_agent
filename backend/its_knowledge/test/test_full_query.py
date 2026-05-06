
"""完整测试 query 接口"""
import sys
import os
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from backend.its_knowledge.api.routers import query_service, retrieval_service
from backend.its_knowledge.schemas.schema import QueryRequest

def test_full_query():
    """模拟完整查询流程"""
    print("\n测试完整查询流程...")
    question = "我的电脑经常死机怎么办？"
    print(f"问题: {question}")

    try:
        # 1. 检索
        print("\n1. 开始检索...")
        context = retrieval_service.retrieval(question)
        print(f"   检索到 {len(context)} 个文档")

        if context:
            for i, doc in enumerate(context[:3]):
                print(f"   文档{i+1}: {doc.metadata.get('title', '无标题')[:50]}")

        # 2. 生成回答
        print("\n2. 生成回答...")
        answer = query_service.query(question, context)
        print(f"\n回答:\n{answer}")

        return True
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_full_query()