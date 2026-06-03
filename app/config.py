"""配置管理模块

使用 Pydantic Settings 管理 AIOps Agent、Kubernetes、Chroma 和飞书配置。
"""

from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用配置
    app_name: str = "KubernetesAIOpsAgent"
    app_version: str = "2.0.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 9900
    project_root: str = str(Path(__file__).resolve().parent.parent)
    static_dir: str = "static"
    upload_dir: str = "uploads"
    log_dir: str = "logs"
    data_dir: str = "data"
    log_enqueue: bool | None = None

    # DashScope 配置
    dashscope_api_key: str = ""  # 默认空字符串，实际使用需从环境变量加载
    dashscope_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen-max"
    dashscope_embedding_model: str = "text-embedding-v4"  # v4 支持多种维度（默认 1024）

    # RAG 配置
    rag_top_k: int = 3
    rag_model: str = "qwen-max"  # 使用快速响应模型，不带扩展思考
    chroma_persist_dir: str = "data/chroma"
    chroma_collection_name: str = "kubernetes_runbooks"

    # 文档分块配置
    chunk_max_size: int = 800
    chunk_overlap: int = 100

    # Kubernetes Provider 配置
    k8s_provider_mode: str = "auto"  # auto | real | demo
    k8s_context: str | None = None
    k8s_namespace: str = "default"
    kubeconfig: str | None = None

    # MCP 服务配置
    mcp_kubernetes_transport: str = "streamable-http"
    mcp_kubernetes_url: str = "http://localhost:8010/mcp"

    # CORS 配置
    cors_allowed_origins: str = "*"  # 生产环境应设置为具体域名，如 "https://aiops.example.com"

    # 飞书配置
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_verification_token: str = ""
    feishu_encrypt_key: str = ""
    feishu_webhook_url: str = ""
    feishu_webhook_secret: str = ""

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value: object) -> object:
        """兼容 Linux/容器环境中常见的 DEBUG=release/prod 写法。"""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production"}:
                return False
            if normalized in {"dev", "develop", "development"}:
                return True
        return value

    def resolve_path(self, value: str) -> Path:
        """解析运行目录，容器和 Linux 服务可通过环境变量覆盖。"""
        path = Path(value)
        if path.is_absolute():
            return path
        return Path(self.project_root).resolve() / path

    @property
    def static_path(self) -> Path:
        """静态资源目录绝对路径"""
        return self.resolve_path(self.static_dir)

    @property
    def upload_path(self) -> Path:
        """上传文件目录绝对路径"""
        return self.resolve_path(self.upload_dir)

    @property
    def log_path(self) -> Path:
        """日志目录绝对路径"""
        return self.resolve_path(self.log_dir)

    @property
    def data_path(self) -> Path:
        """运行数据目录绝对路径"""
        return self.resolve_path(self.data_dir)

    @property
    def chroma_path(self) -> Path:
        """Chroma 持久化目录绝对路径"""
        return self.resolve_path(self.chroma_persist_dir)

    @property
    def mcp_servers(self) -> dict[str, dict[str, Any]]:
        """获取完整的 MCP 服务器配置"""
        return {
            "kubernetes": {
                "transport": self.mcp_kubernetes_transport,
                "url": self.mcp_kubernetes_url,
            },
        }


# 全局配置实例
config = Settings()
