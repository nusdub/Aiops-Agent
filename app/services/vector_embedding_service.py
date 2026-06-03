"""向量嵌入服务模块 - 基于 LangChain Embeddings 标准接口"""

import hashlib

from langchain_core.embeddings import Embeddings
from loguru import logger
from openai import OpenAI

from app.config import config


class DashScopeEmbeddings(Embeddings):
    """阿里云 DashScope Text Embedding (OpenAI 兼容模式)

    实现 LangChain 标准 Embeddings 接口:
    - embed_documents(texts: List[str]) → List[List[float]]: 批量嵌入文档
    - embed_query(text: str) → List[float]: 嵌入单个查询
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-v4",
        dimensions: int = 1024,
    ):
        """
        初始化 DashScope Embeddings

        Args:
            api_key: DashScope API Key
            model: 嵌入模型名称
            dimensions: 向量维度
        """
        if not api_key or api_key == "your-api-key-here":
            raise ValueError("请设置环境变量 DASHSCOPE_API_KEY")

        self.client = OpenAI(api_key=api_key, base_url=config.dashscope_api_base)
        self.model = model
        self.dimensions = dimensions

        # 打印初始化信息
        masked_key = self._mask_api_key(api_key)
        logger.info(
            f"DashScope Embeddings 初始化完成 - "
            f"模型: {model}, 维度: {dimensions}, API Key: {masked_key}"
        )

    @staticmethod
    def _mask_api_key(api_key: str) -> str:
        """掩码 API Key 用于日志，仅显示前4后4字符"""
        if len(api_key) > 12:
            return f"{api_key[:4]}...{api_key[-4:]}"
        if len(api_key) > 4:
            return f"{api_key[:2]}...{api_key[-2:]}"
        return "***"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        批量嵌入文档列表 (LangChain 标准接口)

        Args:
            texts: 文本列表

        Returns:
            List[List[float]]: 嵌入向量列表
        """
        if not texts:
            return []

        try:
            logger.info(f"批量嵌入 {len(texts)} 个文档")

            # 批量调用 API
            response = self.client.embeddings.create(
                model=self.model, input=texts, dimensions=self.dimensions, encoding_format="float"
            )

            embeddings = [item.embedding for item in response.data]
            logger.debug(f"批量嵌入完成, 维度: {len(embeddings[0])}")

            return embeddings

        except Exception as e:
            logger.error(f"批量嵌入失败: {e}")
            raise RuntimeError(f"批量嵌入失败: {e}") from e

    def embed_query(self, text: str) -> list[float]:
        """
        嵌入单个查询文本 (LangChain 标准接口)

        Args:
            text: 查询文本

        Returns:
            List[float]: 嵌入向量
        """
        if not text or not text.strip():
            raise ValueError("查询文本不能为空")

        try:
            logger.debug(f"嵌入查询, 长度: {len(text)} 字符")

            response = self.client.embeddings.create(
                model=self.model, input=text, dimensions=self.dimensions, encoding_format="float"
            )

            embedding = response.data[0].embedding
            logger.debug(f"查询嵌入完成, 维度: {len(embedding)}")

            return embedding

        except Exception as e:
            logger.error(f"查询嵌入失败: {e}")
            raise RuntimeError(f"查询嵌入失败: {e}") from e


class DeterministicFakeEmbeddings(Embeddings):
    """确定性测试 Embedding，避免单元测试依赖外部模型服务。"""

    def __init__(self, dimensions: int = 64) -> None:
        """初始化固定维度向量"""
        self.dimensions = dimensions

    def _embed(self, text: str) -> list[float]:
        """使用哈希生成稳定向量"""
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        while len(values) < self.dimensions:
            for byte in digest:
                values.append((byte / 255.0) * 2 - 1)
                if len(values) >= self.dimensions:
                    break
            digest = hashlib.sha256(digest).digest()
        return values

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量嵌入文档"""
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        """嵌入查询文本"""
        if not text or not text.strip():
            raise ValueError("查询文本不能为空")
        return self._embed(text)


_vector_embedding_service: DashScopeEmbeddings | None = None


def get_vector_embedding_service() -> Embeddings:
    """按需创建向量嵌入服务，避免应用启动时因密钥占位符直接失败。"""
    global _vector_embedding_service
    if config.dashscope_api_key.lower() in {"", "your-api-key-here", "fake", "test"}:
        logger.warning("DASHSCOPE_API_KEY 未配置，使用确定性测试 Embedding")
        return DeterministicFakeEmbeddings()
    if _vector_embedding_service is None:
        _vector_embedding_service = DashScopeEmbeddings(
            api_key=config.dashscope_api_key,
            model=config.dashscope_embedding_model,
            dimensions=1024,
        )
    return _vector_embedding_service
