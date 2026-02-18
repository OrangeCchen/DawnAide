# DawnAide：AgentTeams 系统说明书

## 1. 系统定位与目标

`AgentTeams` 是一个多 Agent 协作平台 POC，核心目标是将用户任务自动转化为"团队协作流程"：

- 由 `team-lead` 统一分析任务并制定执行策略。
- 按任务复杂度动态生成 1~4 位专家并行执行。
- 支持 Round 1（独立分析）+ Round 2（协作讨论）+ 可选领域核查。
- 通过 WebSocket 将思考、流式输出和状态实时推送到前端。
- 联网搜索结果自动生成引用角标，最终汇总保留可溯源引用来源列表。
- 第一轮对话结束后（或用户手动终止后）自动生成 ≤10 字的会话标题。
- 支持会话持久化、场景模板、公文导出、iMessage 双向机器人等能力。

---

## 2. 总体架构

系统采用前后端分离开发、后端可托管前端静态资源的架构：

- **前端**：Vue 3 + TypeScript + Pinia + Vite（端口 `3000`）
- **后端**：FastAPI + WebSocket + asyncio（默认端口 `8000`）
- **模型层**：统一适配 `OpenAI / Spark / Ollama`
- **持久化**：SQLite（`data/agent_teams.db`）
- **配置数据**：YAML（角色、技能、方法论、场景）

运行时主链路：

1. 前端提交任务到 `POST /api/tasks`
2. 后端创建后台异步任务并交由 `Engine -> team-lead` 处理
3. `team-lead` 动态调度专家执行，结果通过 `MessageBus` 广播
4. `WebSocket /ws` 将消息流推送到前端，前端增量渲染消息卡片

---

## 3. 代码结构与模块说明

### 3.1 项目目录（核心部分）

```text
AgentTeams/
├── src/                          # 后端 Python 代码
│   ├── main.py                   # FastAPI 入口、路由注册、SPA 静态托管
│   ├── init.py                   # 系统初始化流程（注册表/引擎/DB/team-lead）
│   ├── config.py                 # 环境变量与全局配置
│   ├── api/
│   │   ├── routes.py             # REST API（teams/tasks/models/roles/...）
│   │   └── websocket.py          # WebSocket 连接管理与广播
│   ├── core/
│   │   ├── engine.py             # 引擎（Agent 注册与任务调度）
│   │   ├── task.py               # 任务与结果数据结构
│   │   ├── team.py               # 团队管理与持久化调用
│   │   └── message_bus.py        # 消息总线与历史管理
│   ├── agents/
│   │   ├── base.py               # Agent 基类（think/stream/message）
│   │   └── team_lead.py          # 协作编排核心（动态专家、核查、汇总）
│   ├── llm/
│   │   ├── factory.py            # LLM 工厂
│   │   ├── openai_adapter.py     # OpenAI 兼容适配
│   │   ├── spark_adapter.py      # Spark 适配
│   │   └── ollama_adapter.py     # Ollama 适配
│   ├── memory/
│   │   ├── memory_system.py      # 分区记忆系统
│   │   └── context_manager.py    # 上下文管理
│   ├── stores/
│   │   ├── role_registry.py      # 角色注册表（YAML）
│   │   ├── skill_registry.py     # 技能注册表（YAML + 触发机制）
│   │   ├── methodology_lib.py    # 方法论库（YAML）
│   │   └── scene_registry.py     # 场景模板注册表（YAML）
│   ├── storage/
│   │   └── database.py           # SQLite 异步持久化
│   ├── display/
│   │   └── hooks.py              # 消息展示 Hook
│   └── tools/                    # 外部能力封装
│       ├── web_search.py         # 联网搜索（DuckDuckGo，多级降级）
│       ├── web_reader.py         # 网页内容抓取与解析
│       ├── doc_exporter.py       # Markdown → Word 导出
│       ├── file_reader.py        # 本地文件/目录读取
│       ├── imessage.py           # iMessage 发送（macOS AppleScript）
│       └── imessage_bot.py       # iMessage 双向机器人（监听+回复）
├── frontend/                     # 前端 Vue 工程
│   ├── vite.config.ts            # 前端端口与 API/WS 代理配置
│   ├── src/
│   │   ├── App.vue               # 页面总布局
│   │   ├── api/websocket.ts      # WS 客户端与重连
│   │   ├── stores/teamStore.ts   # 团队、消息、流式状态管理
│   │   └── components/           # ChatArea / TeamSidebar / MessageCard 等组件
├── data/
│   ├── roles/                    # 角色定义 YAML
│   ├── skills/                   # 技能定义 YAML
│   ├── methodologies/            # 方法论 YAML
│   ├── scenes/                   # 场景模板 YAML
│   └── exports/                  # 导出的 Word 文档目录
├── .env.example                  # 环境变量模板
└── pyproject.toml                # 后端依赖与打包配置
```

### 3.2 后端核心模块职责

- `src/main.py`
  - 创建 FastAPI App、CORS、注册 REST/WS 路由。
  - 若 `frontend/dist` 存在，挂载 `/assets` 并提供 SPA catch-all。
  - 无前端构建产物时返回提示页。

- `src/init.py`
  - 启动阶段依次初始化：目录、显示 Hook、方法论/角色/技能/场景注册表、记忆系统、引擎、数据库、历史恢复、`team-lead`、iMessage Bot 待命监听。

- `src/core/engine.py`
  - 负责 Agent 注册与任务提交入口。
  - 按 `assigned_to` 找到对应 Agent 并调用执行。

- `src/agents/team_lead.py`
  - 系统最关键编排器：
  - 任务分析（可直接回答 / 请求补充信息 / 动态专家协作）。
  - 专家两轮协作 + 可选核查专家并行验证。
  - 最终报告流式输出、可选 iMessage 推送。
  - 自动会话重命名机制：
    - 触发时机：Round 1 完成后立即触发；任务正常完成后兜底触发；用户手动终止后也触发。
    - 优先用 LLM 生成 ≤10 字标题（参考用户首问 + 已有专家中间结果）。
    - LLM 失败时自动回退到本地截断用户首问前 10 字。
    - 仅对默认名称（以"新对话"开头）生效，已命名的不会重复触发。

- `src/core/message_bus.py`
  - 消息发布订阅中心，负责历史记录、DB 持久化、全局广播（供 WebSocket）。
  - 流式片段 `stream_chunk` 只广播不持久化；结束后更新最终消息内容。

- `src/storage/database.py`
  - SQLite 三张核心表：`teams`、`team_members`、`messages`。
  - 应用重启后恢复会话与消息历史。

- `src/llm/openai_adapter.py`
  - OpenAI 兼容 API 适配器，支持流式与非流式调用。
  - 自动检测 qwen3 系列模型并在非流式调用中注入 `enable_thinking: false`。

- `src/api/routes.py`
  - REST API 路由定义（团队/任务/模型/角色/场景/导出等）。
  - 任务提交后创建后台 `asyncio.Task` 并维护运行中任务映射。
  - 终止任务时取消对应 `asyncio.Task`，清理流式状态，并触发兜底重命名。

### 3.3 前端核心模块职责

- `frontend/src/components/ChatArea.vue`
  - 任务输入区、文件路径附加、审查开关、模型切换、终止任务按钮。
  - 调用 `POST /api/tasks` 提交任务，调用 `POST /api/teams/{id}/stop` 终止。

- `frontend/src/components/TeamSidebar.vue`
  - 会话列表展示与删除。
  - iMessage Bot 状态查询与开关（`/api/imessage-bot/*`）。

- `frontend/src/components/MessageCard.vue`
  - 消息渲染组件：Markdown 转 HTML、代码高亮、流式打字效果。
  - 引用角标渲染：将 `[N]` 转为可悬浮交互的引用卡片，显示标题与 URL。
  - 引用来源列表：当 `message.metadata.references` 存在时，在消息底部展示"📚 引用来源"。

- `frontend/src/stores/teamStore.ts`
  - 统一管理团队、当前会话、消息历史、Agent 列表、流式更新逻辑。
  - 处理 `stream_chunk` 增量追加与 `team_renamed` 系统事件（实时更新左侧会话标题）。

- `frontend/src/api/websocket.ts`
  - 建立 `/ws` 连接，自动重连，心跳 `ping/pong`。

---

## 4. 关键业务流程

### 4.1 应用启动流程

1. FastAPI 生命周期触发 `initialize_app()`
2. 加载 YAML 注册表（角色/技能/方法论/场景）
3. 初始化记忆系统、引擎、SQLite 连接
4. 恢复历史团队与消息
5. 创建并注册 `team-lead`
6. 尝试启动 iMessage Bot 待命监听（若已配置并授权）

### 4.2 任务协作流程

1. 前端 `POST /api/tasks` 提交任务
2. 后端将任务异步丢给 `team-lead`
3. `team-lead` 输出任务分析（流式）
4. 分支处理：
   - 信息不足：返回 `info_request`，等待用户补充
   - 任务简单：直接回答（可启用核查）
   - 任务复杂：动态专家多轮协作后汇总
5. 结果与状态经 MessageBus -> WebSocket 实时推送前端
6. Round 1 完成后自动重命名会话（≤10 字）
7. 用户手动终止时，也会触发自动重命名（优先 LLM，兜底本地截断）

### 4.3 联网搜索与引用机制

1. `team-lead` 在规划阶段为需要实时信息的专家标记 `needs_search: true` 并提供 `search_query`
2. 专家执行前自动调用 `web_search`，结果以带编号引用格式注入专家上下文
3. 搜索采用**多级降级**链路，按顺序尝试直到拿够结果：
   - 文本搜索 (cn-zh) → 文本搜索 (全球) → 新闻搜索 (cn-zh) → 新闻搜索 (全球)
4. 多专家场景下，每位专家分配独立引用编号区间（如 1-10、11-20），避免合并冲突
5. 专家输出中的 `[N]` 角标在最终汇总时保留，前端渲染为可交互的悬浮引用卡片
6. 最终消息的 `metadata.references` 存储完整引用来源列表，前端在消息底部展示"📚 引用来源"

### 4.4 用户终止任务流程

1. 前端调用 `POST /api/teams/{team_id}/stop`
2. 后端取消对应 `asyncio.Task`（最多等待 3 秒）
3. 清理所有残留的流式状态（标记 `streaming: false`）
4. 发送"对话已被用户终止"状态消息
5. 尝试自动重命名会话（优先 LLM 生成标题，失败则用用户首问前 10 字兜底）

### 4.5 自动会话重命名机制

系统会在以下时机尝试自动重命名默认名称的会话（以"新对话"开头的会话）：

| 触发时机 | 实现位置 | 命名策略 |
|---------|---------|---------|
| Round 1 完成后 | `team_lead.py` → `_auto_rename_team()` | LLM 生成（用户首问 + 专家中间结果） |
| 任务正常完成后 | `team_lead.py` → `_auto_rename_team()` | 同上（兜底，防 Round 1 时未成功） |
| 用户手动终止后 | `routes.py` → `_fallback_rename_team_after_stop()` | 先尝试 LLM，失败用本地截断 |

命名规则：
- 最多 10 个中文字符（或等量英文）
- 优先通过 LLM 概括核心主题
- LLM 失败时从用户首问中截取前 10 字
- 已有自定义名称的会话不会被覆盖

---

## 5. 配置说明

### 5.1 环境变量

系统使用根目录 `.env`，可从 `.env.example` 复制：

```bash
cp .env.example .env
```

关键配置项：

- `LLM_PROVIDER=openai|spark|ollama`
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL`
- `SPARK_APP_ID` / `SPARK_API_KEY` / `SPARK_API_SECRET`
- `OLLAMA_BASE_URL` / `OLLAMA_MODEL`
- `HOST` / `PORT` / `LOG_LEVEL`

可选能力（代码中有使用）：

- `REVIEWER_MODEL`：核查模型（为空时自动与主模型错开）
- `IMESSAGE_PUSH_TO`：iMessage 目标号码/Apple ID（用于 Bot 与推送能力）

### 5.2 模型兼容性说明

- **qwen3 系列模型**（如 `qwen3-32b`、`qwen3-235b-a22b` 等）默认开启"思考模式"（`enable_thinking`）。
  - 流式调用（`stream_chat`）：正常工作，无需额外处理。
  - 非流式调用（`chat`）：API 要求显式传入 `enable_thinking: false`，否则返回 400 错误。
  - 系统已在 `OpenAIAdapter.chat()` 中自动检测 qwen3 模型并注入该参数，无需手动配置。
- 其他模型（qwen-plus、qwen-max、gpt-4o 等）不受影响。

---

## 6. 技能说明

### 6.1 技能机制

系统技能定义位于 `data/skills/*.yaml`，由 `src/stores/skill_registry.py` 加载并按触发条件自动激活。

触发机制支持三类：

- `always`：始终启用
- `task_metadata`：当任务元数据存在指定键时启用（如 `file_paths`、`scene_type`）
- `expert_flag`：当任意专家带有指定标记时启用（如 `needs_search`、`needs_url_read`、`needs_imessage`）

技能类型（`category`）：

- `builtin`：系统内建能力（不依赖外部服务）
- `tool`：工具能力（调用外部资源/接口）
- `knowledge`：知识规范能力（通过 prompt 模板注入约束）

### 6.2 当前内置技能清单

- `time_awareness`（🕐 时间感知）
  - 分类：`builtin`
  - 触发：`always`
  - 作用：为任务提供当前时间上下文，增强时效性判断能力。

- `file_reading`（📎 文件读取）
  - 分类：`builtin`
  - 触发：`task_metadata.file_paths`
  - 作用：读取用户提交的本地文件/目录内容并拼接到任务上下文。

- `web_search`（🔍 联网搜索）
  - 分类：`tool`
  - 触发：`expert_flag.needs_search`
  - 作用：执行互联网检索，返回带引用编号的结果供专家分析。
  - 降级策略：文本搜索(cn-zh) → 文本搜索(全球) → 新闻搜索(cn-zh) → 新闻搜索(全球)，按 URL 去重合并。
  - 依赖：`ddgs`（DuckDuckGo Search，已写入 `pyproject.toml`）。

- `web_reading`（📄 网页读取）
  - 分类：`tool`
  - 触发：`expert_flag.needs_url_read`
  - 作用：抓取并解析 URL 正文，生成可溯源的网页内容上下文。
  - 依赖：`httpx`、`beautifulsoup4`（已写入 `pyproject.toml`）。

- `imessage`（💬 iMessage）
  - 分类：`tool`
  - 触发：`expert_flag.needs_imessage`
  - 作用：通过 Apple iMessage 向指定联系人发送消息，并回传发送结果。

- `official_document`（📜 公文写作规范）
  - 分类：`knowledge`
  - 触发：`task_metadata.scene_type`
  - 作用：注入 GB/T 9704 公文规范模板，约束标题、正文层级、语言与落款格式。

- `doc_export`（📝 Word 导出）
  - 分类：`tool`
  - 触发：用户在前端点击导出按钮时调用 `POST /api/export/word`
  - 作用：将 Markdown 内容转换为 `.docx` Word 文档并下载。
  - 依赖：`python-docx`（已写入 `pyproject.toml`）。

### 6.3 技能与执行链路关系

- `team-lead` 在任务分析阶段决定专家配置（如 `needs_search` 等标记）。
- `SkillRegistry` 根据任务元数据与专家标记解析本次激活技能。
- 工具类技能在专家执行阶段触发（搜索/网页读取/iMessage）。
- 知识类技能（如公文规范）通过 `prompt_template` 注入专家 system prompt，约束输出质量与格式。

### 6.4 如何新增一个技能（YAML 模板 + 触发规则示例）

#### 步骤 1：在 `data/skills` 新建技能文件

建议文件名：`<skill_name>.yaml`（例如 `api_debug.yaml`）。

通用 YAML 模板：

```yaml
name: api_debug
display_name: API 调试
icon: "🧪"
category: tool
description: 调试接口请求与响应，辅助定位联调问题
trigger:
  type: expert_flag
  key: needs_api_debug
prompt_template: |
  你是 API 调试专家，请关注：
  1. 请求参数完整性
  2. 返回码与错误信息
  3. 可复现的修复建议
parameters:
  - name: endpoint
    type: string
    required: false
```

字段建议：

- `name`：唯一标识，建议小写下划线
- `display_name`：前端展示名称
- `icon`：技能图标（可选）
- `category`：`builtin|tool|knowledge`
- `description`：技能用途
- `trigger`：触发规则
- `prompt_template`：知识型/规范型技能建议提供
- `parameters`：可选参数声明（当前主要用于说明）

#### 步骤 2：配置触发规则（3 种示例）

1) 始终启用（`always`）

```yaml
trigger:
  type: always
```

2) 基于任务元数据（`task_metadata`）

```yaml
trigger:
  type: task_metadata
  key: scene_type
```

说明：当 `task.metadata.scene_type` 存在且为真时激活。

3) 基于专家标记（`expert_flag`）

```yaml
trigger:
  type: expert_flag
  key: needs_search
```

说明：当任一专家规划结果包含 `needs_search: true` 时激活。

#### 步骤 3：让技能真正参与执行

- 若是工具型技能（`tool`）：
  - 需要在专家执行链路中有对应标记与处理逻辑（例如 `needs_search` -> 调用 `web_search`）。
- 若是知识型技能（`knowledge`）：
  - 在 `prompt_template` 中写清规则，系统会将其注入专家 system prompt。
- 若是内建技能（`builtin`）：
  - 通常依赖任务上下文拼接或系统默认能力。

#### 步骤 4：验证是否生效

1. 重启后端，确认日志显示"技能注册表已加载"。
2. 提交一条能触发该技能的任务。
3. 检查前端消息中的技能标签、状态提示和执行结果是否符合预期。
4. 必要时在 `team-lead` 规划输出中确认专家标记是否正确生成。

---

## 7. 前后端启动说明

### 7.1 开发模式（推荐）

需要两个终端分别启动后端与前端。

#### 后端启动

```bash
# 在项目根目录
# 1) 若 .venv 已损坏（例如指向不存在的 python3.13），先删除
rm -rf .venv

# 2) 使用 Python 3.11+ 创建虚拟环境（建议显式指定）
python3.12 -m venv .venv
source .venv/bin/activate

# 3) 确认版本满足要求（本项目 requires-python >= 3.11）
python -V

# 4) 安装依赖（会自动安装 pyproject.toml 中的所有依赖，含 ddgs/beautifulsoup4/python-docx 等）
pip install -e .
cp .env.example .env
# 编辑 .env，填入模型配置与 API Key

# 5) 启动后端
python -m src.main
# 或
uvicorn src.main:app --reload --port 8000
# 或（推荐：不依赖 shell 激活状态，最稳妥）
.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000
.venv/bin/uvicorn src.main:app --reload --port 8000
```

注意：

- 常见拼写错误是 `vicorn`（错误），正确命令是 `uvicorn`。
- 若仅需稳定运行，建议先用**不带 `--reload`**的命令排障：
  - `.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000`

后端可访问：

- API 文档：`http://localhost:8000/docs`
- REST 基础路径：`http://localhost:8000/api/*`
- WebSocket：`ws://localhost:8000/ws`

#### 前端启动

```bash
cd frontend
npm install
npm run dev
```

前端默认地址：`http://localhost:3000`

说明：`frontend/vite.config.ts` 已将 `/api` 与 `/ws` 代理到 `http://localhost:8000`。

### 7.2 一体化部署模式（后端托管前端静态资源）

```bash
cd frontend
npm install
npm run build

cd ..
python -m src.main
```

此时后端会托管 `frontend/dist`，通过后端端口统一访问（默认 `http://localhost:8000`）。

---

## 8. 主要接口清单（后端）

- 团队管理
  - `GET /api/teams`
  - `POST /api/teams`
  - `GET /api/teams/{team_id}`
  - `PATCH /api/teams/{team_id}`
  - `DELETE /api/teams/{team_id}`
  - `POST /api/teams/{team_id}/members`
  - `POST /api/teams/{team_id}/stop`

- 任务与消息
  - `POST /api/tasks`
  - `GET /api/teams/{team_id}/messages`

- 能力与配置
  - `GET /api/agents`
  - `GET /api/roles`
  - `POST /api/roles`
  - `GET /api/models`
  - `POST /api/models/switch`
  - `GET /api/scenes`
  - `POST /api/export/word`

- iMessage
  - `POST /api/imessage-bot/start`
  - `POST /api/imessage-bot/stop`
  - `GET /api/imessage-bot/status`

- 实时通道
  - `WS /ws`

---

## 9. 数据与持久化

- SQLite 数据库：`data/agent_teams.db`
- 消息策略：
  - 普通消息持久化（`messages` 表）
  - 流式片段不落库，仅实时推送
  - 流式结束后回写最终消息内容与统计信息
- YAML 数据：
  - `data/roles`：角色模板
  - `data/skills`：技能触发与标签定义
  - `data/methodologies`：方法论流程
  - `data/scenes`：场景表单与 prompt 模板

---

## 10. 常见问题与排查

- **前端页面可打开但请求失败**
  - 检查后端是否运行在 `8000`，以及前端代理配置是否改动。

- **后端能启动但模型调用失败**
  - 检查 `.env` 中 provider 与对应 API Key/URL/model 是否匹配。
  - 若使用 qwen3 系列模型，确认 `openai` 库版本 ≥1.60，以支持 `extra_body` 参数。

- **联网搜索返回 0 条结果**
  - 日志中出现 `No module named 'ddgs'`：说明依赖未安装，在 `.venv` 中执行 `pip install -e .` 即可（`ddgs` 已写入 `pyproject.toml`）。
  - 日志中出现 `panicked at system-configuration`：macOS 环境下 `ddgs` 底层库偶发崩溃，重试通常可恢复。
  - 搜索正常但结果不准：检查 `search_query` 是否合理，可在后端日志中搜索 `[搜索]` 查看实际请求与返回条数。

- **最终汇总缺少引用角标和来源列表**
  - 若搜索返回 0 条，则 `references` 为空，前端不会渲染引用。先排查搜索是否正常工作（见上条）。
  - 若搜索正常但汇总没角标：检查专家输出中是否使用了 `[N]` 角标，以及汇总 prompt 是否包含引用指令。

- **自动会话重命名不生效**
  - 日志中出现 `enable_thinking must be set to false`：说明 qwen3 模型兼容未生效，确认 `src/llm/openai_adapter.py` 已包含 `_is_thinking_model()` 检测。
  - 日志中出现 `自动重命名对话失败` 但无后续兜底重命名：检查 `routes.py` 中取消任务分支是否包含 `_fallback_rename_team_after_stop` 调用。
  - 会话已有名称（非"新对话…"开头）：系统只对默认名称重命名，已命名的不会重复触发。

- **看不到流式输出**
  - 检查浏览器 WS 连接是否成功（`/ws`）。
  - 确认后端日志中无 WebSocket 断连异常。

- **Word 导出失败**
  - 日志中出现 `No module named 'docx'`：说明 `python-docx` 未安装，在 `.venv` 中执行 `pip install -e .` 即可。

- **iMessage Bot 不工作**
  - 仅 macOS 可用。
  - 需配置 `IMESSAGE_PUSH_TO`。
  - 需给终端/应用授予读取 Messages 数据库的权限（全磁盘访问）。

- **依赖安装通用问题**
  - 本项目所有 Python 依赖（含工具模块所需的 `ddgs`、`beautifulsoup4`、`python-docx`）均已声明在 `pyproject.toml` 中。
  - 首次安装或重建虚拟环境后，执行一次 `pip install -e .` 即可安装全部依赖，无需逐个手动安装。
  - 若 pip 遇到 SSL 证书错误，可加 `--trusted-host pypi.org --trusted-host files.pythonhosted.org` 参数。

---

## 11. 建议的最小验证步骤

1. 启动后端，访问 `http://localhost:8000/docs` 确认 API 正常。
2. 启动前端，创建新对话并提交简单任务（如"介绍下系统功能"）。
3. 观察是否出现实时流式消息与状态更新。
4. 提交一条需要联网搜索的任务（如"2026年春晚时间"），确认：
   - 后端日志显示搜索返回 >0 条结果。
   - 最终汇总中出现可交互的引用角标和"📚 引用来源"列表。
5. 第一轮完成后，观察左侧会话列表标题是否从"新对话…"自动更新为 ≤10 字的主题标题。
6. 新建对话并提交任务，在执行中途点击"终止"按钮，确认对话被终止后会话标题仍然自动更新。
7. 开启"审查"开关再提交一次任务，确认核查链路生效。
8. 可选：提交含 `file_paths` 的任务验证文件读取链路。
9. 可选：在场景面板提交公文写作任务，点击导出 Word 按钮验证导出功能。

---

## 12. 依赖管理

所有 Python 依赖均声明在项目根目录 `pyproject.toml` 的 `dependencies` 中：

| 依赖包 | 用途 | 使用模块 |
|--------|------|---------|
| `fastapi` | Web 框架 | `src/api/*`, `src/main.py` |
| `uvicorn[standard]` | ASGI 服务器 | 启动命令 |
| `websockets` | WebSocket 协议 | `src/api/websocket.py` |
| `pydantic` / `pydantic-settings` | 数据校验与配置 | 全局 |
| `httpx` | 异步 HTTP 客户端 | `src/tools/web_reader.py` |
| `pyyaml` | YAML 解析 | `src/stores/*` |
| `python-dotenv` | 环境变量加载 | `src/config.py` |
| `loguru` | 日志 | 全局 |
| `openai` | LLM API 调用 | `src/llm/openai_adapter.py` |
| `tiktoken` | Token 计数 | `src/llm/openai_adapter.py` |
| `aiosqlite` | 异步 SQLite | `src/storage/database.py` |
| `jinja2` | 模板渲染 | 场景 prompt 模板 |
| `markdown` | Markdown 处理 | 导出等 |
| `ddgs` | DuckDuckGo 搜索 | `src/tools/web_search.py` |
| `beautifulsoup4` | HTML 解析 | `src/tools/web_reader.py` |
| `python-docx` | Word 文档生成 | `src/tools/doc_exporter.py` |

首次安装或重建虚拟环境后，只需执行一次：

```bash
pip install -e .
```

即可安装全部依赖，**无需逐个手动安装**。后续新增依赖时，应同步更新 `pyproject.toml`，然后再次执行 `pip install -e .`。
