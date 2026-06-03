"""向量存储管理器 - 封装 Chroma VectorStore 操作"""

from typing import Any, cast

from langchain_core.documents import Document
from loguru import logger

from app.config import config
from app.services.vector_embedding_service import get_vector_embedding_service


class VectorStoreManager:
    """向量存储管理器"""

    def __init__(self):
        """初始化向量存储管理器"""
        self.vector_store: Any = None
        self.collection_name = config.chroma_collection_name

    def _initialize_vector_store(self):
        """初始化 Chroma VectorStore"""
        if self.vector_store is not None:
            return self.vector_store

        try:
            from langchain_chroma import Chroma

            config.chroma_path.mkdir(parents=True, exist_ok=True)
            # Chroma 是本项目默认知识库后端，降低 Linux 单机部署复杂度。
            self.vector_store = Chroma(
                embedding_function=get_vector_embedding_service(),
                collection_name=self.collection_name,
                persist_directory=str(config.chroma_path),
            )

            logger.info(
                f"Chroma VectorStore 初始化成功: {config.chroma_path}, collection: {self.collection_name}"
            )
            return self.vector_store

        except Exception as e:
            logger.error(f"VectorStore 初始化失败: {e}")
            raise

    def add_documents(self, documents: list[Document]) -> list[str]:
        """
        批量添加文档到向量存储（自动批量向量化）

        Args:
            documents: 文档列表

        Returns:
            List[str]: 文档 ID 列表
        """
        try:
            import time
            import uuid

            start_time = time.time()
            vector_store = self.get_vector_store()

            # 为每个文档生成唯一 id（因为 auto_id=False）
            ids = [str(uuid.uuid4()) for _ in documents]

            # Chroma 的 add_documents 会自动调用 embedding_function 并进行批量处理。
            result_ids = vector_store.add_documents(documents, ids=ids)

            elapsed = time.time() - start_time
            logger.info(
                f"批量添加 {len(documents)} 个文档到 VectorStore 完成, "
                f"耗时: {elapsed:.2f}秒, 平均: {elapsed / len(documents):.2f}秒/个"
            )
            return cast(list[str], result_ids)
        except Exception as e:
            logger.error(f"添加文档失败: {e}")
            raise

    def delete_by_source(self, file_path: str) -> int:
        """
        删除指定文件的所有文档

        优先使用 Chroma 公开 API（get / delete），降级时通过内部 _collection
        访问，确保在 Chroma 版本迁移后仍能工作。

        Args:
            file_path: 文件路径

        Returns:
            int: 删除的文档数量
        """
        try:
            vector_store = self.get_vector_store()
            # 优先尝试 Chroma 公开的 get / delete 方法
            try:
                existing = vector_store.get(where={"_source": file_path})
            except TypeError:
                # Chroma >= 0.6 可能不接受 get() 的 where 参数
                existing = {}
            ids = existing.get("ids", []) if existing else []
            if not ids:
                # 降级：通过内部 _collection 访问（兼容旧版本 Chroma）
                collection = getattr(vector_store, "_collection", None)
                if collection is not None:
                    existing = collection.get(where={"_source": file_path}) or {}
                    ids = existing.get("ids", [])
            if ids:
                vector_store.delete(ids=ids)
            logger.info(f"删除文件旧数据: {file_path}, 删除数量: {len(ids)}")
            return len(ids)

        except Exception as e:
            logger.warning(f"删除旧数据失败 (可能是首次索引): {e}")
            return 0

    def get_vector_store(self):
        """
        获取 VectorStore 实例

        Returns:
            Chroma: VectorStore 实例
        """
        return self._initialize_vector_store()

    def similarity_search(self, query: str, k: int = 3) -> list[Document]:
        """
        相似度搜索

        Args:
            query: 查询文本
            k: 返回结果数量

        Returns:
            List[Document]: 相关文档列表
        """
        try:
            vector_store = self.get_vector_store()
            docs = vector_store.similarity_search(query, k=k)
            logger.debug(f"相似度搜索完成: query='{query}', 结果数={len(docs)}")
            return cast(list[Document], docs)
        except Exception as e:
            logger.error(f"相似度搜索失败: {e}")
            return []


# 全局单例
vector_store_manager = VectorStoreManager()
