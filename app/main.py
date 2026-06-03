"""FastAPI 应用入口"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.api import aiops, chat, feishu, file, health
from app.config import config


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info("=" * 60)
    logger.info(f"🚀 {config.app_name} v{config.app_version} 启动中...")
    logger.info(f"📝 环境: {'开发' if config.debug else '生产'}")
    logger.info(f"🌐 监听地址: http://{config.host}:{config.port}")
    logger.info(f"📚 API 文档: http://{config.host}:{config.port}/docs")
    logger.info(f"📦 Chroma 目录: {config.chroma_path}")
    logger.info(f"☸️ Kubernetes Provider 模式: {config.k8s_provider_mode}")
    logger.info("=" * 60)

    yield

    logger.info(f"👋 {config.app_name} 关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title=config.app_name,
    version=config.app_version,
    description="基于 LangChain、MCP、Chroma、Kubernetes 和飞书的告警驱动 AIOps Agent",
    lifespan=lifespan,
)

# 配置 CORS
# 生产环境通过 CORS_ALLOWED_ORIGINS 环境变量限制具体域名，
# 例如 CORS_ALLOWED_ORIGINS="https://aiops.example.com,https://aiops-admin.example.com"
_cors_origins = [
    origin.strip()
    for origin in config.cors_allowed_origins.split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins if _cors_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(health.router, tags=["健康检查"])
app.include_router(chat.router, prefix="/api", tags=["对话"])
app.include_router(file.router, prefix="/api", tags=["文件管理"])
app.include_router(aiops.router, prefix="/api", tags=["AIOps智能运维"])
app.include_router(feishu.router, prefix="/api", tags=["飞书集成"])

# 挂载静态文件
static_dir = config.static_path
if static_dir.exists():
    # 使用绝对路径挂载，避免 Linux 服务从非项目根目录启动时找不到静态资源。
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
else:
    logger.warning(f"静态资源目录不存在，跳过挂载: {static_dir}")


@app.get("/")
async def root():
    """返回首页"""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {
        "message": f"Welcome to {config.app_name} API",
        "version": config.app_version,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app", host=config.host, port=config.port, reload=config.debug, log_level="info"
    )
