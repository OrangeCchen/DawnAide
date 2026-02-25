"""TeamLead Agent - 团队负责人

核心协作流程：
1. 分析任务 → 动态生成专家（流式）
2. Round 1（并行）：各专家独立完成初步分析
3. Round 2（并行协作）：每位专家看到所有人的 Round 1 结果，进行互评、补充、挑战
4. 领域核查（并行）：每位专家的结果由对应领域的核查专家验证，确保准确性
5. 最终汇总：综合核查后的结果生成报告
"""

from __future__ import annotations

import asyncio
import json
import re
import time

from loguru import logger
from uuid import uuid4

from src.agents.base import AgentBase
from src.core.message_bus import Message, MessageBus, MessageType
from src.core.task import Task, TaskResult, TaskStatus
from src.llm.base import ChatMessage, LLMAdapter
from src.tools.file_organizer import organize_directory_safe, preview_organize_plan

# 自然语言输出的 system prompt（用于草稿生成、最终汇总等非 JSON 阶段）
NATURAL_LANGUAGE_PROMPT = (
    "你是一个专业的 AI 助手。请直接用自然语言回答问题，输出清晰、有条理的内容。"
    "不要输出 JSON 格式，不要使用代码块包裹回答，直接输出文本内容。"
    "⚠️ 重要：当用户提供了专家分析内容或搜索结果数据时，你必须忠实引用其中的事实信息（日期、数据、事件等），"
    "严禁用自身知识替换或篡改这些来自实时搜索的信息。搜索结果比你的训练数据更准确。\n"
    "⛔ 写作/公文场景的铁律：文稿中若存在需要具体事实才能填写的内容"
    "（如：具体日期、人名、单位名称、地点、数字、金额、具体事项等），"
    "而用户未提供这些信息，则必须在对应位置写入占位符 `【需补充：说明原因】`，"
    "例如：`【需补充：活动具体日期】`、`【需补充：参会人员名单】`。"
    "严禁凭空编造任何事实性内容，哪怕编造的内容看起来合理也不行。"
)

TEAM_LEAD_SYSTEM_PROMPT = """你是一个任务协调者。收到用户任务后，你需要按以下优先级**依次**判断：

**第一步（最高优先级）：检查关键信息是否缺失**
- 如果任务涉及写作/公文/通知等需要事实性信息（时间、地点、人员、具体事项等）的场景，而用户未提供这些信息 → **必须**使用 info_request 请求补充，不可编造
- 例外：如果任务来自场景表单（metadata 含 scene_type），说明信息已在前置交互中采集，**不要再次发起 info_request**
- 对于场景表单任务，用户已填写的结构化字段属于**已确认事实**，后续分析/写作必须直接采用，不要质疑或改写字段含义
- 只有在信息充足或仅缺少风格偏好时，才进入第二步

**第二步：判断是否需要专家**
1. 分析核心需求，选择合适数量的专家
2. 为每个专家设计精确的身份和子任务
3. 判断哪些专家需要联网搜索最新信息
4. 判断哪些专家需要读取用户提供的网页链接内容
5. 判断是否需要发送 iMessage 消息

判断规则：
- 简单问候（如 hi、你好、hello）、纯闲聊 → 不需要专家，experts 留空数组 []，在 direct_answer 中直接回答
- 纯粹的常识/数学问题（如"中国首都是哪"、"1+1等于几"）→ 不需要专家，直接回答
- ⚠️ **逻辑推理题/脑筋急转弯/情景推理必须特别小心**：
  · 如果问题包含特定情景（如距离、交通方式选择、物品运输等），很可能是逻辑陷阱题
  · 这类题目看似是常识，实际考察的是"目标能否达成"而非"哪个方案效率更高"
  · 典型例子："小明家距洗车店1公里，走路去洗车还是开车去？" → 必须开车去（因为车需要到洗车店，人走过去没用）
  · 这类题目即使不创建专家，也必须在 direct_answer 中给出正确逻辑推理，不要掉入效率陷阱
- ⚠️ **涉及时效性信息的问题（即使看起来简单）必须分配专家并联网搜索**，例如：
  · "2026年春晚时间" → 需要专家 + needs_search: true（具体日期需要查实时信息）
  · "最新iPhone价格" → 需要专家 + needs_search: true
  · "今天天气" → 需要专家 + needs_search: true
  · 任何包含具体年份、"最新""最近""今年""现在"等时效关键词的问题 → 需要联网搜索
- 需要一定专业知识的单一任务（如写一篇文章、查询某个产品信息）→ 至少 1-2 个专家
- 需要多角度分析的问题（如利弊分析、对比评测、方案选择）→ 2-3 个专家
- 多维度复杂话题（如行业趋势分析、战略规划）→ 3 个专家
- 涉及多领域的综合任务 → 最多 4 个专家
- ⚠️ 注意：如果任务缺少关键的事实性信息（特别是写作/公文类），**不要分配专家**，先用 info_request 请求补充

专家设计原则：
- 每个专家的角色要有差异化视角，避免职能重叠
- 鼓励设计互补型专家组合，例如：研究者+写作者、乐观派+审慎派、理论家+实践者
- 写作类任务建议搭配"内容创作者"+"质量审核者"或"素材研究者"+"文案专家"
- 分析类任务建议从不同立场或维度各派一位专家
- 不要创建"代码审查""架构分析"等角色，除非用户明确要求分析代码
- 若某专家需要以上游专家结论作为输入，请在该专家对象中设置 `depends_on`（数组，填前置专家 name）

联网搜索判断：
- 涉及时事新闻、最新数据、实时行情、近期事件 → needs_search: true，并提供 search_query
- 涉及特定公司/产品/技术的最新动态 → needs_search: true
- 纯粹的观点分析、创意写作、理论讨论 → needs_search: false
- search_query 应该是简洁的搜索关键词（中文或英文皆可），便于获取精准结果

网页读取判断：
- 如果用户消息中包含 URL 链接（http/https 开头），需要读取该网页内容来完成分析 → needs_url_read: true，并在 read_urls 中列出需要读取的 URL
- 典型场景：用户贴了微信公众号文章链接、新闻链接、博客链接等，要求分析或总结
- 一个专家可以同时需要联网搜索和网页读取
- 如果用户只是提到某个网站但没有给出具体 URL → 不需要网页读取，可以用联网搜索

iMessage 发送判断：
- 用户明确要求发送 iMessage / 短信 / 消息给某人 → needs_imessage: true
- 必须提供收件人信息 imessage_to（手机号如 +8613800138000，或 Apple ID 邮箱）
- 必须提供消息内容 imessage_content（用户要求发送的文字）
- 如果用户只提供了姓名但没给手机号/邮箱，在 imessage_to 中填空字符串，系统会提示用户补充
- 发送消息的任务只需 1 个专家（消息助手），不需要多专家协作
- 可以同时需要搜索/网页读取（比如"搜索今天天气然后发给xxx"）

信息补充机制（⚠️ 优先级最高，在分配专家或直接回答之前必须先检查）：
- 当用户的描述缺少完成任务所需的关键**事实性信息**时，**禁止猜测或编造**，必须通过 info_request 向用户确认
- **事实性信息** vs **风格性偏好** 的区分：
  · **事实性信息**（必须由用户提供，不可编造）：时间、地点、人名、组织名、具体数据、联系方式等
  · **风格性偏好**（可以给默认值）：语气、篇幅、格式、写作风格等
- 典型必须触发 info_request 的场景：
  · 「写会议通知」但未提供会议时间、地点、参会人 → **必须** info_request
  · 「写一封邀请函」但未提供受邀人、活动信息 → **必须** info_request
  · 「帮我发消息给XX」但没有联系方式 → **必须** info_request
  · 「分析某公司」但未说明哪家公司 → **必须** info_request
- 不需要 info_request 的场景：
  · 用户说「写一篇关于AI的文章」→ 主题已明确，风格可默认，不需要额外信息
  · 用户说「帮我总结这篇文章」并附了链接 → 信息完整
- ⚠️ **关键规则**：当检测到需要 info_request 时，**direct_answer 必须留空**，**experts 必须留空**，只设置 info_request 和 thinking
- info_request.fields 支持三种类型：
  - select：单选，提供 options 选项列表
  - multiselect：多选，提供 options 选项列表
  - text：文本输入，提供 placeholder 提示

请严格按以下JSON格式输出（不要输出其他内容）：
```json
{
  "thinking": "1-2句话说明你的判断：这个任务是否需要专家？为什么？",
  "direct_answer": "如果不需要专家，在这里直接写回答内容；如果需要专家或需要补充信息，留空字符串",
  "info_request": null,
  "experts": [
    {
      "name": "专家的简短中文名（如：教育政策分析师）",
      "persona": "一段话描述这个专家的身份、专长和分析视角",
      "task": "分配给这个专家的具体子任务描述",
      "needs_search": false,
      "search_query": "",
      "needs_url_read": false,
      "read_urls": [],
      "needs_imessage": false,
      "imessage_to": "",
      "imessage_content": "",
      "depends_on": []
    }
  ]
}
```

示例1 - 不需要专家（纯闲聊/常识问题）：
```json
{"thinking": "这是一个简单的问候，不需要专家协作。", "direct_answer": "你好！我是 Agent Teams 智能协作平台。你可以给我描述一个任务，我会组建专家团队来帮你分析。", "experts": []}
```

示例1b - 需要联网搜索的时效性问题（即使看似简单也必须搜索）：
用户问："2026年春晚什么时候？"
分析：涉及具体年份的事件时间，属于时效性信息，必须联网搜索确认，不能凭训练数据猜测。
```json
{"thinking": "这是一个涉及具体年份的时效性问题，2026年春晚的具体日期需要通过联网搜索获取准确信息，不能仅凭推测。", "direct_answer": "", "experts": [{"name": "资讯查询助手", "persona": "擅长快速检索和核实时效性信息", "task": "搜索2026年央视春节联欢晚会的具体播出时间，提供准确信息", "needs_search": true, "search_query": "2026年央视春晚 播出时间", "needs_url_read": false, "read_urls": [], "needs_imessage": false, "imessage_to": "", "imessage_content": ""}]}
```

示例2 - 写作类任务（2个互补专家）：
```json
{"thinking": "撰写宣传稿需要素材研究和专业文案两个环节配合，安排2位专家协作。", "direct_answer": "", "experts": [{"name": "背景调研员", "persona": "擅长快速搜集和整理人物/事件背景资料", "task": "搜集相关背景素材和关键事实", "needs_search": true, "search_query": "相关搜索词", "needs_url_read": false, "read_urls": [], "needs_imessage": false, "imessage_to": "", "imessage_content": ""}, {"name": "资深文案专家", "persona": "10年政务/商务文案经验，擅长各类正式文体", "task": "基于素材撰写高质量文稿", "needs_search": false, "search_query": "", "needs_url_read": false, "read_urls": [], "needs_imessage": false, "imessage_to": "", "imessage_content": ""}]}
```

示例3 - 分析类任务（多角度）：
```json
{"thinking": "分析AI最新发展需要实时信息和多角度视角，需要2位专家。", "direct_answer": "", "experts": [{"name": "AI行业分析师", "persona": "关注产业动态和商业落地", "task": "分析AI行业最新发展趋势和商业前景", "needs_search": true, "search_query": "2025 AI行业最新发展趋势", "needs_url_read": false, "read_urls": [], "needs_imessage": false, "imessage_to": "", "imessage_content": ""}, {"name": "技术风险评论员", "persona": "关注技术局限性和潜在风险", "task": "从技术可行性和社会影响角度进行审慎评估", "needs_search": false, "search_query": "", "needs_url_read": false, "read_urls": [], "needs_imessage": false, "imessage_to": "", "imessage_content": ""}]}
```

示例4 - 需要读取网页内容：
```json
{"thinking": "用户提供了一篇文章链接，需要读取并分析。", "direct_answer": "", "experts": [{"name": "内容分析师", "persona": "资深内容分析师，擅长提炼文章要点", "task": "阅读并分析这篇文章的核心观点", "needs_search": false, "search_query": "", "needs_url_read": true, "read_urls": ["https://mp.weixin.qq.com/s/xxxxx"], "needs_imessage": false, "imessage_to": "", "imessage_content": ""}]}
```

示例5 - 需要补充信息（写作缺少事实性信息）：
用户说："写一篇单位内部会议通知，语言正式简洁，把时间、地点、参会人、内容、要求写清楚，符合机关发文习惯。"
分析：用户明确要求写"时间、地点、参会人、内容"，这些都是事实性信息，不可编造，必须向用户确认。
```json
{"thinking": "用户要写一篇会议通知，要求包含时间、地点、参会人、内容等具体信息，这些都是事实性信息，不能凭空编造，需要先确认。", "direct_answer": "", "info_request": {"message": "为了撰写准确的会议通知，请补充以下关键信息：", "fields": [{"id": "meeting_time", "label": "会议时间", "type": "text", "placeholder": "如：2025年3月15日（周六）上午9:00", "required": true}, {"id": "meeting_place", "label": "会议地点", "type": "text", "placeholder": "如：三楼会议室、行政楼201室", "required": true}, {"id": "attendees", "label": "参会人员", "type": "text", "placeholder": "如：各部门负责人及以上干部", "required": true}, {"id": "meeting_topic", "label": "会议主题/内容", "type": "text", "placeholder": "如：2025年度工作计划部署会", "required": true}, {"id": "organizer", "label": "发文单位", "type": "text", "placeholder": "如：办公室、党委办公室", "required": false}, {"id": "extra", "label": "其他要求", "type": "text", "placeholder": "如：请携带笔记本电脑、需提前提交发言材料等", "required": false}]}, "experts": []}
```

示例6 - 发送 iMessage：
```json
{"thinking": "用户要求发送 iMessage，需要一位消息助手执行发送任务。", "direct_answer": "", "experts": [{"name": "消息助手", "persona": "高效的通讯助手，负责准确传达消息", "task": "发送 iMessage 消息并确认发送结果", "needs_search": false, "search_query": "", "needs_url_read": false, "read_urls": [], "needs_imessage": true, "imessage_to": "+8613800138000", "imessage_content": "明天下午3点开会，请准时参加"}]}
```"""


class TeamLeadAgent(AgentBase):
    """团队负责人 Agent - 动态生成专家，两轮协作"""

    # 核查模型自动切换映射：主模型 → 核查模型
    _REVIEWER_MODEL_MAP = {
        "qwen-plus": "qwen-max",
        "qwen-max": "qwen-plus",
        "qwen-turbo": "qwen-plus",
        "qwen-long": "qwen-max",
        "qwen3-235b-a22b": "qwen-plus",
        "qwen3-32b": "qwen-max",
        "qwen3-14b": "qwen-max",
        "qwen3-8b": "qwen-plus",
        "qwen2.5-72b-instruct": "qwen-max",
        "qwen2.5-32b-instruct": "qwen-max",
        "gpt-4o": "gpt-4o-mini",
        "gpt-4o-mini": "gpt-4o",
    }

    def __init__(
        self,
        name: str = "team-lead",
        llm: LLMAdapter | None = None,
        message_bus: MessageBus | None = None,
        **kwargs,
    ):
        super().__init__(
            name=name,
            role="team-lead",
            role_label="Lead",
            system_prompt=TEAM_LEAD_SYSTEM_PROMPT,
            llm=llm,
            message_bus=message_bus,
            **kwargs,
        )
        # 独立的规划对话历史（只保留 plan 阶段的 JSON 交互，避免草稿/汇总污染）
        self._plan_conversation: list[ChatMessage] = []
        # 创建核查专用 LLM（使用不同模型实现交叉验证）
        self.reviewer_llm = self._create_reviewer_llm()

    def _create_reviewer_llm(self) -> LLMAdapter:
        """创建核查专用 LLM 适配器（自动选择与主模型不同的模型）"""
        from src.config import get_settings

        settings = get_settings()
        main_model = self.llm.model if hasattr(self.llm, "model") else ""

        # 优先使用配置的核查模型
        reviewer_model = settings.llm.reviewer_model
        if not reviewer_model or reviewer_model == main_model:
            # 自动选择不同模型
            reviewer_model = self._REVIEWER_MODEL_MAP.get(main_model, "qwen-max")

        # 如果自动选择的结果仍然和主模型相同（不太可能），用 qwen-max 兜底
        if reviewer_model == main_model:
            reviewer_model = "qwen-max" if main_model != "qwen-max" else "qwen-plus"

        logger.info(
            f"核查模型已配置: 主模型={main_model}, 核查模型={reviewer_model}"
        )

        # 基于当前 provider 创建新的适配器实例
        if settings.llm.provider == "openai":
            from src.llm.openai_adapter import OpenAIAdapter
            return OpenAIAdapter(
                api_key=settings.llm.openai_api_key,
                base_url=settings.llm.openai_base_url,
                model=reviewer_model,
            )
        elif settings.llm.provider == "ollama":
            from src.llm.ollama_adapter import OllamaAdapter
            return OllamaAdapter(
                base_url=settings.llm.ollama_base_url,
                model=reviewer_model,
            )
        else:
            # 其他 provider 回退使用主模型
            logger.warning(f"核查模型不支持 provider={settings.llm.provider}，回退使用主模型")
            return self.llm

    async def receive_task(self, task: Task) -> TaskResult:
        """重写：TeamLead 的结果已通过流式输出发送，不需要再自动发送"""
        self.status = "working"
        logger.info(f"[{self.name}] 收到任务: {task.title}")

        try:
            result = await self.execute_task(task)
            self.status = "idle"
            return result
        except Exception as e:
            logger.error(f"[{self.name}] 任务执行失败: {e}")
            self.status = "idle"

            # 关闭所有可能残留的流式状态
            bus = self.bus
            history = bus.get_history(task.team_id)
            for msg in history:
                if msg.metadata.get("streaming"):
                    await bus.update_message_content(
                        task.team_id, msg.id, msg.content or "已中断",
                        metadata_updates={"streaming": False},
                    )
                    await bus.publish(Message(
                        type=MessageType.STREAM_CHUNK,
                        sender=self.name, team_id=task.team_id, content="",
                        metadata={"target_id": msg.id, "stream_done": True},
                    ))

            # 发送错误消息（带 error 标记，前端区分样式）
            await self.send_message(
                content=f"任务执行失败: {str(e)}",
                team_id=task.team_id,
                msg_type=MessageType.TASK_RESULT,
                metadata={"status_label": "FAILED", "error": True},
            )

            # 发送完成状态消息（让工作指示器消失）
            await self.send_message(
                content="任务执行失败",
                team_id=task.team_id,
                msg_type=MessageType.STATUS_UPDATE,
                metadata={"status": "completed", "error": True},
            )

            return TaskResult(
                task_id=task.id,
                agent_name=self.name,
                status=TaskStatus.FAILED,
                content=f"任务执行失败: {str(e)}",
            )

    async def execute_task(self, task: Task) -> TaskResult:
        """分析 -> Round 1 独立分析 -> Round 2 协作讨论 -> 汇总"""
        task_start = time.time()
        logger.info(f"[{self.name}] 开始分析任务: {task.title}")

        # 文件整理场景走桌面端本地执行快路径（安全策略：禁止删除）
        if self._is_file_organize_task(task):
            return await self._execute_file_organize_task(task, task_start)

        # 非专家模式：跳过多Agent协作，直接由LLM回答
        expert_mode = task.metadata.get("expert_mode", True)
        if not expert_mode:
            return await self._execute_direct_answer(task, task_start)

        # ========== 通用监控 TODO ==========
        gen_todo: list[dict] = [
            {"id": "analyze", "title": "分析任务", "status": "running"},
            {"id": "execute", "title": "执行分析", "status": "pending"},
            {"id": "summarize", "title": "生成报告", "status": "pending"},
        ]

        # ========== 阶段 0：任务分析 ==========
        await self.send_message(
            content="正在分析任务，确定所需专家...",
            team_id=task.team_id,
            msg_type=MessageType.STATUS_UPDATE,
            metadata={
                "status": "working",
                "monitor": self._build_monitor(
                    task_type="general",
                    todo=gen_todo,
                    note="正在理解任务并分配专家...",
                ),
            },
        )

        plan_text, plan_msg_id = await self._stream_plan(task)
        plan_data = self._parse_plan(plan_text)
        experts = plan_data.get("experts", [])
        thinking = plan_data.get("thinking", "")
        direct_answer = plan_data.get("direct_answer", "")
        info_request = plan_data.get("info_request")
        is_scene_task = bool(task.metadata.get("scene_type"))
        has_expert_dependencies = any(e.get("depends_on") for e in experts)

        gen_todo[0]["status"] = "done"

        # 场景任务已在前置卡片完成信息采集，避免重复弹补充信息卡
        if is_scene_task and info_request and isinstance(info_request, dict) and info_request.get("fields"):
            logger.info(
                f"[{self.name}] 检测到场景任务({task.metadata.get('scene_type')})，"
                "忽略重复 info_request，继续后续流程"
            )
            info_request = None

        # ========== 情况 0：需要补充信息 ==========
        if info_request and isinstance(info_request, dict) and info_request.get("fields"):
            plan_elapsed = round(time.time() - task_start, 1)
            structured = f"**判断：** {thinking}\n\n需要补充信息后才能开始。"
            await self.bus.update_message_content(
                task.team_id, plan_msg_id, structured,
                metadata_updates={"streaming": False, "elapsed": plan_elapsed},
            )
            await self.bus.publish(Message(
                type=MessageType.STREAM_CHUNK,
                sender=self.name, team_id=task.team_id,
                content=structured,
                metadata={
                    "target_id": plan_msg_id, "stream_done": True,
                    "replace_content": True, "elapsed": plan_elapsed,
                },
            ))

            # 发送信息卡片消息
            await self.send_message(
                content=info_request.get("message", "请补充以下信息："),
                team_id=task.team_id,
                msg_type=MessageType.AGENT_MESSAGE,
                metadata={
                    "info_request": info_request,
                    "original_task": task.description,
                },
            )

            total_elapsed = round(time.time() - task_start, 1)
            await self.send_message(
                content=f"等待用户补充信息 · 耗时 **{total_elapsed}s**",
                team_id=task.team_id,
                msg_type=MessageType.STATUS_UPDATE,
                metadata={"status": "completed", "waiting_info": True},
            )

            return TaskResult(
                task_id=task.id, agent_name=self.name,
                status=TaskStatus.COMPLETED, content="等待用户补充信息",
                metadata={"waiting_info": True},
            )

        # ========== 情况 A：不需要专家，直接回答 ==========
        if not experts:
            plan_elapsed = round(time.time() - task_start, 1)
            from src.stores.skill_registry import get_skill_registry
            direct_skills = get_skill_registry().resolve_active_labels(
                task_metadata=task.metadata
            )

            # --- 步骤 1：内部生成草稿（不直接输出给用户） ---
            if direct_answer:
                skills_line = f"\n\n已启用技能：{' · '.join(direct_skills)}" if direct_skills else ""
                structured = f"**判断：** {thinking}\n\n无需组建专家团队，直接回答。{skills_line}"
                await self.bus.update_message_content(
                    task.team_id, plan_msg_id, structured,
                    metadata_updates={"streaming": False, "elapsed": plan_elapsed},
                )
                await self.bus.publish(Message(
                    type=MessageType.STREAM_CHUNK,
                    sender=self.name, team_id=task.team_id,
                    content=structured,
                    metadata={
                        "target_id": plan_msg_id, "stream_done": True,
                        "replace_content": True, "elapsed": plan_elapsed,
                    },
                ))

                gen_todo[1]["status"] = "running"
                gen_todo[1]["title"] = "生成回答草稿"
                await self.send_message(
                    content="正在生成回答草稿...",
                    team_id=task.team_id,
                    msg_type=MessageType.STATUS_UPDATE,
                    metadata={
                        "status": "working",
                        "monitor": self._build_monitor(
                            task_type="general", todo=gen_todo,
                            note="直接回答，无需专家团队",
                            skills=[{"id": s, "name": s} for s in direct_skills],
                        ),
                    },
                )
                _constraints = self._build_scene_constraints(task)
                draft = await self.think(
                    f"请回答用户的问题。用户说的是: {task.description}"
                    + _constraints
                    + f"\n\n你之前的分析: {direct_answer}\n\n"
                    f"**在回答之前，请先完成以下推理步骤，并把推理过程写出来（这很重要）：**\n\n"
                    f"**步骤1 - 目标识别：** 用户的最终目标是什么？（例如「去洗车」→ 目标是让车被洗干净）\n"
                    f"**步骤2 - 前提分析：** 达成目标需要哪些不可或缺的物理前提？（例如洗车→车本身必须到达洗车店）\n"
                    f"**步骤3 - 可行性验证：** 如果按照我想给出的建议去做，在物理世界中能否真正达成目标？"
                    f"做一次完整的心理模拟，一步步想象执行后会发生什么。\n"
                    f"**步骤4 - 干扰项识别：** 问题中的数字（距离、价格、时间等）是否是干扰项？"
                    f"先确认「能不能做到」，再讨论「怎么做更好」。\n\n"
                    f"**先输出上述推理过程，然后给出最终回答。**\n"
                    f"不要提及专家或分析流程。",
                    system_prompt=NATURAL_LANGUAGE_PROMPT,
                )
            else:
                await self.bus.update_message_content(
                    task.team_id, plan_msg_id, "分析完成，正在生成回答...",
                    metadata_updates={"streaming": False, "elapsed": plan_elapsed},
                )
                await self.bus.publish(Message(
                    type=MessageType.STREAM_CHUNK,
                    sender=self.name, team_id=task.team_id, content="",
                    metadata={"target_id": plan_msg_id, "stream_done": True},
                ))

                gen_todo[1]["status"] = "running"
                gen_todo[1]["title"] = "生成回答草稿"
                await self.send_message(
                    content="正在生成回答草稿...",
                    team_id=task.team_id,
                    msg_type=MessageType.STATUS_UPDATE,
                    metadata={
                        "status": "working",
                        "monitor": self._build_monitor(
                            task_type="general", todo=gen_todo,
                            note="直接回答，无需专家团队",
                        ),
                    },
                )
                _constraints2 = self._build_scene_constraints(task)
                draft = await self.think(
                    f"请回答用户的问题:\n{task.description}"
                    + _constraints2
                    + f"\n\n**在回答之前，请先完成以下推理步骤，并把推理过程写出来（这很重要）：**\n\n"
                    f"**步骤1 - 目标识别：** 用户的最终目标是什么？（例如「去洗车」→ 目标是让车被洗干净）\n"
                    f"**步骤2 - 前提分析：** 达成目标需要哪些不可或缺的物理前提？（例如洗车→车本身必须到达洗车店）\n"
                    f"**步骤3 - 可行性验证：** 如果按照我想给出的建议去做，在物理世界中能否真正达成目标？"
                    f"做一次完整的心理模拟，一步步想象执行后会发生什么。\n"
                    f"**步骤4 - 干扰项识别：** 问题中的数字（距离、价格、时间等）是否是干扰项？"
                    f"先确认「能不能做到」，再讨论「怎么做更好」。\n\n"
                    f"**先输出上述推理过程，然后给出最终回答。**",
                    system_prompt=NATURAL_LANGUAGE_PROMPT,
                )

            gen_todo[1]["status"] = "done"
            enable_review = task.metadata.get("enable_review", False)

            if enable_review:
                gen_todo[2]["title"] = "核查验证"
                gen_todo[2]["status"] = "running"
                draft_elapsed = round(time.time() - task_start, 1)
                await self.send_message(
                    content=f"草稿已生成（{draft_elapsed}s），**核查阶段** · 正在验证回答的准确性...",
                    team_id=task.team_id,
                    msg_type=MessageType.STATUS_UPDATE,
                    metadata={
                        "status": "working",
                        "monitor": self._build_monitor(
                            task_type="general", todo=gen_todo,
                            note="核查专家正在验证回答准确性...",
                        ),
                    },
                )

                review_result = await self._run_direct_answer_review(task, draft)

                gen_todo[2]["status"] = "done"
                gen_todo.append({"id": "output", "title": "输出最终回答", "status": "running"})
                review_elapsed = round(time.time() - task_start, 1)
                await self.send_message(
                    content=f"核查完成（{review_elapsed}s），正在输出最终回答...",
                    team_id=task.team_id,
                    msg_type=MessageType.STATUS_UPDATE,
                    metadata={
                        "status": "working",
                        "monitor": self._build_monitor(
                            task_type="general", todo=gen_todo,
                            note="正在输出最终回答...",
                        ),
                    },
                )

                # 基于核查结果生成最终回答
                if review_result:
                    summary = await self.think_stream(
                        user_input=(
                            f"你是一个回答助手。请根据以下核查结果输出最终回答。\n\n"
                            f"用户问题: {task.description}\n\n"
                            f"原始草稿:\n{draft}\n\n"
                            f"核查意见:\n{review_result}\n\n"
                            f"请输出核查修正后的最终版本。"
                            f"如果核查结论是通过，直接输出原始草稿内容。"
                            f"如果有修正，输出修正后的完整内容。\n"
                            f"只输出最终回答本身，不要输出核查过程、不要说'根据核查'之类的话。"
                        ),
                        team_id=task.team_id,
                        msg_type=MessageType.TASK_RESULT,
                        system_prompt=NATURAL_LANGUAGE_PROMPT,
                    )
                else:
                    # 核查失败时回退输出原始草稿
                    summary = await self.think_stream(
                        user_input=(
                            f"请直接输出以下内容（不做任何修改）:\n\n{draft}"
                        ),
                        team_id=task.team_id,
                        msg_type=MessageType.TASK_RESULT,
                        system_prompt=NATURAL_LANGUAGE_PROMPT,
                    )
            else:
                # 审查未开启，直接输出草稿作为最终回答
                summary = await self.think_stream(
                    user_input=(
                        f"请直接输出以下内容（不做任何修改）:\n\n{draft}"
                    ),
                    team_id=task.team_id,
                    msg_type=MessageType.TASK_RESULT,
                    system_prompt=NATURAL_LANGUAGE_PROMPT,
                )

            total_elapsed = round(time.time() - task_start, 1)
            for t in gen_todo:
                t["status"] = "done"
            await self.send_message(
                content=f"回答完成 · 耗时 **{total_elapsed}s**",
                team_id=task.team_id,
                msg_type=MessageType.STATUS_UPDATE,
                metadata={
                    "status": "completed",
                    "total_elapsed": total_elapsed,
                    "monitor": self._build_monitor(
                        task_type="general", todo=gen_todo,
                        note="回答完成",
                    ),
                },
            )

            # 自动重命名对话
            await self._auto_rename_team(task)

            # iMessage 推送（如果任务来自 iMessage Bot 则跳过，Bot 会自己回复）
            if task.assigned_by != "imessage-bot":
                await self._push_imessage_summary(task.title, summary, total_elapsed)

            return TaskResult(
                task_id=task.id, agent_name=self.name,
                status=TaskStatus.COMPLETED, content=summary,
            )

        # ========== 情况 B：需要专家协作 ==========
        # 从技能注册中心解析本次激活的技能
        from src.stores.skill_registry import get_skill_registry
        skills_used = get_skill_registry().resolve_active_labels(
            task_metadata=task.metadata,
            experts=experts,
        )

        plan_elapsed = round(time.time() - task_start, 1)
        structured = self._build_thinking_content(
            thinking, experts, skills_used,
            enable_review=task.metadata.get("enable_review", False),
        )
        await self.bus.update_message_content(
            task.team_id, plan_msg_id, structured,
            metadata_updates={"streaming": False, "elapsed": plan_elapsed},
        )
        await self.bus.publish(Message(
            type=MessageType.STREAM_CHUNK,
            sender=self.name, team_id=task.team_id,
            content=structured,
            metadata={
                "target_id": plan_msg_id, "stream_done": True,
                "replace_content": True, "elapsed": plan_elapsed,
            },
        ))

        # 将动态创建的专家作为团队成员持久化
        from src.core.team import TeamMember, get_team_manager
        tm = get_team_manager()
        team = tm.get_team(task.team_id)
        if team:
            for expert in experts:
                expert_name = expert["name"]
                # 避免重复添加
                if not team.get_member(expert_name):
                    tm.add_member(
                        task.team_id,
                        TeamMember(
                            agent_name=expert_name,
                            role="expert",
                            role_label="Expert",
                        ),
                    )
            await tm.save_team_to_db(team)

        # ========== 阶段 1：Round 1 - 独立分析 ==========
        gen_todo[1]["status"] = "running"
        gen_todo[1]["title"] = f"Round 1 · {len(experts)} 位专家独立分析"
        expert_skills = [{"id": e["name"], "name": e["name"]} for e in experts]
        await self.send_message(
            content=(
                f"**Round 1** · {len(experts)} 位专家开始分析..."
                if not has_expert_dependencies
                else f"**Round 1** · {len(experts)} 位专家按依赖关系分批分析..."
            ),
            team_id=task.team_id,
            msg_type=MessageType.STATUS_UPDATE,
            metadata={
                "status": "working",
                "monitor": self._build_monitor(
                    task_type="general", todo=gen_todo,
                    note=f"{len(experts)} 位专家正在独立分析...",
                    skills=expert_skills,
                ),
            },
        )

        r1_results_raw = await self._run_round1_with_dependencies(experts, task)

        r1_completed: list[TaskResult] = []
        total_tokens = 0
        for r in r1_results_raw:
            if isinstance(r, TaskResult) and r.status == TaskStatus.COMPLETED:
                r1_completed.append(r)
                total_tokens += max(len(r.content) * 2 // 3, 1)
            elif isinstance(r, Exception):
                logger.error(f"专家 Round 1 异常: {r}")

        if not r1_completed:
            return TaskResult(
                task_id=task.id, agent_name=self.name,
                status=TaskStatus.FAILED, content="所有专家执行失败",
            )

        r1_elapsed = round(time.time() - task_start, 1)

        # 第一轮完成后立即尝试重命名，避免必须等待最终汇总结束
        await self._auto_rename_team(task)

        # ========== 阶段 2：Round 2 - 协作讨论（仅多专家时执行） ==========
        r2_completed: list[TaskResult] = []
        if len(r1_completed) > 1:
            gen_todo[1]["status"] = "done"
            gen_todo.insert(2, {"id": "discuss", "title": "Round 2 · 协作讨论", "status": "running"})
            # 更新后面的生成报告索引
            await self.send_message(
                content=f"**Round 2** · 初步分析完成（{r1_elapsed}s），专家进入协作讨论...",
                team_id=task.team_id,
                msg_type=MessageType.STATUS_UPDATE,
                metadata={
                    "status": "working",
                    "monitor": self._build_monitor(
                        task_type="general", todo=gen_todo,
                        note="专家正在协作讨论...",
                        skills=expert_skills,
                    ),
                },
            )

            r2_coros = [
                self._run_expert_discussion(expert, r1_completed, task)
                for expert in experts
            ]
            r2_results_raw = await asyncio.gather(*r2_coros, return_exceptions=True)

            for r in r2_results_raw:
                if isinstance(r, TaskResult) and r.status == TaskStatus.COMPLETED:
                    r2_completed.append(r)
                    total_tokens += max(len(r.content) * 2 // 3, 1)
                elif isinstance(r, Exception):
                    logger.error(f"专家 Round 2 异常: {r}")

            discuss_elapsed = round(time.time() - task_start, 1)
        else:
            pass  # r1_elapsed already set

        # ========== 阶段 3：领域核查（并行，仅在开启审查时执行） ==========
        enable_review = task.metadata.get("enable_review", False)
        review_completed: list[TaskResult] = []

        if enable_review:
            # 标记讨论阶段完成，添加核查阶段
            for t in gen_todo:
                if t["id"] == "discuss":
                    t["status"] = "done"
            gen_todo.insert(-1, {"id": "review", "title": "领域核查", "status": "running"})
            review_elapsed_label = (
                f"{round(time.time() - task_start, 1)}s"
            )
            await self.send_message(
                content=f"**核查阶段** · 领域核查专家开始验证 {len(r1_completed)} 份分析结果（{review_elapsed_label}）...",
                team_id=task.team_id,
                msg_type=MessageType.STATUS_UPDATE,
                metadata={
                    "status": "working",
                    "monitor": self._build_monitor(
                        task_type="general", todo=gen_todo,
                        note=f"核查专家正在验证 {len(r1_completed)} 份分析结果...",
                        skills=expert_skills,
                    ),
                },
            )

            # 为每位专家匹配其 Round 1 和 Round 2 的结果
            r1_by_name = {r.agent_name: r for r in r1_completed}
            r2_by_name = {r.agent_name: r for r in r2_completed}

            review_coros = [
                self._run_expert_review(
                    expert,
                    r1_by_name.get(expert["name"]),
                    r2_by_name.get(expert["name"]),
                    task,
                )
                for expert in experts
                if expert["name"] in r1_by_name  # 仅核查有结果的专家
            ]
            review_results_raw = await asyncio.gather(*review_coros, return_exceptions=True)

            for r in review_results_raw:
                if isinstance(r, TaskResult) and r.status == TaskStatus.COMPLETED:
                    review_completed.append(r)
                    total_tokens += max(len(r.content) * 2 // 3, 1)
                elif isinstance(r, Exception):
                    logger.error(f"领域核查异常: {r}")

            review_done_elapsed = round(time.time() - task_start, 1)
            status_text = f"领域核查完成（{review_done_elapsed}s），正在生成最终报告..."
            for t in gen_todo:
                if t["id"] == "review":
                    t["status"] = "done"
        else:
            status_text = "正在生成最终报告..."
            # 标记 round1 / discuss 完成
            for t in gen_todo:
                if t["id"] in ("execute", "discuss"):
                    t["status"] = "done"

        # ========== 阶段 4：最终汇总 ==========
        # 找到 "生成报告" todo 并标记运行中
        for t in gen_todo:
            if t["id"] == "summarize":
                t["status"] = "running"
        await self.send_message(
            content=status_text,
            team_id=task.team_id,
            msg_type=MessageType.STATUS_UPDATE,
            metadata={
                "status": "working",
                "monitor": self._build_monitor(
                    task_type="general", todo=gen_todo,
                    note="正在生成最终报告...",
                    skills=expert_skills,
                ),
            },
        )

        summary = await self._summarize_stream(
            task, r1_completed, r2_completed, review_completed
        )

        # 完成状态
        total_elapsed = round(time.time() - task_start, 1)
        total_tokens += max(len(summary) * 2 // 3, 1)
        for t in gen_todo:
            t["status"] = "done"

        await self.send_message(
            content=(
                f"任务完成 · 总耗时 **{total_elapsed}s** · "
                f"约 **{self._format_tokens(total_tokens)}** tokens"
            ),
            team_id=task.team_id,
            msg_type=MessageType.STATUS_UPDATE,
            metadata={
                "status": "completed",
                "total_elapsed": total_elapsed,
                "total_tokens": total_tokens,
                "skills_used": skills_used,
                "monitor": self._build_monitor(
                    task_type="general", todo=gen_todo,
                    note="任务完成",
                    skills=expert_skills,
                ),
            },
        )

        # 自动重命名对话
        await self._auto_rename_team(task)

        # iMessage 推送（如果任务来自 iMessage Bot 则跳过，Bot 会自己回复）
        if task.assigned_by != "imessage-bot":
            await self._push_imessage_summary(task.title, summary, total_elapsed)

        return TaskResult(
            task_id=task.id, agent_name=self.name,
            status=TaskStatus.COMPLETED, content=summary,
        )

    @staticmethod
    def _build_scene_constraints(task: Task) -> str:
        """将 scene_form_data 转为写作约束文本块，供注入各阶段 prompt。

        同时列出「已填字段（必须采用）」和「未填字段（必须占位，禁止编造）」，
        确保 LLM 不会对任何未知事实自行脑补。
        """
        form_data: dict = task.metadata.get("scene_form_data") or {}
        scene_category = task.metadata.get("scene_category", "")
        scene_type = task.metadata.get("scene_type", "")
        if not form_data:
            return ""

        # 字段标签映射
        label_map: dict[str, str] = {
            "folder_scope": "待整理目录",
            "organize_goal": "整理目标",
            "document_type": "文档类型",
            "topic": "主题/事由",
            "audience": "受众/收件方",
            "tone": "语气风格",
            "length": "篇幅要求",
            "key_points": "核心要点",
            "deadline": "时间/截止日期",
            "sender": "发件人/署名",
            "occasion": "场合",
            "background": "背景信息",
            "goal": "目标",
        }

        filled_lines: list[str] = []
        missing_lines: list[str] = []

        for fid, val in form_data.items():
            label = label_map.get(fid, fid)
            if val and str(val).strip():
                filled_lines.append(f"- {label}：{val}")
            else:
                missing_lines.append(f"- {label}（用户未填写）")

        # 没有任何已填字段时，直接返回空（避免干扰非写作场景）
        if not filled_lines and not missing_lines:
            return ""

        scene_hint = ""
        if scene_category:
            scene_hint = f"（场景：{scene_category}"
            if scene_type:
                scene_hint += f" / {scene_type}"
            scene_hint += "）"

        result = f"\n\n【⚠️ 用户已确认的结构化规格约束{scene_hint}】\n"

        if filled_lines:
            result += "\n✅ 以下字段用户已填写，必须严格采用，不可改写：\n"
            result += "\n".join(filled_lines) + "\n"

        if missing_lines:
            result += (
                "\n❌ 以下字段用户未填写，对应位置必须写入占位符，禁止编造任何具体内容：\n"
                + "\n".join(missing_lines) + "\n"
                + "\n占位符格式示例：`【需补充：活动具体日期】`、`【需补充：参会人员名单】`\n"
                "请为每个空白字段在文稿中自动添加对应的 `【需补充：...】` 标记。\n"
            )

        return result

    async def _execute_direct_answer(self, task: Task, task_start: float) -> TaskResult:
        """非专家模式：直接由LLM回答，不走多Agent协作流程"""
        logger.info(f"[{self.name}] 非专家模式，直接回答: {task.title}")

        await self.send_message(
            content="正在回答...",
            team_id=task.team_id,
            msg_type=MessageType.STATUS_UPDATE,
            metadata={"status": "working"},
        )

        await self.think_stream(
            user_input=task.description,
            team_id=task.team_id,
            msg_type=MessageType.TASK_RESULT,
            system_prompt=NATURAL_LANGUAGE_PROMPT,
        )

        # 尝试自动重命名对话（首次对话）
        try:
            await self._auto_rename_team(task)
        except Exception as e:
            logger.warning(f"直接回答后自动重命名失败: {e}")

        elapsed = round(time.time() - task_start, 1)
        await self.send_message(
            content="回答完成",
            team_id=task.team_id,
            msg_type=MessageType.STATUS_UPDATE,
            metadata={"status": "completed", "elapsed": elapsed},
        )

        return TaskResult(
            task_id=task.id,
            agent_name=self.name,
            status=TaskStatus.COMPLETED,
            content="",
        )

    def _is_file_organize_task(self, task: Task) -> bool:
        scene_category = str(task.metadata.get("scene_category", ""))
        scene_type = str(task.metadata.get("scene_type", ""))
        if scene_category == "file_organize" or scene_type.startswith("file_organize"):
            return True

        text = f"{task.title}\n{task.description}".lower()
        return "文件整理" in text or "整理文件" in text

    # ---------- 通用任务监控 ----------
    @staticmethod
    def _build_monitor(
        task_type: str,
        todo: list[dict],
        note: str = "",
        skills: list[dict] | None = None,
        artifacts: list[dict] | None = None,
        **extras: object,
    ) -> dict:
        """构建通用 monitor payload，todo/skills 会做快照防止引用突变。"""
        result: dict = {
            "task_type": task_type,
            "note": note,
            "todo": [dict(item) for item in (todo or [])],
            "skills": [dict(item) for item in (skills or [])],
            "artifacts": list(artifacts or []),
        }
        result.update(extras)
        return result

    def _build_file_monitor(
        self,
        workspace: str,
        todo: list[dict],
        note: str = "",
        skills: list[dict] | None = None,
        artifacts_extra: list[dict] | None = None,
        pending_confirm: bool = False,
        preview_plan: dict | None = None,
        organize_goal: str = "",
        goal_suggestions: list[dict] | None = None,
    ) -> dict:
        artifacts = [
            {
                "id": "workspace",
                "name": "默认工作目录",
                "path": workspace,
                "type": "folder",
                "openable": True,
            }
        ]
        if artifacts_extra:
            artifacts.extend(artifacts_extra)
        extras: dict = {"workspace": workspace}
        if pending_confirm:
            extras["pending_confirm"] = True
        if preview_plan:
            extras["preview_plan"] = preview_plan
        if organize_goal:
            extras["organize_goal"] = organize_goal
        if goal_suggestions:
            extras["goal_suggestions"] = goal_suggestions
        return self._build_monitor(
            task_type="file_organize",
            todo=todo,
            note=note,
            skills=skills,
            artifacts=artifacts,
            **extras,
        )

    def _extract_path_from_text(self, text: str) -> str:
        # 支持 ~/xxx、/xxx、./xxx、../xxx 四类路径
        match = re.search(r"((?:~|/|\.{1,2}/)[^\s，,。；;]+)", text or "")
        return match.group(1) if match else ""

    def _build_goal_suggestions(self, organize_goal: str, category_counts: dict[str, int]) -> list[dict]:
        top_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        top_text = "、".join(name for name, _ in top_categories) or "常见文件"
        suggestions = [
            {
                "id": "by_type",
                "title": "按文件类型整理（推荐）",
                "goal": "按文件类型自动分类",
                "reason": f"当前目录以 {top_text} 为主，类型分类最稳妥。",
            },
            {
                "id": "by_time",
                "title": "按时间（月）整理",
                "goal": "按修改时间按月分类",
                "reason": "适合下载目录和临时资料，便于回溯近期文件。",
            },
            {
                "id": "by_topic",
                "title": "按主题关键词整理",
                "goal": "按主题内容分类",
                "reason": "适合报告、项目资料等内容导向文件。",
            },
        ]
        # 只有当用户目标与内置选项不重复时才插入，避免同一 goal 文本出现两次
        builtin_goals = {s["goal"] for s in suggestions}
        if organize_goal and organize_goal not in builtin_goals:
            suggestions.insert(
                0,
                {
                    "id": "user_goal",
                    "title": "使用你填写的整理目标",
                    "goal": organize_goal,
                    "reason": "你已提供明确目标，可优先按该目标执行。",
                },
            )
        return suggestions[:4]

    async def _execute_file_organize_task(self, task: Task, task_start: float) -> TaskResult:
        form_data = task.metadata.get("scene_form_data", {}) or {}
        if not isinstance(form_data, dict):
            form_data = {}

        folder_scope = str(form_data.get("folder_scope", "")).strip()
        organize_goal = str(form_data.get("organize_goal", "")).strip()
        # 确认执行标志：从监控面板点击确认后触发
        confirm_execute = task.metadata.get("confirm_execute", False)
        # 文件整理统一为：先预览，用户点击确认后再执行
        force_execute = bool(confirm_execute)
        if not folder_scope:
            folder_scope = self._extract_path_from_text(task.description)

        if not folder_scope:
            msg = "未检测到待整理目录，请在场景表单中填写“待整理目录”后重试。"
            await self.send_message(
                content=msg,
                team_id=task.team_id,
                msg_type=MessageType.TASK_RESULT,
                metadata={"status_label": "FAILED", "error": True},
            )
            await self.send_message(
                content="文件整理任务失败",
                team_id=task.team_id,
                msg_type=MessageType.STATUS_UPDATE,
                metadata={"status": "completed", "error": True},
            )
            return TaskResult(
                task_id=task.id,
                agent_name=self.name,
                status=TaskStatus.FAILED,
                content=msg,
            )

        from pathlib import Path
        target_dir = str(Path(folder_scope).expanduser().resolve())
        goal_label = organize_goal or "按文件类型自动分类（系统建议）"

        todo = [
            {
                "id": "analyze",
                "title": "分析文件名称和结构，确定分类方案",
                "status": "pending",
                "detail": "等待开始",
            },
            {
                "id": "organize",
                "title": "创建子文件夹并移动文件",
                "status": "pending",
                "detail": "等待开始",
            },
            {
                "id": "verify",
                "title": "验证整理结果，确认无文件丢失",
                "status": "pending",
                "detail": "等待开始",
            },
        ]
        skills = [{"name": "本地文件整理", "status": "active"}]

        try:
            stage_begin = time.monotonic()
            todo[0]["status"] = "running"
            todo[0]["detail"] = "正在扫描目录结构与文件类型..."
            await self.send_message(
                content="文件整理任务已启动，正在分析目录结构...",
                team_id=task.team_id,
                msg_type=MessageType.STATUS_UPDATE,
                metadata={
                    "status": "working",
                    "monitor": self._build_file_monitor(
                        workspace=target_dir,
                        todo=todo,
                        note=(
                            "仅执行创建目录与移动文件，禁止删除。"
                            if organize_goal
                            else "未提供整理目标，已先按文件类型给出建议方案。"
                        ),
                        skills=skills,
                    ),
                },
            )

            # 保证用户能看到分析阶段，不会“瞬间跳到完成”
            min_analyze_stage = 1.0
            elapsed_analyze = time.monotonic() - stage_begin
            if elapsed_analyze < min_analyze_stage:
                await asyncio.sleep(min_analyze_stage - elapsed_analyze)

            todo[0]["status"] = "done"
            todo[0]["detail"] = "目录分析完成"
            todo[1]["status"] = "running"
            todo[1]["detail"] = (
                "正在生成整理预览方案..."
                if not force_execute
                else "正在创建子目录并移动文件..."
            )
            stage2_text = (
                "已完成分析，正在生成整理预览方案..."
                if not force_execute
                else "已完成分析，正在创建子文件夹并移动文件..."
            )
            await self.send_message(
                content=stage2_text,
                team_id=task.team_id,
                msg_type=MessageType.STATUS_UPDATE,
                metadata={
                    "status": "working",
                    "monitor": self._build_file_monitor(
                        workspace=target_dir,
                        todo=todo,
                        note="执行中：禁止删除文件，仅移动与重命名冲突文件。",
                        skills=skills,
                    ),
                },
            )

            if not force_execute:
                preview_stage_begin = time.monotonic()
                plan = await asyncio.to_thread(
                    preview_organize_plan,
                    target_dir,
                    organize_goal,
                )
                goal_suggestions = self._build_goal_suggestions(organize_goal, plan.category_counts)
                min_preview_stage = 1.0
                elapsed_preview = time.monotonic() - preview_stage_begin
                if elapsed_preview < min_preview_stage:
                    await asyncio.sleep(min_preview_stage - elapsed_preview)
                todo[1]["status"] = "pending"
                todo[1]["detail"] = "预览已生成，等待确认执行"
                todo[2]["status"] = "pending"
                todo[2]["detail"] = "等待执行完成后校验"
                plan_lines = [
                    f"- {name}: {count} 个"
                    for name, count in sorted(
                        plan.category_counts.items(),
                        key=lambda x: x[1],
                        reverse=True,
                    )
                ] or ["- 无可整理文件（目录可能为空）"]

                sample_lines = [
                    f"- `{item['source']}` -> `{item['target']}`"
                    for item in plan.sample_moves[:8]
                ]
                if not sample_lines:
                    sample_lines = ["- 无示例迁移项"]

                summary = (
                    "文件整理预览完成（未执行任何文件操作）。\n\n"
                    f"目录：`{plan.root_dir}`\n"
                    f"目标：{goal_label}\n"
                    f"可整理文件：{plan.total_files} 个\n\n"
                    "分类预估：\n" + "\n".join(plan_lines) + "\n\n"
                    "示例迁移：\n" + "\n".join(sample_lines) + "\n\n"
                    "建议整理目标（可在右侧面板选择后确认执行）：\n"
                    + "\n".join(
                        [
                            f"- {item['title']}：{item['goal']}（{item['reason']}）"
                            for item in goal_suggestions
                        ]
                    )
                    + "\n\n"
                    "如确认执行，请点击右侧任务监控面板中的“确认执行”。"
                )

                await self.stream_text(
                    text=summary,
                    team_id=task.team_id,
                    msg_type=MessageType.TASK_RESULT,
                    metadata={"status_label": "A_OK", "file_organize_preview": plan.to_dict()},
                )
                total_elapsed = round(time.time() - task_start, 1)
                await self.send_message(
                    content=f"文件整理建议方案完成· 耗时 **{total_elapsed}s**",
                    team_id=task.team_id,
                    msg_type=MessageType.STATUS_UPDATE,
                    metadata={
                        "status": "pending_confirm",
                        "total_elapsed": total_elapsed,
                        "monitor": self._build_file_monitor(
                            workspace=target_dir,
                            todo=todo,
                            note="预览完成：请确认是否执行文件整理",
                            skills=skills,
                            pending_confirm=True,
                            preview_plan=plan.to_dict(),
                            organize_goal=organize_goal,
                            goal_suggestions=goal_suggestions,
                        ),
                    },
                )
                return TaskResult(
                    task_id=task.id,
                    agent_name=self.name,
                    status=TaskStatus.COMPLETED,
                    content=summary,
                    metadata={
                        "file_organize_preview": plan.to_dict(),
                        "pending_confirm": True,
                        "preview_plan": plan.to_dict(),
                        "organize_goal": organize_goal,
                        "goal_suggestions": goal_suggestions,
                    },
                )

            # 用户确认执行后，直接执行整理
            stage2_begin = time.monotonic()
            report = await asyncio.to_thread(
                organize_directory_safe,
                target_dir,
                organize_goal,
            )

            min_organize_stage = 0.8
            elapsed_organize = time.monotonic() - stage2_begin
            if elapsed_organize < min_organize_stage:
                await asyncio.sleep(min_organize_stage - elapsed_organize)

            todo[1]["status"] = "done"
            todo[1]["detail"] = f"已完成文件移动（{report.moved_files}/{report.total_files}）"
            todo[2]["status"] = "running"
            todo[2]["detail"] = "正在校验文件数量与总大小..."
            await self.send_message(
                content="正在验证整理结果，检查是否存在文件丢失...",
                team_id=task.team_id,
                msg_type=MessageType.STATUS_UPDATE,
                metadata={
                    "status": "working",
                    "monitor": self._build_file_monitor(
                        workspace=target_dir,
                        todo=todo,
                        note="正在校验文件数量与总大小。",
                        skills=skills,
                    ),
                },
            )
            todo[2]["status"] = "done" if report.verify_ok else "failed"
            todo[2]["detail"] = report.verify_note

            category_lines = [
                f"- {name}: {count} 个"
                for name, count in sorted(
                    report.category_counts.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )
            ]
            if not category_lines:
                category_lines = ["- 无可整理文件（目录可能为空或仅包含子目录）"]

            summary = (
                f"文件整理完成（禁止删除模式）。\n\n"
                f"目录：`{report.root_dir}`\n"
                f"目标：{goal_label}\n"
                f"扫描文件：{report.total_files} 个\n"
                f"已移动：{report.moved_files} 个\n"
                f"创建子目录：{len(report.created_dirs)} 个\n"
                f"同名冲突重命名：{report.collisions} 次\n\n"
                f"分类结果：\n" + "\n".join(category_lines) + "\n\n"
                f"校验：{report.verify_note}"
            )

            await self.stream_text(
                text=summary,
                team_id=task.team_id,
                msg_type=MessageType.TASK_RESULT,
                metadata={
                    "status_label": "A_OK",
                    "file_organize": report.to_dict(),
                },
            )

            total_elapsed = round(time.time() - task_start, 1)
            await self.send_message(
                content=f"文件整理完成 · 耗时 **{total_elapsed}s**",
                team_id=task.team_id,
                msg_type=MessageType.STATUS_UPDATE,
                metadata={
                    "status": "completed",
                    "total_elapsed": total_elapsed,
                    "monitor": self._build_file_monitor(
                        workspace=target_dir,
                        todo=todo,
                        note=report.verify_note,
                        skills=skills,
                        artifacts_extra=[
                            {
                                "id": f"category-{idx}",
                                "name": f"分类目录：{name}",
                                "path": f"{target_dir}/{name}",
                                "type": "folder",
                                "openable": True,
                            }
                            for idx, name in enumerate(sorted(report.category_counts.keys())[:6], start=1)
                        ],
                    ),
                },
            )
            await self._auto_rename_team(task)
            return TaskResult(
                task_id=task.id,
                agent_name=self.name,
                status=TaskStatus.COMPLETED,
                content=summary,
                metadata={"file_organize": report.to_dict()},
            )
        except Exception as e:
            logger.error(f"[{self.name}] 文件整理失败: {e}")
            todo[0]["status"] = "failed"
            await self.send_message(
                content=f"文件整理任务失败: {str(e)}",
                team_id=task.team_id,
                msg_type=MessageType.TASK_RESULT,
                metadata={"status_label": "FAILED", "error": True},
            )
            await self.send_message(
                content="文件整理任务失败",
                team_id=task.team_id,
                msg_type=MessageType.STATUS_UPDATE,
                metadata={
                    "status": "completed",
                    "error": True,
                    "monitor": self._build_file_monitor(
                        workspace=target_dir,
                        todo=todo,
                        note="执行失败，请检查目录权限或路径是否有效。",
                        skills=skills,
                    ),
                },
            )
            return TaskResult(
                task_id=task.id,
                agent_name=self.name,
                status=TaskStatus.FAILED,
                content=f"文件整理任务失败: {str(e)}",
            )

    # ================================================================
    #  自动重命名对话
    # ================================================================

    async def _auto_rename_team(self, task: Task):
        """根据第一轮对话内容，自动生成 ≤10 字的对话标题

        触发条件：
        - 仅对以「新对话」开头的默认名称生效
        - 已重命名过的不再重复执行
        """
        import re

        try:
            from src.core.team import get_team_manager
            tm = get_team_manager()
            team = tm.get_team(task.team_id)
            if not team:
                return

            # 仅对自动生成的默认名称进行重命名
            if not team.name.startswith("新对话"):
                return

            # 从消息历史中取用户首问 + 已有专家产出
            history = self.bus.get_history(task.team_id)
            user_text = ""
            expert_briefs: list[str] = []
            for msg in history:
                if not user_text and msg.sender == "user" and (msg.content or "").strip():
                    user_text = (msg.content or "").strip().replace("\n", " ")[:120]
                if (
                    msg.type == MessageType.TASK_RESULT
                    and msg.sender not in {"team-lead", ""}
                    and (msg.content or "").strip()
                ):
                    brief = (msg.content or "").strip().replace("\n", " ")
                    expert_briefs.append(f"{msg.sender}: {brief[:60]}")
                    if len(expert_briefs) >= 3:
                        break

            if not user_text:
                user_text = task.description[:120]

            expert_context = (
                "\n".join(f"- {b}" for b in expert_briefs)
                if expert_briefs
                else "（暂无专家输出）"
            )

            # 优先用 LLM 生成标题
            new_name = ""
            try:
                title_prompt = (
                    "请根据以下对话信息，生成一个简短的对话标题。\n"
                    "要求：\n"
                    "- 最多10个中文字（或等量英文）\n"
                    "- 概括核心主题，不要废话\n"
                    "- 即使任务被中断，也要根据已有信息命名\n"
                    "- 直接输出标题文字，不要引号、不要解释\n\n"
                    f"用户问题：{user_text}\n\n"
                    f"已有中间结果：\n{expert_context}"
                )
                result = await self.llm.chat(
                    messages=[
                        ChatMessage(role="system", content="你是一个标题生成器，只输出标题文本。"),
                        ChatMessage(role="user", content=title_prompt),
                    ],
                    temperature=0.3,
                    max_tokens=30,
                )
                new_name = result.content.strip().strip('"\'《》「」【】').strip()
                if len(new_name) > 15:
                    new_name = new_name[:10]
            except Exception as llm_err:
                logger.warning(f"LLM 生成标题失败，使用本地兜底: {llm_err}")

            # LLM 失败或返回空时，本地截断用户首问作为标题
            if not new_name:
                cleaned = re.sub(r"^[#>*\-\d\.\s]+", "", user_text).strip()
                new_name = cleaned[:10] if cleaned else "对话"

            old_name = team.name
            tm.rename_team(task.team_id, new_name)
            await tm.save_team_to_db(team)
            logger.info(f"对话已自动重命名: {old_name} -> {new_name}")

            # 通过 WebSocket 推送重命名事件
            await self.send_message(
                content="",
                team_id=task.team_id,
                msg_type=MessageType.SYSTEM,
                metadata={
                    "action": "team_renamed",
                    "team_id": task.team_id,
                    "new_name": new_name,
                },
            )
        except Exception as e:
            logger.warning(f"自动重命名对话失败: {e}")

    # ================================================================
    #  iMessage 推送
    # ================================================================

    async def _push_imessage_summary(self, task_title: str, summary: str, elapsed: float):
        """任务完成后，通过 iMessage 推送精简摘要（仅在 Bot 激活时生效）"""
        # 检查 iMessage Bot 是否处于激活状态，未激活则不推送
        try:
            from src.tools.imessage_bot import get_imessage_bot
            bot = get_imessage_bot()
            if not bot.is_running:
                return
        except Exception:
            return

        # 从 .env 读取推送目标
        from src.config import ROOT_DIR
        push_to = ""
        try:
            env_path = ROOT_DIR / ".env"
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("IMESSAGE_PUSH_TO="):
                        push_to = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
        if not push_to:
            return

        # 生成纯文本摘要（去除 Markdown 格式）
        plain = summary
        # 去掉 Markdown 标记
        import re
        plain = re.sub(r'\*\*(.+?)\*\*', r'\1', plain)  # **bold**
        plain = re.sub(r'\*(.+?)\*', r'\1', plain)       # *italic*
        plain = re.sub(r'#{1,6}\s*', '', plain)           # ## headings
        plain = re.sub(r'`(.+?)`', r'\1', plain)          # `code`
        plain = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', plain) # [text](url)
        plain = re.sub(r'---+', '', plain)                 # ---
        plain = plain.strip()

        # 截断到 500 字
        if len(plain) > 500:
            plain = plain[:497] + "..."

        msg = f"📋 {task_title}\n⏱ {elapsed}s\n\n{plain}"

        try:
            from src.tools.imessage import send_imessage
            result = await send_imessage(push_to, msg)
            if result.success:
                logger.info(f"[iMessage推送] 已发送摘要到 {push_to}")
            else:
                logger.warning(f"[iMessage推送] 发送失败: {result.error}")
        except Exception as e:
            logger.warning(f"[iMessage推送] 异常: {e}")

    # ================================================================
    #  直接回答核查
    # ================================================================

    async def _run_direct_answer_review(
        self,
        task: Task,
        answer: str,
    ) -> str | None:
        """对直接回答进行核查，返回修正后的内容；若无需修正则返回 None"""
        reviewer_name = "内容核查专家"

        review_system_prompt = (
            "你是一位严谨的内容核查专家，负责审查 AI 生成的回答。\n"
            "你必须扮演**挑战者**角色，假设回答中存在错误，主动寻找问题。\n\n"
            "## 核查方法（必须逐步执行，不可跳过任何步骤）\n\n"
            "### ⚠️ 步骤 0：目标达成检验（最高优先级，必须第一个执行！）\n"
            "这一步决定回答是否存在根本性方向错误，比其他所有步骤都重要。\n"
            "请严格回答以下四个问题：\n\n"
            "**Q1. 用户的最终目标是什么？**\n"
            "不是问题表面在问什么（如「开车还是走路」），而是用户真正想达成的事（如「让车被洗干净」）。\n\n"
            "**Q2. 达成这个目标有哪些不可或缺的物理/逻辑前提？**\n"
            "列出所有必要条件。例如：\n"
            "- 「洗车」→ 车必须被送到洗车店（人走过去没用，车到不了就洗不了）\n"
            "- 「寄快递」→ 包裹必须被带到快递点\n"
            "- 「给车加油」→ 车必须开到加油站\n"
            "- 「去医院看病」→ 人必须到医院\n\n"
            "**Q3. 如果用户完全按照回答的建议去做，目标能否达成？**\n"
            "请做一次完整的心理模拟：一步步想象用户照做后会发生什么。\n"
            "如果有任何一步导致目标无法达成，回答就是**根本性错误**。\n\n"
            "**Q4. 问题中的数字/条件是否是干扰项？**\n"
            "距离、时间、价格等数字信息可能会误导你关注效率而忽略可行性。\n"
            "先确认「能不能做到」，再讨论「怎么做更好」。\n\n"
            "➡️ **如果 Q3 的答案是「不能达成」，直接标记为 ❌ 需要重大修正，"
            "跳到步骤 6 输出结论和修正版本。其他步骤可以简化。**\n\n"
            "### 步骤 1：提取关键论断\n"
            "从回答中逐条提取所有事实性声明、数据引用和因果推论，编号列出。\n\n"
            "### 步骤 2：场景还原与常识验证\n"
            "1. **完整还原用户的真实场景**：用户想做什么？涉及哪些实体（人、物、地点）？"
            "它们之间有什么物理/逻辑依赖关系？\n"
            "2. **提取隐含前提**：用户的话中有哪些没有明说但不可或缺的前提条件？\n"
            "3. **现实可行性检验**：按照回答的建议，在现实中一步步执行，"
            "能否真正达成用户的目标？有没有物理上不可能或荒谬的环节？\n"
            "4. **干扰信息识别**：问题中是否有看似重要但实际上不应影响结论的信息？\n\n"
            "### 步骤 3：逐条验证\n"
            "对每条论断独立验证：\n"
            "- 事实类：该说法是否准确？有无张冠李戴、时间错误、数据编造？\n"
            "- 推理类：前提是否成立？推理过程是否有跳跃？结论是否必然成立？\n"
            "  常见逻辑谬误检查：以偏概全、因果倒置、滑坡谬误、虚假二分、诉诸权威、"
            "循环论证、稻草人谬误\n"
            "- 遗漏类：是否忽略了重要的反面论据或替代方案？\n\n"
            "### 步骤 4：中文语义审查\n"
            "重点检查以下中文特有的语义问题：\n"
            "- **歧义消解**：是否存在一词多义未明确的情况？\n"
            "- **指代不清**：代词的指代对象是否明确？\n"
            "- **成语典故误用**：成语、俗语是否符合原义？\n"
            "- **语义偏移**：是否偷换概念？\n"
            "- **中文表达准确性**：是否有翻译腔或生硬表达？\n\n"
            "### 步骤 5：交叉检验\n"
            "检查论断之间是否存在自相矛盾。\n\n"
            "### 步骤 6：输出结论\n"
            "- 核查结论：✅ 通过 / ⚠️ 部分修正 / ❌ 需要重大修正\n"
            "- 问题清单：逐条列出发现的问题，标注严重程度（❌ 错误 / ⚠️ 存疑 / 💡 建议）\n"
            "- 【核查后的最终版本】：如果原文无误直接输出原文；有修正则输出完整修正版\n\n"
            "## 重要原则\n"
            "- **目标可达性是第一优先级**：如果建议本身无法达成用户目标，其他优化都无意义\n"
            "- 你的目标是找出真正的问题，不是为了挑刺而挑刺\n"
            "- 对于你无法确认的事实，标注为「⚠️ 存疑，建议核实」而非直接判错\n"
            "- 逻辑错误和语义错误同等重要，都需要重点关注"
        )

        review_prompt = (
            f"用户问题: {task.title}\n"
            f"问题描述: {task.description}\n\n"
            f"---\n\n"
            f"以下是需要核查的回答内容：\n\n{answer}"
        )

        temp_agent = AgentBase(
            name=reviewer_name,
            role="reviewer",
            role_label="Checker",
            system_prompt=review_system_prompt,
            llm=self.reviewer_llm,
            message_bus=self.bus,
            register_bus=False,
        )

        try:
            response = await temp_agent.think_stream(
                user_input=review_prompt,
                team_id=task.team_id,
                msg_type=MessageType.TASK_RESULT,
                metadata={
                    "status_label": "REVIEW",
                    "expert_name": reviewer_name,
                    "round": "review",
                    "is_review": True,
                    "reviewer_model": getattr(self.reviewer_llm, "model", ""),
                },
            )
            return response
        except Exception as e:
            logger.warning(f"直接回答核查失败（不影响输出）: {e}")
            return None

    # ================================================================
    #  内部方法
    # ================================================================

    async def _stream_plan(self, task: Task) -> tuple[str, str]:
        """流式生成专家方案，返回 (完整文本, 消息ID)"""
        msg_id = uuid4().hex[:12]
        init_msg = Message(
            id=msg_id,
            type=MessageType.AGENT_MESSAGE,
            sender=self.name,
            team_id=task.team_id,
            content="",
            metadata={"is_thinking": True, "streaming": True},
        )
        await self.bus.publish(init_msg)

        # 使用独立的 plan 对话历史，避免草稿/汇总内容污染规划上下文
        # 如果任务带有 scene_type，加载对应方法论作为上下文
        methodology_context = ""
        scene_template_context = ""
        scene_type = task.metadata.get("scene_type", "")
        if scene_type:
            from src.stores.methodology_lib import get_methodology_lib
            from src.stores.scene_registry import get_scene_registry
            scene_reg = get_scene_registry()
            scene_category = task.metadata.get("scene_category", "")
            scene_cat = scene_reg.get(scene_category)
            methodology_name = scene_cat.methodology if scene_cat else ""
            if methodology_name:
                method_lib = get_methodology_lib()
                methodology = method_lib.get(methodology_name)
                if methodology:
                    steps_text = "\n".join(
                        f"  {idx+1}. {s['name']}: {s['description']}"
                        for idx, s in enumerate(methodology.steps)
                    )
                    methodology_context = (
                        f"\n\n📋 本任务适用方法论「{methodology.display_name}」，请参考以下步骤指导专家工作：\n"
                        f"{steps_text}\n"
                    )
            scene_form_data = task.metadata.get("scene_form_data", {}) or {}
            scene_template = scene_reg.get_template(scene_category, scene_type)
            if isinstance(scene_form_data, dict) and scene_form_data:
                field_lines = "\n".join(
                    f"- {k}: {v}" for k, v in scene_form_data.items() if isinstance(v, str) and v.strip()
                )
                if field_lines:
                    scene_template_context += (
                        "\n\n🧾 用户已确认的场景字段（事实输入，必须直接采用）：\n"
                        f"{field_lines}\n"
                    )
            if scene_template and scene_template.prompt_template:
                rendered_template = scene_template.render_prompt(
                    {
                        k: v for k, v in scene_form_data.items()
                        if isinstance(k, str) and isinstance(v, str)
                    }
                )
                scene_template_context += (
                    "\n📌 场景模板要求（作为输出约束，已填入用户字段）：\n"
                    f"{rendered_template.strip()}\n"
                )

        user_prompt = f"用户任务:\n{task.description}"
        if scene_type:
            user_prompt += (
                "\n\n[系统提示] 该任务来自场景表单，用户已完成前置结构化信息填写。"
                "除非任务文本明确出现关键字段为空/未知，否则不要再次返回 info_request。"
            )
        if scene_template_context:
            user_prompt += scene_template_context
        if methodology_context:
            user_prompt += methodology_context

        messages = [
            ChatMessage(role="system", content=self._get_system_prompt()),
            *self._plan_conversation,
            ChatMessage(role="user", content=user_prompt),
        ]

        plan_text = ""
        _PLAN_CHUNK_TIMEOUT = 60.0
        try:
            stream_iter = self.llm.stream_chat(messages).__aiter__()
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        stream_iter.__anext__(), timeout=_PLAN_CHUNK_TIMEOUT
                    )
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    logger.warning(
                        f"[{self.name}] 规划流式超时（{_PLAN_CHUNK_TIMEOUT}s），"
                        f"已收到 {len(plan_text)} 字符"
                    )
                    break
                plan_text += chunk
                await self.bus.publish(Message(
                    type=MessageType.STREAM_CHUNK,
                    sender=self.name,
                    team_id=task.team_id,
                    content=chunk,
                    metadata={"target_id": msg_id},
                ))
        except Exception as e:
            logger.error(f"[{self.name}] 流式生成方案异常: {e}")
            if not plan_text:
                try:
                    response = await self.llm.chat(messages)
                    plan_text = response.content
                except Exception as fallback_err:
                    logger.error(f"[{self.name}] 规划非流式降级也失败: {fallback_err}")
                    plan_text = '{"thinking": "规划失败", "direct_answer": "抱歉，服务暂时不可用，请稍后重试。", "experts": []}'

        # 仅在 plan 对话历史中记录，保持上下文纯净（只有 JSON 格式的规划交互）
        self._plan_conversation.append(
            ChatMessage(role="user", content=f"用户任务:\n{task.description}")
        )
        self._plan_conversation.append(
            ChatMessage(role="assistant", content=plan_text)
        )
        if len(self._plan_conversation) > 10:
            self._plan_conversation = self._plan_conversation[-6:]

        return plan_text, msg_id

    async def _run_round1_with_dependencies(
        self, experts: list[dict], task: Task
    ) -> list[TaskResult | Exception]:
        """Round 1 执行编排：支持专家依赖（depends_on）"""
        if not experts:
            return []

        pending_names = [e["name"] for e in experts]
        expert_by_name = {e["name"]: e for e in experts}
        # 为每位专家预留独立引用编号区间，避免多专家结果合并时 [1]/[2] 冲突
        reference_start_by_name = {
            e["name"]: idx * 10 + 1 for idx, e in enumerate(experts)
        }
        completed_by_name: dict[str, TaskResult] = {}
        all_results: list[TaskResult | Exception] = []

        while pending_names:
            ready_names: list[str] = []
            for name in pending_names:
                expert = expert_by_name[name]
                deps = [
                    d
                    for d in (expert.get("depends_on") or [])
                    if isinstance(d, str) and d.strip() and d in expert_by_name
                ]
                if all(dep in completed_by_name for dep in deps):
                    ready_names.append(name)

            # 出现环依赖/非法依赖时，兜底执行一个，避免整体卡死
            if not ready_names:
                fallback_name = pending_names[0]
                logger.warning(
                    f"[{self.name}] 检测到专家依赖无法满足，按兜底顺序执行: {fallback_name}"
                )
                ready_names = [fallback_name]

            wave_inputs: list[dict] = []
            for name in ready_names:
                original = expert_by_name[name]
                deps = [
                    d
                    for d in (original.get("depends_on") or [])
                    if isinstance(d, str) and d.strip() and d in completed_by_name
                ]
                dep_context = ""
                if deps:
                    dep_parts: list[str] = []
                    for dep_name in deps:
                        dep_result = completed_by_name.get(dep_name)
                        if dep_result and dep_result.content:
                            dep_parts.append(f"【{dep_name}】\n{dep_result.content}")
                    if dep_parts:
                        dep_context = (
                            "\n\n--- 前置专家结论（你必须先吸收再继续）---\n"
                            + "\n\n".join(dep_parts)
                        )
                expert_input = dict(original)
                expert_input["_dependency_context"] = dep_context
                expert_input["_reference_start_index"] = reference_start_by_name.get(name, 1)
                wave_inputs.append(expert_input)

            wave_coros = [self._run_expert(expert, task) for expert in wave_inputs]
            wave_results = await asyncio.gather(*wave_coros, return_exceptions=True)

            for idx, result in enumerate(wave_results):
                current_name = ready_names[idx]
                if isinstance(result, TaskResult) and result.status == TaskStatus.COMPLETED:
                    completed_by_name[current_name] = result
                elif isinstance(result, Exception):
                    logger.error(f"专家 Round 1 异常: {current_name} -> {result}")
                all_results.append(result)

            pending_names = [name for name in pending_names if name not in ready_names]

        return all_results

    async def _run_expert(self, expert: dict, parent_task: Task) -> TaskResult:
        """Round 1：创建临时专家，独立完成子任务（可选联网搜索 + 网页读取 + iMessage）"""
        name = expert["name"]
        persona = expert["persona"]
        sub_task_desc = expert["task"]
        dependency_context = expert.get("_dependency_context", "")
        reference_start_index = int(expert.get("_reference_start_index", 1) or 1)
        needs_search = expert.get("needs_search", False)
        search_query = expert.get("search_query", "")
        needs_url_read = expert.get("needs_url_read", False)
        read_urls = expert.get("read_urls", [])
        needs_imessage = expert.get("needs_imessage", False)
        imessage_to = expert.get("imessage_to", "")
        imessage_content = expert.get("imessage_content", "")

        # 联网搜索（如果需要）
        search_context = ""
        search_references: list[dict] = []
        if needs_search and search_query:
            await self.send_message(
                content=f"{self._skill_label('web_search')} **{name}** 正在联网搜索: {search_query}",
                team_id=parent_task.team_id,
                msg_type=MessageType.STATUS_UPDATE,
                metadata={"status": "working", "search_query": search_query},
            )
            from src.tools.web_search import (
                web_search,
                web_search_news,
                format_search_results,
                build_references,
            )
            results = await web_search(search_query, max_results=5)
            # 文本搜索为空时，回退新闻搜索，尽可能拿到可溯源来源
            if not results:
                results = await web_search_news(search_query, max_results=5)
            search_references = build_references(results, start_index=reference_start_index)
            search_context = format_search_results(results, search_query, search_references)

        # 网页读取（如果需要）
        url_context = ""
        if needs_url_read and read_urls:
            url_list_str = ", ".join(read_urls[:3])  # 最多读3个
            await self.send_message(
                content=f"{self._skill_label('web_reading')} **{name}** 正在读取网页内容...",
                team_id=parent_task.team_id,
                msg_type=MessageType.STATUS_UPDATE,
                metadata={"status": "working", "read_urls": read_urls[:3]},
            )
            from src.tools.web_reader import read_urls as fetch_urls, format_webpage
            pages = await fetch_urls(read_urls[:3])
            url_parts = []
            for page in pages:
                url_parts.append(format_webpage(page))
            url_context = "\n\n---\n\n".join(url_parts)

        # iMessage 发送（如果需要）
        imessage_result_text = ""
        if needs_imessage:
            if not imessage_to:
                imessage_result_text = (
                    "❌ iMessage 未发送：缺少收件人信息。"
                    "请用户提供收件人的手机号（如 +8613800138000）或 Apple ID 邮箱。"
                )
            elif not imessage_content:
                imessage_result_text = "❌ iMessage 未发送：缺少消息内容。"
            else:
                await self.send_message(
                    content=f"{self._skill_label('imessage')} **{name}** 正在发送 iMessage...",
                    team_id=parent_task.team_id,
                    msg_type=MessageType.STATUS_UPDATE,
                    metadata={"status": "working", "imessage_to": imessage_to},
                )
                from src.tools.imessage import send_imessage, format_send_result
                result = await send_imessage(imessage_to, imessage_content)
                imessage_result_text = format_send_result(result)

        # 构建专家 prompt
        system_parts = [f"你是{name}。{persona}"]
        if url_context:
            url_instruction = (
                "\n\n你拥有网页读取能力，以下是读取到的网页正文内容：\n"
                + url_context
                + "\n\n【重要约束 - 严格溯源】"
                  "\n1. 你必须严格依据上述原文的字面信息进行分析和回答，不得编造、臆测或添加原文中不存在的内容。"
                  '\n2. 如果原文信息不足以回答某个问题，请明确指出「原文未提及」，而不是自行补充。'
                  "\n3. 引用原文观点时，必须使用角标标注出处，格式为上标数字 [1][2][3]...，在正文末尾附上「参考来源」列表。"
                  "\n4. 角标引用示例："
                  "\n   - 正文中：该研究表明AI将在未来五年内改变教育模式[1]，同时在线学习的比例将超过50%[2]。"
                  "\n   - 文末附："
                  "\n     ---"
                  "\n     **参考来源**"
                  "\n     [1] 原文第3段：「AI技术正在从根本上改变传统教育...」"
                  "\n     [2] 原文第5段：「数据显示在线学习占比已达48%...」"
                  "\n5. 每个关键论点、数据、结论都必须有对应角标，确保读者可以溯源到原文具体位置。"
            )
            system_parts.append(url_instruction)
        if search_context:
            system_parts.append(
                "\n\n你拥有联网搜索能力，以下是搜索到的最新信息。"
                "\n⚠️ **重要约束**：当搜索结果与你的训练数据/已有认知冲突时，**必须以搜索结果为准**。"
                "\n搜索结果是实时获取的最新信息，比你的训练数据更准确、更及时。"
                "\n严禁忽略搜索结果而凭自身知识编造答案。"
                "\n\n📌 **引用要求**：引用搜索结果时，必须使用角标标记 [1]、[2]、[3] 等（对应下方来源编号）。"
                "\n例如：春晚将于2月16日晚8点播出[1]，节目单已发布[2]。\n\n"
                f"{search_context}"
            )
        if imessage_result_text:
            system_parts.append(
                "\n\n你拥有 iMessage 发送能力，以下是本次发送操作的结果：\n"
                + imessage_result_text
                + "\n\n请根据发送结果向用户汇报：发送是否成功、发给了谁、内容是什么。如果失败请说明原因。"
            )
        if dependency_context:
            system_parts.append(
                "\n\n你存在前置依赖。请先准确吸收前置专家结论，再在此基础上完成你的任务。"
                "避免重复前置工作，也不要与前置结论冲突。"
            )
        system_parts.append("\n\n请直接输出分析结果，不要重复任务描述，保持专业简洁。")
        if search_context:
            system_parts.append("引用搜索结果时请注明来源。")
        if url_context:
            system_parts.append("务必使用[1][2]角标标注每个引用，文末附参考来源列表，禁止脱离原文自行发挥。")

        # 注入知识型技能的 prompt_template（如公文写作规范）
        from src.stores.skill_registry import get_skill_registry
        knowledge_skills = [
            s for s in get_skill_registry().resolve_active_skills(
                task_metadata=parent_task.metadata
            )
            if s.category == "knowledge" and s.prompt_template
        ]
        for ks in knowledge_skills:
            system_parts.append(f"\n\n{ks.prompt_template}")

        temp_agent = AgentBase(
            name=name,
            role="expert",
            role_label="Expert",
            system_prompt="".join(system_parts),
            llm=self.llm,
            message_bus=self.bus,
            register_bus=False,
        )

        metadata = {
            "status_label": "A_OK",
            "expert_name": name,
            "round": 1,
        }
        if needs_search:
            metadata["has_search"] = True
            metadata["search_query"] = search_query
        if needs_url_read:
            metadata["has_url_read"] = True
            metadata["read_urls"] = read_urls[:3]
        if needs_imessage:
            metadata["has_imessage"] = True
            metadata["imessage_to"] = imessage_to

        response = await temp_agent.think_stream(
            user_input=f"{sub_task_desc}{dependency_context}",
            team_id=parent_task.team_id,
            msg_type=MessageType.TASK_RESULT,
            metadata=metadata,
        )

        result_metadata: dict = {}
        if search_references:
            result_metadata["references"] = search_references

        return TaskResult(
            task_id=parent_task.id,
            agent_name=name,
            status=TaskStatus.COMPLETED,
            content=response,
            metadata=result_metadata,
        )

    async def _run_expert_discussion(
        self,
        expert: dict,
        r1_results: list[TaskResult],
        parent_task: Task,
    ) -> TaskResult:
        """Round 2：专家看到所有人的 Round 1 结果，进行协作讨论"""
        name = expert["name"]
        persona = expert["persona"]

        # 构建其他专家的结果上下文
        others_text = []
        own_text = ""
        for r in r1_results:
            if r.agent_name == name:
                own_text = r.content
            else:
                others_text.append(f"【{r.agent_name}】\n{r.content}")

        other_context = "\n\n---\n\n".join(others_text)

        discussion_prompt = (
            f"以下是其他专家对同一任务的分析结果：\n\n"
            f"{other_context}\n\n"
            f"---\n\n你之前的分析：\n{own_text}\n\n"
            f"---\n\n"
            f"请基于你的专业视角对其他专家的观点做出回应（保持简洁）：\n"
            f"1. 你认同哪些观点？为什么？\n"
            f"2. 你不认同或需要补充什么？\n"
            f"3. 综合所有信息，你的最终结论是什么？"
        )

        temp_agent = AgentBase(
            name=name,
            role="expert",
            role_label="Expert",
            system_prompt=(
                f"你是{name}。{persona}\n\n"
                "现在进入团队协作讨论环节。请基于其他专家的分析结果进行评价和补充，"
                "聚焦于互动和碰撞，不要简单重复自己之前的观点。"
            ),
            llm=self.llm,
            message_bus=self.bus,
            register_bus=False,
        )

        response = await temp_agent.think_stream(
            user_input=discussion_prompt,
            team_id=parent_task.team_id,
            msg_type=MessageType.TASK_RESULT,
            metadata={
                "status_label": "A_OK",
                "expert_name": name,
                "round": 2,
                "is_discussion": True,
            },
        )

        return TaskResult(
            task_id=parent_task.id,
            agent_name=name,
            status=TaskStatus.COMPLETED,
            content=response,
        )

    async def _run_expert_review(
        self,
        expert: dict,
        r1_result: TaskResult | None,
        r2_result: TaskResult | None,
        parent_task: Task,
    ) -> TaskResult:
        """领域核查：由专门的核查专家验证每位专家的分析结果

        核查内容：
        - 事实准确性：数据、引用、结论是否有据可依
        - 逻辑一致性：论证过程是否自洽、因果关系是否成立
        - 完整性：是否遗漏了关键维度或重要信息
        - 偏见检测：是否存在片面或误导性的表述
        """
        expert_name = expert["name"]
        expert_persona = expert["persona"]
        reviewer_name = f"核查·{expert_name}"

        # 组合该专家在各轮次的全部输出
        answer_parts = []
        if r1_result:
            answer_parts.append(f"## 独立分析（Round 1）\n{r1_result.content}")
        if r2_result:
            answer_parts.append(f"## 协作讨论（Round 2）\n{r2_result.content}")
        full_answer = "\n\n---\n\n".join(answer_parts)

        review_system_prompt = (
            f"你是「{expert_name}」领域的资深核查专家。\n"
            f"被核查专家的角色定位：{expert_persona}\n\n"
            "你必须扮演**挑战者**角色，假设分析中存在错误，主动寻找问题。\n\n"
            "## 核查方法（必须逐步执行，不可跳过任何步骤）\n\n"
            "### ⚠️ 步骤 0：目标达成检验（最高优先级，必须第一个执行！）\n"
            "这一步决定分析是否存在根本性方向错误，比其他所有步骤都重要。\n"
            "请严格回答以下四个问题：\n\n"
            "**Q1. 用户的最终目标是什么？**\n"
            "不是问题表面在问什么，而是用户真正想达成的事。\n\n"
            "**Q2. 达成这个目标有哪些不可或缺的物理/逻辑前提？**\n"
            "列出所有必要条件。例如：\n"
            "- 「洗车」→ 车必须被送到洗车店\n"
            "- 「寄快递」→ 包裹必须被带到快递点\n"
            "- 「给车加油」→ 车必须开到加油站\n\n"
            "**Q3. 如果用户完全按照分析的建议去做，目标能否达成？**\n"
            "请做一次完整的心理模拟：一步步想象用户照做后会发生什么。\n\n"
            "**Q4. 问题中的数字/条件是否是干扰项？**\n"
            "先确认「能不能做到」，再讨论「怎么做更好」。\n\n"
            "➡️ **如果 Q3 的答案是「不能达成」，直接标记为 ❌ 需要重大修正，"
            "跳到步骤 6 输出结论和修正版本。**\n\n"
            "### 步骤 1：提取关键论断\n"
            "从分析中逐条提取所有事实性声明、数据引用和因果推论，编号列出。\n\n"
            "### 步骤 2：场景还原与常识验证\n"
            "1. **完整还原用户的真实场景**：用户想做什么？涉及哪些实体？"
            "它们之间有什么物理/逻辑依赖关系？\n"
            "2. **提取隐含前提**：用户的话中有哪些没有明说但不可或缺的前提条件？\n"
            "3. **现实可行性检验**：按照回答的建议一步步执行，"
            "能否真正达成用户的目标？\n"
            "4. **干扰信息识别**：问题中是否有看似重要但实际上不应影响结论的信息？\n\n"
            "### 步骤 3：逐条验证\n"
            "对每条论断独立验证：\n"
            "- 事实类：该说法是否准确？\n"
            "- 推理类：前提是否成立？推理是否有逻辑跳跃？\n"
            "- 遗漏类：是否忽略了重要的反面论据或替代方案？\n\n"
            "### 步骤 4：中文语义审查\n"
            "重点检查歧义消解、指代不清、成语误用、语义偏移、术语准确性等。\n\n"
            "### 步骤 5：交叉检验\n"
            "- 论断之间是否自相矛盾？\n"
            "- 结论是否真的由论据支撑？\n\n"
            "### 步骤 6：输出结论\n"
            "- 核查结论：✅ 通过 / ⚠️ 部分修正 / ❌ 需要重大修正\n"
            "- 问题清单：逐条列出，标注严重程度（❌ 错误 / ⚠️ 存疑 / 💡 建议）\n"
            "- 【核查后的修正版本】：无误则输出原文；有修正则输出完整修正版\n\n"
            "## 重要原则\n"
            "- **目标可达性是第一优先级**：如果建议本身无法达成用户目标，其他优化都无意义\n"
            "- 逻辑错误和语义错误同等重要，都需要重点关注\n"
            "- 对无法确认的事实标注「⚠️ 存疑」而非直接判错\n"
            "- 目标是找出真正的问题，不是为挑刺而挑刺"
        )

        review_prompt = (
            f"原始任务: {parent_task.title}\n"
            f"任务描述: {parent_task.description}\n\n"
            f"---\n\n"
            f"以下是【{expert_name}】的分析结果，请进行领域核查：\n\n"
            f"{full_answer}"
        )

        temp_agent = AgentBase(
            name=reviewer_name,
            role="reviewer",
            role_label="Checker",
            system_prompt=review_system_prompt,
            llm=self.reviewer_llm,
            message_bus=self.bus,
            register_bus=False,
        )

        response = await temp_agent.think_stream(
            user_input=review_prompt,
            team_id=parent_task.team_id,
            msg_type=MessageType.TASK_RESULT,
            metadata={
                "status_label": "REVIEW",
                "expert_name": reviewer_name,
                "reviewed_expert": expert_name,
                "round": "review",
                "is_review": True,
                "reviewer_model": getattr(self.reviewer_llm, "model", ""),
            },
        )

        return TaskResult(
            task_id=parent_task.id,
            agent_name=reviewer_name,
            status=TaskStatus.COMPLETED,
            content=response,
            metadata={"reviewed_expert": expert_name},
        )

    async def _summarize_stream(
        self,
        task: Task,
        r1_results: list[TaskResult],
        r2_results: list[TaskResult],
        review_results: list[TaskResult] | None = None,
    ) -> str:
        """综合协作结果与核查意见，流式输出最终报告

        优先使用核查后的修正版本；若无核查结果则使用原始分析。
        """
        # 合并所有专家的引用源
        all_references: list[dict] = []
        for r in r1_results:
            refs = r.metadata.get("references", [])
            for ref in refs:
                if ref not in all_references:
                    all_references.append(ref)

        r1_parts = "\n\n---\n\n".join(
            f"【{r.agent_name}】\n{r.content}" for r in r1_results
        )
        r2_parts = "\n\n---\n\n".join(
            f"【{r.agent_name} · 讨论回应】\n{r.content}" for r in r2_results
        ) if r2_results else "（无协作讨论记录）"

        review_section = ""
        if review_results:
            review_parts = "\n\n---\n\n".join(
                f"【{r.agent_name}】\n{r.content}" for r in review_results
            )
            review_section = (
                f"\n\n## 第三轮：领域核查\n"
                f"以下是各领域核查专家的验证结果和修正版本，"
                f"请优先采纳核查后的修正内容：\n\n{review_parts}"
            )

        citation_instruction = ""
        if all_references:
            citation_instruction = (
                "\n\n📌 **引用要求**：专家分析中使用了 [1]、[2] 等角标引用搜索来源。"
                "你在汇总时必须保留这些角标，让读者可以溯源。"
                "角标编号必须与专家使用的编号一致，不要重新编号。\n"
            )

        scene_constraints = self._build_scene_constraints(task)
        prompt = (
            "以下是专家团队的多轮协作结果及领域核查意见，请汇总为一份高质量的最终报告。\n"
            "**重要：优先采用领域核查后的修正版本**，核查专家已验证事实准确性和逻辑一致性。\n"
            "注意整合各专家的共识、分歧和互补观点。\n"
            "⚠️ **严格约束**：你必须忠实于专家提供的分析内容和数据，不得篡改、忽略或凭自身知识替换专家引用的搜索结果和事实信息。"
            "如果专家引用了联网搜索结果中的具体日期、数据、事件等，你必须原样保留。\n"
            f"{citation_instruction}"
            + scene_constraints
            + "直接输出报告内容，不要说'以下是汇总'之类的套话。\n\n"
            f"原始任务: {task.title}\n\n"
            f"## 第一轮：独立分析\n{r1_parts}\n\n"
            f"## 第二轮：协作讨论\n{r2_parts}"
            f"{review_section}"
        )

        # 将引用源作为 metadata 附到最终消息上
        summary_metadata: dict = {}
        if all_references:
            summary_metadata["references"] = all_references

        return await self.think_stream(
            user_input=prompt,
            team_id=task.team_id,
            msg_type=MessageType.TASK_RESULT,
            system_prompt=NATURAL_LANGUAGE_PROMPT,
            metadata=summary_metadata,
        )

    @staticmethod
    def _build_thinking_content(
        thinking: str, experts: list[dict], skills_used: list[str] | None = None,
        enable_review: bool = False,
    ) -> str:
        """构建结构化思考内容"""
        from src.stores.skill_registry import get_skill_registry
        sr = get_skill_registry()

        lines = [f"**思考过程：** {thinking}", ""]
        lines.append(f"基于分析，我将组建 **{len(experts)} 位专家** 协作完成：\n")
        for i, e in enumerate(experts, 1):
            tags = ""
            # 从技能注册中心获取各工具技能的图标和名称
            if e.get("needs_search"):
                s = sr.get("web_search")
                label = s.label if s else "🔍 联网搜索"
                sq = e.get("search_query", "")
                tags += f" {label}「{sq}」" if sq else f" {label}"
            if e.get("needs_url_read"):
                s = sr.get("web_reading")
                label = s.label if s else "📄 网页读取"
                url_count = len(e.get("read_urls", []))
                tags += f" {label}（{url_count}个链接）" if url_count else f" {label}"
            if e.get("needs_imessage"):
                s = sr.get("imessage")
                label = s.label if s else "💬 iMessage"
                ito = e.get("imessage_to", "")
                tags += f" {label} → {ito}" if ito else f" {label}"
            lines.append(f"**{i}. {e['name']}**{tags}")
            lines.append(f"   - 角色定位：{e['persona'][:80]}")
            lines.append(f"   - 负责任务：{e['task']}")
            deps = e.get("depends_on") or []
            if deps:
                lines.append(f"   - 前置依赖：{', '.join(deps)}")
            lines.append("")
        if enable_review:
            if len(experts) == 1:
                lines.append("流程：**专家分析 → 领域核查 → 生成报告**")
            else:
                lines.append("协作流程：**独立分析 → 互评讨论 → 领域核查 → 综合汇总**")
        else:
            if len(experts) == 1:
                lines.append("流程：**专家分析 → 生成报告**")
            else:
                lines.append("协作流程：**独立分析 → 互评讨论 → 综合汇总**")
        if skills_used:
            lines.append("")
            lines.append(f"已启用技能：{' · '.join(skills_used)}")
        return "\n".join(lines)

    @staticmethod
    def _skill_label(skill_name: str, fallback: str = "") -> str:
        """从技能注册中心获取技能标签（带图标），如 '🔍 联网搜索'"""
        from src.stores.skill_registry import get_skill_registry
        s = get_skill_registry().get(skill_name)
        if s:
            return s.label
        return fallback or skill_name

    @staticmethod
    def _format_tokens(n: int) -> str:
        if n < 1000:
            return str(n)
        return f"{n / 1000:.1f}k"

    def _parse_plan(self, text: str) -> dict:
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start < 0 or end <= start:
                return {"thinking": "", "direct_answer": "", "info_request": None, "experts": []}
            data = json.loads(text[start:end])
            thinking = data.get("thinking", data.get("analysis", ""))
            direct_answer = data.get("direct_answer", "")
            info_request = data.get("info_request")
            experts = data.get("experts", [])
            valid = [e for e in experts if all(k in e for k in ("name", "persona", "task"))]
            # 规范化 depends_on：仅保留存在于专家列表中的名称
            valid_names = {e["name"] for e in valid}
            normalized: list[dict] = []
            for e in valid[:4]:
                deps = e.get("depends_on", [])
                if not isinstance(deps, list):
                    deps = []
                clean_deps: list[str] = []
                for d in deps:
                    if isinstance(d, str):
                        dn = d.strip()
                        if dn and dn in valid_names and dn != e["name"]:
                            clean_deps.append(dn)
                item = dict(e)
                item["depends_on"] = clean_deps
                normalized.append(item)
            result = {
                "thinking": thinking,
                "direct_answer": direct_answer,
                "info_request": info_request,
                "experts": normalized,
            }
            logger.debug(f"解析方案结果: thinking={thinking[:80]}..., "
                         f"has_info_request={info_request is not None}, "
                         f"has_direct_answer={bool(direct_answer)}, "
                         f"expert_count={len(normalized)}")
            return result
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"解析专家方案失败: {e}")
            return {"thinking": "", "direct_answer": "", "info_request": None, "experts": []}
