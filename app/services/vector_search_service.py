"""向量检索服务模块"""

from typing import Any

from loguru import logger

from app.services.vector_store_manager import vector_store_manager


class SearchResult:
    """搜索结果类"""

    def __init__(
        self,
        id: str,
        content: str,
        score: float,
        metadata: dict[str, Any],
    ):
        self.id = id
        self.content = content
        self.score = score
        self.metadata = metadata

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "content": self.content,
            "score": self.score,
            "metadata": self.metadata,
        }


class VectorSearchService:
    """向量检索服务 - 负责从 Chroma 中搜索相似文档"""

    def __init__(self):
        """初始化向量检索服务"""
        logger.info("向量检索服务初始化完成")

    def search_similar_documents(self, query: str, top_k: int = 3) -> list[SearchResult]:
        """
        搜索相似文档

        Args:
            query: 查询文本
            top_k: 返回最相似的K个结果

        Returns:
            List[SearchResult]: 搜索结果列表

        Raises:
            RuntimeError: 搜索失败时抛出
        """
        try:
            logger.info(f"开始搜索相似文档, 查询: {query}, topK: {top_k}")

            results = vector_store_manager.get_vector_store().similarity_search_with_score(
                query,
                k=top_k,
            )

            search_results = [
                SearchResult(
                    id=str(doc.metadata.get("id") or doc.metadata.get("_source") or index),
                    content=doc.page_content,
                    score=float(score),
                    metadata=doc.metadata,
                )
                for index, (doc, score) in enumerate(results, 1)
            ]

            logger.info(f"搜索完成, 找到 {len(search_results)} 个相似文档")
            return search_results

        except Exception as e:
            logger.error(f"搜索相似文档失败: {e}")
            raise RuntimeError(f"搜索失败: {e}") from e


# 全局单例
vector_search_service = VectorSearchService()
