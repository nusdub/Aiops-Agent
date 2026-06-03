"""RAG Agent 服务 - 基于 LangGraph 的智能代理

使用 langchain_qwq 的 ChatQwen 原生集成，
支持真正的流式输出和更好的模型适配。
"""

import asyncio
from collections.abc import AsyncGenerator, Sequence
from typing import Annotated, Any, cast

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_qwq import ChatQwen
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from loguru import logger
from pydantic import SecretStr
from typing_extensions import TypedDict

from app.agent.mcp_client import get_mcp_client_with_retry
from app.config import config
from app.tools import get_current_time, retrieve_knowledge

# 阿里千问大模型和langchain集成参考： https://docs.langchain.com/oss/python/integrations/chat/qwen
# 注意：需要配置环境变量 DASHSCOPE_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1 否则默认访问的是新加坡站点
# 同时也需要配置环境变量 DASHSCOPE_API_KEY=your_api_key


class AgentState(TypedDict):
    """Agent 状态"""

    messages: Annotated[Sequence[BaseMessage], add_messages]


def build_trimmed_messages(state: AgentState) -> dict[str, Any] | None:
    """
    修剪消息历史，只保留最近的几条消息以适应上下文窗口。

    策略：
    - 保留第一条系统消息（SystemMessage）
    - 保留最近的 6 条消息（3 轮对话）
    - 当消息少于等于 7 条时，不做修剪

    使用 RemoveMessage 逐条标记需要删除的旧消息，
    避免依赖不存在的 REMOVE_ALL_MESSAGES 常量。

    Args:
        state: Agent 状态

    Returns:
        包含修剪后消息的字典，如果无需修剪则返回 None
    """
    messages = state["messages"]

    # 如果消息数量较少，无需修剪
    if len(messages) <= 7:
        return None

    # 提取第一条系统消息
    first_msg = messages[0]

    # 保留最近的 6 条消息（3 轮对话）
    recent_messages = messages[-6:]

    # 被修剪掉的中间消息，逐条标记删除
    removed = [
        RemoveMessage(id=getattr(msg, "id", str(i)))
        for i, msg in enumerate(messages[1:-6])
        if not isinstance(msg, SystemMessage)
    ]

    # 构建新消息列表：系统消息 + 最近消息
    new_messages = [first_msg] + list(recent_messages)

    logger.debug(f"修剪消息历史: {len(messages)} -> {len(new_messages)} 条")

    return {"messages": removed + new_messages}


class RagAgentService:
    """RAG Agent 服务 - 使用 LangGraph + ChatQwen 原生集成"""

    def __init__(self, streaming: bool = True):
        """初始化 RAG Agent 服务

        Args:
            streaming: 是否启用流式输出，默认为 True
        """
        self.model_name = config.rag_model
        self.streaming = streaming
        self.system_prompt = self._build_system_prompt()

        self.model = ChatQwen(
            model=self.model_name,
            api_key=SecretStr(config.dashscope_api_key) if config.dashscope_api_key else None,
            temperature=0.7,
            streaming=streaming,
        )

        # 定义基础工具
        self.tools = [retrieve_knowledge, get_current_time]

        # MCP 客户端（延迟初始化，使用全局管理）
        self.mcp_tools: list = []

        # 创建内存检查点（用于会话管理）
        self.checkpointer = MemorySaver()

        # Agent 初始化（会在异步方法中完成）
        self.agent = None
        self._agent_initialized = False
        self._init_lock = asyncio.Lock()

        logger.info(
            f"RAG Agent 服务初始化完成 (ChatQwen), model={self.model_name}, streaming={streaming}"
        )

    async def _initialize_agent(self):
        """异步初始化 Agent（包括 MCP 工具）。

        使用 asyncio.Lock 防止并发请求触发双重初始化，
        这在生产环境中属于常见问题：多个请求同时到达时，
        _agent_initialized 检查与赋值之间存在竞态窗口。
        """
        if self._agent_initialized:
            return

        async with self._init_lock:
            # Double-check：获取锁后再次检查，避免锁内重复初始化
            if self._agent_initialized:
                return

            # 使用全局 MCP 客户端管理器（带重试拦截器）
            mcp_client = await get_mcp_client_with_retry()

            # 获取 MCP 工具
            mcp_tools = await mcp_client.get_tools()
            logger.info(f"成功加载 {len(mcp_tools)} 个 MCP 工具")

            # 将 MCP 工具添加到实例变量中
            self.mcp_tools = mcp_tools

            # 合并所有工具
            all_tools = self.tools + self.mcp_tools

            self.agent = create_react_agent(
                self.model,
                tools=all_tools,
                checkpointer=self.checkpointer,
                prompt=self.system_prompt,
                messages_modifier=build_trimmed_messages,
            )

            self._agent_initialized = True

            if all_tools:
                tool_names = [tool.name if hasattr(tool, "name") else str(tool) for tool in all_tools]
                logger.info(f"可用工具列表: {', '.join(tool_names)}")

    def _build_system_prompt(self) -> str:
        """
        构建系统提示词

        注意：LangChain 框架会自动将工具信息传递给 LLM，
        因此系统提示词中无需列举具体的工具列表。

        Returns:
            str: 系统提示词
        """
        from textwrap import dedent

        return dedent("""
            你是一个专业的AI助手，能够使用多种工具来帮助用户解决问题。

            工作原则:
            1. 理解用户需求，选择合适的工具来完成任务
            2. 当需要获取实时信息或专业知识时，主动使用相关工具
            3. 基于工具返回的结果提供准确、专业的回答
            4. 如果工具无法提供足够信息，请诚实地告知用户

            回答要求:
            - 保持友好、专业的语气
            - 回答简洁明了，重点突出
            - 基于事实，不编造信息
            - 如有不确定的地方，明确说明

            请根据用户的问题，灵活使用可用工具，提供高质量的帮助。
        """).strip()

    async def query(
        self,
        question: str,
        session_id: str,
    ) -> str:
        """
        非流式处理用户问题（一次性返回完整答案）

        Args:
            question: 用户问题
            session_id: 会话ID（作为 thread_id）

        Returns:
            str: 完整答案
        """
        try:
            await self._initialize_agent()

            logger.info(f"[会话 {session_id}] RAG Agent 收到查询（非流式）: {question}")

            # 构建 Agent 输入（system prompt 已通过 create_react_agent 的 prompt 参数注入）
            agent_input = {"messages": [HumanMessage(content=question)]}

            # 配置 thread_id（用于会话持久化）
            config_dict = {"configurable": {"thread_id": session_id}}

            if self.agent is None:
                raise RuntimeError("RAG Agent 初始化失败")

            result = await self.agent.ainvoke(
                input=agent_input,
                config=config_dict,
            )

            # 提取最终答案
            messages_result = result.get("messages", [])
            if messages_result:
                last_message = messages_result[-1]
                answer = (
                    last_message.content if hasattr(last_message, "content") else str(last_message)
                )

                # 记录工具调用
                if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                    tool_names = [
                        tc.get("name", "unknown")
                        if isinstance(tc, dict)
                        else getattr(tc, "name", "unknown")
                        for tc in last_message.tool_calls
                    ]
                    logger.info(f"[会话 {session_id}] Agent 调用了工具: {tool_names}")

                logger.info(f"[会话 {session_id}] RAG Agent 查询完成（非流式）")
                return answer

            logger.warning(f"[会话 {session_id}] Agent 返回结果为空")
            return ""

        except Exception as e:
            logger.error(f"[会话 {session_id}] RAG Agent 查询失败（非流式）: {e}")
            raise

    async def query_stream(
        self,
        question: str,
        session_id: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        流式处理用户问题（逐步返回答案片段）

        Args:
            question: 用户问题
            session_id: 会话ID（作为 thread_id）

        Yields:
            Dict[str, Any]: 包含流式数据的字典
                - type: "content" | "tool_call" | "complete" | "error"
                - data: 具体内容
        """
        try:
            await self._initialize_agent()

            logger.info(f"[会话 {session_id}] RAG Agent 收到查询（流式）: {question}")

            # 构建 Agent 输入（system prompt 已通过 create_react_agent 的 prompt 参数注入）
            agent_input = {"messages": [HumanMessage(content=question)]}

            # 配置 thread_id（用于会话持久化）
            config_dict = {"configurable": {"thread_id": session_id}}

            if self.agent is None:
                raise RuntimeError("RAG Agent 初始化失败")

            async for token, metadata in self.agent.astream(
                input=agent_input,
                config=config_dict,
                stream_mode="messages",
            ):
                node_name = (
                    metadata.get("langgraph_node", "unknown")
                    if isinstance(metadata, dict)
                    else "unknown"
                )
                message_type = type(token).__name__

                if message_type in ("AIMessage", "AIMessageChunk"):
                    content_blocks = getattr(token, "content_blocks", None)

                    if content_blocks and isinstance(content_blocks, list):
                        for block in content_blocks:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text_content = block.get("text", "")
                                if text_content:
                                    yield {
                                        "type": "content",
                                        "data": text_content,
                                        "node": node_name,
                                    }
                    else:
                        # Fallback：部分模型/provider 不使用 content_blocks，
                        # 直接读取 token.content（字符串或字符串列表）
                        text = getattr(token, "content", "")
                        if isinstance(text, str) and text:
                            yield {
                                "type": "content",
                                "data": text,
                                "node": node_name,
                            }
                        elif isinstance(text, list):
                            for item in text:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    chunk = item.get("text", "")
                                    if chunk:
                                        yield {
                                            "type": "content",
                                            "data": chunk,
                                            "node": node_name,
                                        }

            logger.info(f"[会话 {session_id}] RAG Agent 查询完成（流式）")
            yield {"type": "complete"}

        except Exception as e:
            logger.error(f"[会话 {session_id}] RAG Agent 查询失败（流式）: {e}")
            yield {"type": "error", "data": str(e)}
            raise

    def get_session_history(self, session_id: str) -> list:
        """
        获取会话历史（从 MemorySaver checkpointer 中读取）

        Args:
            session_id: 会话ID（即 thread_id）

        Returns:
            list: 消息历史列表 [{"role": "user|assistant", "content": "...", "timestamp": "..."}]
        """
        try:
            from datetime import datetime

            config = {"configurable": {"thread_id": session_id}}
            checkpoint_tuple = self.checkpointer.get(config)  # type: ignore[arg-type]

            if not checkpoint_tuple:
                logger.info(f"获取会话历史: {session_id}, 消息数量: 0")
                return []

            # MemorySaver.get() 返回 CheckpointTuple，通过 .checkpoint 属性访问
            checkpoint_data = checkpoint_tuple.checkpoint  # type: ignore[attr-defined]

            # 从检查点中提取消息
            messages = checkpoint_data.get("channel_values", {}).get("messages", [])

            # 转换为前端需要的格式
            history = []
            for msg in messages:
                # 跳过系统消息
                if isinstance(msg, SystemMessage):
                    continue

                role = "user" if isinstance(msg, HumanMessage) else "assistant"
                content = msg.content if hasattr(msg, "content") else str(msg)

                timestamp = getattr(msg, "timestamp", None) or datetime.now().isoformat()
                history.append({"role": role, "content": content, "timestamp": timestamp})

            logger.info(f"获取会话历史: {session_id}, 消息数量: {len(history)}")
            return history

        except Exception as e:
            logger.error(f"获取会话历史失败: {session_id}, 错误: {e}")
            return []

    def clear_session(self, session_id: str) -> bool:
        """
        清空会话历史（写入空消息 checkpoint 覆盖旧状态）。

        MemorySaver 没有官方的 delete API，通过写入一个仅含空 messages 的
        checkpoint 来模拟"清空"。使用运行时生成的 UUID 和时间戳而非硬编码值，
        避免在 LangGraph 未来版本中因 checkpoint 格式校验而失效。

        Args:
            session_id: 会话ID（即 thread_id）

        Returns:
            bool: 是否成功
        """
        try:
            from datetime import UTC, datetime
            from uuid import uuid4

            config = cast(RunnableConfig, {"configurable": {"thread_id": session_id}})
            self.checkpointer.put(
                config,
                checkpoint={
                    "v": 1,
                    "id": str(uuid4()),
                    "ts": datetime.now(UTC).isoformat(),
                    "channel_values": {"messages": []},
                    "channel_versions": {},
                    "versions_seen": {},
                    "updated_channels": [],
                },
                metadata={},
                new_versions={},
            )
            logger.info(f"已清除会话历史: {session_id}")
            return True

        except Exception as e:
            logger.error(f"清空会话历史失败: {session_id}, 错误: {e}")
            return False

    async def cleanup(self):
        """清理资源"""
        try:
            logger.info("清理 RAG Agent 服务资源...")
            # MCP 客户端由全局管理器统一管理，无需手动清理
            logger.info("RAG Agent 服务资源已清理")
        except Exception as e:
            logger.error(f"清理资源失败: {e}")


# 全局单例 - 启用流式输出
rag_agent_service = RagAgentService(streaming=True)
