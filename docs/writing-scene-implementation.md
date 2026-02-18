# 写作场景落地方案 — 三轮深度思考

> 基于 AgentTeams 现有架构（技能注册表、角色库、方法论库、信息卡片机制），规划写作场景的完整实现路径。

---

## 第一轮思考：用户故事走查 — 一个文员写会议通知的全过程

### 1.1 先忘掉技术，只看用户

张琳是某机关办公室的文员。领导说："下周三开个全体干部会，你发个通知。"

她的工作流程是：
1. 打开 Word，从上次的通知模板复制一份
2. 改时间、改地点、改参会人
3. 纠结措辞：是"请各部门负责人"还是"请各部门主要负责同志"？
4. 确认格式：主送、抄送写不写？落款日期用阿拉伯数字还是汉字？
5. 找领导审批，被退回来改两次
6. 最终定稿，打印分发

**痛点在哪？**

| 步骤 | 痛点 | 严重程度 |
|---|---|---|
| 1. 找模板 | 上次的模板在哪个文件夹？格式对不对？ | 中 |
| 2. 填内容 | 简单替换，不痛 | 低 |
| 3. 措辞 | 这是最花时间的——反复斟酌、百度搜范文 | **高** |
| 4. 格式 | 公文格式规范记不全 | **高** |
| 5. 审批 | 被退回改措辞/格式，返工成本大 | **高** |
| 6. 定稿 | 简单操作 | 低 |

**核心洞察：** 痛点集中在"措辞 + 格式 + 返工"。如果系统能一次性输出一篇格式正确、措辞得体的通知，用户只需要提供事实信息（时间、地点、人员），就能大幅减少返工。

### 1.2 理想的用户旅程

```
张琳打开 AgentTeams
    │
    ▼
看到首页的场景卡片，点击 [📝 公文写作]
    │
    ▼
展开子类型：[ 会议通知 ] [ 工作方案 ] [ 请示报告 ] [ 述职总结 ] ...
    │
    ▼
点击 [会议通知]
    │
    ▼
弹出信息收集表单（预定义的字段）：
  ┌───────────────────────────────┐
  │ 会议名称：[                   ]│
  │ 会议时间：[                   ]│
  │ 会议地点：[                   ]│
  │ 主持人：  [                   ]│
  │ 参会人员：[                   ]│
  │ 会议议题：[                   ]│
  │ 参会要求：[                   ]│
  │ 发文单位：[                   ]│
  │ 语气风格：[ 正式严谨 ] [ 简洁明快 ]│
  │                               │
  │        [ 生成通知 ]            │
  └───────────────────────────────┘
    │
    ▼
系统分配专家：公文格式专家 + 内容撰写专家
    │
    ▼
30 秒后输出一篇格式规范的会议通知
    │
    ▼
张琳看完后：
  - 满意 → 点击 [复制] 或 [导出 Word]
  - 不满意 → 在下方输入"把参会要求改成更强调纪律" → 系统基于原文修改
```

### 1.3 关键决策点

走完这个旅程，暴露了几个必须回答的问题：

**Q1：场景入口放在哪里？**
- 方案 A：替换当前的空白状态提示（`ChatArea.vue` 中的 `exampleTasks`）
- 方案 B：新增一个独立的"场景选择"面板
- **倾向 A**：不增加新页面，在现有界面的空白区域展示场景卡片，点击后自动填入结构化的提问。用户的心智模型保持一致——始终是"在聊天框发消息"。

**Q2：信息收集走 info_request 还是前端直接生成？**
- 方案 A：前端点击场景后直接展示表单，填完后拼成文字发给后端
- 方案 B：前端发一个特殊标记的任务，后端走 info_request 流程
- **倾向 A**：前端直接展示更快、更确定。info_request 适合"AI 判断后决定问什么"的场景，而场景模板的字段是预定义的，不需要 AI 判断。

**Q3：专家组合是固定的还是动态的？**
- 方案 A：写作类任务固定分配"格式专家 + 内容专家"
- 方案 B：仍然让 team-lead 动态决定
- **倾向 B + 引导**：保持动态，但在 prompt 中对写作场景提供更强的引导，确保分配合理。因为不同写作任务差异很大（通知 vs 述职报告 vs 调研方案），固定搭配会不够灵活。

**Q4：公文格式规范从哪里来？**
- 方案 A：直接写在 prompt 里
- 方案 B：作为"方法论"加载到系统（`data/methodologies/`）
- 方案 C：作为"技能"的 prompt_template 注入
- **倾向 B**：方法论库正好适合这个用途。一个"公文写作方法论"定义步骤和格式规范，team-lead 在分配写作任务时自动引用。当前方法论库只有 `code_review_flow`，正好可以扩展。

### 1.4 第一轮结论

> 写作场景的本质是：**结构化信息收集 → 格式规范注入 → 多角色协作 → 可迭代输出**。现有系统的四大基础设施（信息卡片、方法论库、专家动态创建、流式输出）已经覆盖了 80% 的需求，剩下 20% 是"场景入口"和"写作专项知识"的补充。

---

## 第二轮思考：现有架构的复用与缺口分析

### 2.1 逐模块审视

#### 模块 1：技能注册表（`data/skills/*.yaml`）

**现状：** 5 个技能（时间感知、联网搜索、网页读取、文件读取、iMessage），全部是"工具类"技能。

**写作场景需要什么技能？**

| 技能 | 是否已有 | 说明 |
|---|---|---|
| 时间感知 | ✅ | 写通知需要知道当前日期 |
| 联网搜索 | ✅ | 搜索范文/格式参考（可选） |
| **公文格式规范** | ❌ | 各类公文的标准格式 |
| **写作风格库** | ❌ | 不同语气/风格的写作要求 |

**思考：** "公文格式规范"不是一个"工具"——它不需要调用外部 API，它是一组**知识**。它更像是一个 `prompt_template`，在专家执行写作任务时自动注入。

**SkillDefinition 的 `prompt_template` 字段正好可以承载这种知识！** 现有代码中这个字段存在但未被实际使用。如果让技能的 `prompt_template` 在专家执行时自动注入到 system prompt 中，就能实现"知识注入"。

这意味着我们可以创建一种新类型的技能——**知识型技能**（`category: knowledge`），与现有的工具型技能（`category: tool`）区分：

```yaml
# data/skills/official_document.yaml
name: official_document
display_name: 公文写作规范
icon: "📜"
category: knowledge
description: 中国机关公文写作的格式规范和常用模板
trigger:
  type: task_metadata
  key: scene_type
  value: official_document
prompt_template: |
  你需要遵循以下公文写作规范：
  
  一、格式要求
  - 标题：居中，二号方正小标宋体
  - 主送机关：顶格写，后加冒号
  - 正文：首行缩进2字符，三号仿宋
  - 落款：右对齐，单位名称 + 日期
  ...
  
  二、常见公文类型模板
  ### 会议通知
  标题格式：关于召开XXX会议的通知
  正文结构：
  1. 会议目的和背景（1-2句）
  2. 会议基本信息（时间、地点、参会人）
  3. 会议议程（如有）
  4. 参会要求（着装、材料准备等）
  5. 联系方式
  落款：发文单位 + 年月日
  
  ### 工作方案
  ...
```

**但存在一个缺口：** 当前 `_run_expert` 方法在构建专家的 system prompt 时，没有注入技能的 `prompt_template`。需要增加这个连接。

#### 模块 2：角色库（`data/roles/*.yaml`）

**现状：** 7 个角色，其中 `writer.yaml` 是通用的文案专家。

**问题：** `writer.yaml` 的 system_prompt 太通用了：

```
你是一名资深文案专家。你的职责是：
1. 根据需求撰写高质量文案
2. 优化和润色已有文本
...
```

这个 prompt 对"写朋友圈"和"写机关通知"是一样的，没有场景差异化。

**思考：** 角色库的定位应该是"可被 team-lead 参考的模板"，而不是直接使用的。当前 team-lead 是动态创建专家的（完全由 LLM 决定 persona 和 task），角色库的内容并没有被实际注入到动态专家中。

**两个方向：**
1. 让 team-lead 在创建写作类专家时，自动参考 `writer.yaml` 的 system_prompt → 需要修改 team_lead.py 的专家创建逻辑
2. 不改角色库的使用方式，而是通过方法论 + 技能注入写作知识 → 更轻量

**倾向方向 2：** 角色库保持"参考模板"的定位，写作场景的知识通过技能（prompt_template）和方法论（steps）注入。这样不需要改 team-lead 的核心逻辑。

#### 模块 3：方法论库（`data/methodologies/*.yaml`）

**现状：** 1 个方法论（`code_review_flow`），**且未被实际使用**。

`MethodologyLibrary` 在 `__init__.py` 中被加载了，但 `team_lead.py` 并没有引用它。方法论只是静静地躺在注册表里。

**这是一个关键缺口。** 方法论库是最适合承载"写作流程"的地方，但它需要被激活——让 team-lead 在执行写作任务时能读取对应的方法论。

**写作方法论设计：**

```yaml
# data/methodologies/official_writing_flow.yaml
name: official_writing_flow
display_name: 公文写作流程
description: 标准的公文写作方法论，确保格式规范、内容得体
steps:
  - name: requirement_analysis
    description: 分析写作需求：文体类型、受众、语气、核心要传达的信息
  - name: structure_design
    description: 根据文体类型确定文档结构（标题、主送、正文分段、落款）
  - name: content_drafting
    description: 按结构逐段撰写内容，注意措辞的正式性和准确性
  - name: format_review
    description: 检查公文格式是否符合规范（标题、字体、段落格式要求）
  - name: language_polish
    description: 润色语言，确保简洁明快、无歧义、符合机关发文习惯
applicable_roles:
  - team-lead
  - writer
```

**但方法论怎么注入到 team-lead 的执行流程中？** 这需要在 `execute_task` 中增加一步：根据任务类型匹配方法论，将方法论的 steps 作为上下文传递给专家。

#### 模块 4：信息卡片机制

**现状：** 可用，但触发方式是"AI 判断后决定问什么"。

**写作场景的需求：** 用户点击"会议通知"后，**立即**展示预定义的信息收集表单，不需要 AI 判断。

**关键区别：**
- 当前 info_request：用户输入模糊描述 → AI 分析缺什么 → 发 info_request
- 场景模板：用户选择场景 → 前端直接展示表单 → 用户填写 → 拼成描述发送

**这意味着需要一个新机制 — "场景模板"：** 不经过 AI 判断，由前端直接驱动。

#### 模块 5：前端（ChatArea.vue）

**现状：** 空白状态显示 `exampleTasks`，这是最自然的场景入口位置。

当前代码中的 example tasks：

```typescript
// ChatArea.vue 中（推测）
const exampleTasks = [
  '分析一下当前AI Agent的发展趋势',
  '帮我写一篇关于...的文章',
  ...
]
```

**改造方向：** 将 `exampleTasks` 升级为场景卡片系统：

```typescript
const sceneTemplates = [
  {
    id: 'official_writing',
    name: '公文写作',
    icon: '📝',
    children: [
      {
        id: 'meeting_notice',
        name: '会议通知',
        fields: [
          { id: 'meeting_name', label: '会议名称', type: 'text', required: true },
          { id: 'meeting_time', label: '会议时间', type: 'text', required: true },
          ...
        ],
        promptTemplate: '请撰写一篇会议通知。\n会议名称：{meeting_name}\n...'
      },
      { id: 'work_plan', name: '工作方案', ... },
      ...
    ]
  },
  { id: 'research', name: '调研分析', icon: '📊', ... },
  ...
]
```

**这些数据放在哪里？**
- 方案 A：写在前端代码里（简单，但改一个字段要改代码）
- 方案 B：放在 `data/scenes/*.yaml` 里，后端提供 API，前端读取（灵活）
- **倾向 B**：与现有的 `data/` 配置文件体系一致，可以随时增删场景而不需要重新部署前端。

### 2.2 缺口汇总

| 缺口 | 描述 | 影响范围 | 工作量 |
|---|---|---|---|
| **场景模板系统** | 前端展示 + 后端提供 API + YAML 配置 | 新增 | 中 |
| **方法论激活** | team-lead 根据任务类型加载方法论 | 修改 team_lead.py | 小 |
| **知识型技能注入** | 专家执行时注入 prompt_template | 修改 team_lead.py | 小 |
| **公文知识库** | 公文格式规范、常用模板 | 新增 YAML | 中（内容编写） |
| **迭代修改** | 基于上一次结果继续优化 | 修改前后端 | 中 |
| **复制/导出** | 一键复制、导出 Word | 前端 + 后端 | 小 |

### 2.3 第二轮结论

> 现有架构的三大注册表（技能、角色、方法论）提供了很好的扩展点，但**方法论库和技能的 prompt_template 当前没有被实际使用**，这是最大的"睡眠资产"。激活它们比新建模块更有价值。写作场景的落地路径：**场景模板（新增）→ 方法论激活（唤醒）→ 知识技能注入（唤醒）→ 迭代修改（新增）→ 导出（新增）**。

---

## 第三轮思考：实现蓝图 — 具体到文件和数据结构

### 3.1 总体架构变化

```
用户点击场景卡片
    │
    ├─── 前端: ScenePanel 组件（新增）
    │     ↓ 
    │    GET /api/scenes → 加载场景模板
    │     ↓ 
    │    展示场景卡片 → 用户选子类型 → 展示表单 → 用户填写
    │     ↓
    │    拼成结构化描述 + scene_type 元数据
    │     ↓
    │    POST /api/tasks { description, metadata: { scene_type: "meeting_notice" } }
    │
    ├─── 后端: team_lead.py
    │     ↓
    │    execute_task 收到带 scene_type 的任务
    │     ↓
    │    根据 scene_type 加载对应方法论（writing_flow）
    │     ↓
    │    方法论的 steps 注入到规划 prompt 中
    │     ↓
    │    LLM 输出专家分配方案
    │     ↓
    │    _run_expert 时，检查活跃技能的 prompt_template
    │     ↓
    │    知识型技能的 prompt_template 注入到专家的 system prompt
    │     ↓
    │    专家在"公文格式规范"指导下完成写作
    │
    └─── 输出: 格式规范的公文
          ↓
         用户满意 → 复制/导出
         用户不满意 → 输入修改意见 → 携带上下文重新生成
```

### 3.2 需要新增的文件

#### 文件 1：`data/scenes/official_writing.yaml` — 场景模板

```yaml
name: official_writing
display_name: 公文写作
icon: "📝"
description: 各类机关公文、通知、方案的撰写
methodology: official_writing_flow  # 关联方法论
children:
  - id: meeting_notice
    name: 会议通知
    description: 单位内部或跨部门的会议通知
    fields:
      - id: meeting_name
        label: 会议名称/主题
        type: text
        placeholder: "如：2026年度工作总结会"
        required: true
      - id: meeting_time
        label: 会议时间
        type: text
        placeholder: "如：2026年3月15日（周日）上午9:00"
        required: true
      - id: meeting_place
        label: 会议地点
        type: text
        placeholder: "如：三楼大会议室"
        required: true
      - id: host
        label: 主持人
        type: text
        placeholder: "如：张副局长"
        required: false
      - id: attendees
        label: 参会人员
        type: text
        placeholder: "如：各科室负责人及以上干部"
        required: true
      - id: agenda
        label: 会议议题/议程
        type: text
        placeholder: "如：1. 听取各科室年度工作汇报 2. 部署下一年重点工作"
        required: false
      - id: requirements
        label: 参会要求
        type: text
        placeholder: "如：请准时参会，不得无故缺席；请提前准备发言材料"
        required: false
      - id: organizer
        label: 发文单位
        type: text
        placeholder: "如：办公室"
        required: false
      - id: tone
        label: 语气风格
        type: select
        options: ["正式严谨", "简洁明快", "亲和友好"]
        required: false
    prompt_template: |
      请撰写一篇规范的会议通知。
      
      会议名称：{meeting_name}
      会议时间：{meeting_time}
      会议地点：{meeting_place}
      主持人：{host}
      参会人员：{attendees}
      会议议题：{agenda}
      参会要求：{requirements}
      发文单位：{organizer}
      语气风格：{tone}
      
      请严格按照机关公文格式输出，包含标题、主送、正文、落款。

  - id: work_summary
    name: 工作总结
    description: 年度/季度/月度工作总结
    fields:
      - id: period
        label: 总结时段
        type: select
        options: ["年度总结", "半年总结", "季度总结", "月度总结"]
        required: true
      - id: department
        label: 部门/个人
        type: text
        placeholder: "如：综合管理科 / 张三"
        required: true
      - id: key_work
        label: 主要工作内容（要点）
        type: text
        placeholder: "用逗号分隔主要工作，如：完成XX项目验收, 组织XX次培训, 推进XX制度建设"
        required: true
      - id: achievements
        label: 主要成绩/亮点
        type: text
        placeholder: "如：项目获省级表彰, 经费节约30%"
        required: false
      - id: problems
        label: 存在的问题
        type: text
        placeholder: "如：人手不足, 信息化水平待提升"
        required: false
      - id: next_plan
        label: 下一步计划
        type: text
        placeholder: "如：推进数字化转型, 加强人才引进"
        required: false
      - id: tone
        label: 语气风格
        type: select
        options: ["正式客观", "突出成绩", "务实反思"]
        required: false
    prompt_template: |
      请撰写一篇{period}工作总结。
      
      部门/个人：{department}
      主要工作：{key_work}
      主要成绩：{achievements}
      存在问题：{problems}
      下一步计划：{next_plan}
      语气风格：{tone}

  - id: request_report
    name: 请示报告
    description: 向上级请示批准某事项
    fields:
      - id: to_unit
        label: 上级单位
        type: text
        placeholder: "如：市教育局"
        required: true
      - id: subject
        label: 请示事项
        type: text
        placeholder: "如：关于申请增加编制的请示"
        required: true
      - id: reason
        label: 请示原因/背景
        type: text
        placeholder: "简述为什么需要请示这件事"
        required: true
      - id: proposal
        label: 具体方案/请求
        type: text
        placeholder: "如：拟增加3个编制，用于..."
        required: true
      - id: from_unit
        label: 发文单位
        type: text
        placeholder: "如：XX区教育局"
        required: true
    prompt_template: |
      请撰写一份请示报告。
      
      上级单位：{to_unit}
      请示事项：{subject}
      原因背景：{reason}
      具体方案：{proposal}
      发文单位：{from_unit}

  - id: speech_draft
    name: 发言稿/讲话稿
    description: 会议发言、领导讲话等
    fields:
      - id: occasion
        label: 发言场合
        type: text
        placeholder: "如：年度表彰大会、新员工入职仪式"
        required: true
      - id: speaker
        label: 发言人身份
        type: text
        placeholder: "如：局长、科长、项目负责人"
        required: true
      - id: audience
        label: 听众
        type: text
        placeholder: "如：全体干部职工、新入职员工"
        required: true
      - id: key_points
        label: 核心要点
        type: text
        placeholder: "用逗号分隔，如：回顾成绩, 指出不足, 部署重点, 提出期望"
        required: true
      - id: duration
        label: 发言时长
        type: select
        options: ["5分钟（约800字）", "10分钟（约1500字）", "15分钟（约2500字）", "20分钟（约3500字）"]
        required: false
      - id: tone
        label: 语气风格
        type: select
        options: ["激励鼓舞", "严肃郑重", "亲切温暖", "务实简练"]
        required: false
    prompt_template: |
      请撰写一篇发言稿。
      
      发言场合：{occasion}
      发言人：{speaker}
      听众：{audience}
      核心要点：{key_points}
      时长要求：{duration}
      语气风格：{tone}
```

#### 文件 2：`data/scenes/daily_writing.yaml` — 日常写作场景

```yaml
name: daily_writing
display_name: 日常写作
icon: "✍️"
description: 邮件、汇报、简报等日常文书
children:
  - id: email_draft
    name: 正式邮件
    description: 工作邮件、商务邮件
    fields:
      - id: recipient
        label: 收件人
        type: text
        placeholder: "如：客户张总、合作方李经理"
        required: true
      - id: purpose
        label: 邮件目的
        type: select
        options: ["通知告知", "请求协助", "回复确认", "致谢感谢", "催办提醒", "其他"]
        required: true
      - id: content
        label: 核心内容
        type: text
        placeholder: "简述邮件要表达的主要信息"
        required: true
      - id: tone
        label: 语气
        type: select
        options: ["正式商务", "友好亲切", "简洁直接", "委婉客气"]
        required: false
    prompt_template: |
      请撰写一封正式邮件。
      收件人：{recipient}
      邮件目的：{purpose}
      核心内容：{content}
      语气要求：{tone}

  - id: weekly_report
    name: 周报
    description: 工作周报
    fields:
      - id: week_range
        label: 本周时间范围
        type: text
        placeholder: "如：2月10日-2月14日"
        required: true
      - id: completed
        label: 本周完成的工作
        type: text
        placeholder: "逗号分隔，如：完成XX方案初稿, 参加XX会议, 对接XX供应商"
        required: true
      - id: in_progress
        label: 进行中的工作
        type: text
        placeholder: "如：XX项目招标中, XX系统测试阶段"
        required: false
      - id: next_week
        label: 下周计划
        type: text
        placeholder: "如：完成XX方案定稿, 启动XX项目"
        required: false
      - id: problems
        label: 需协调的问题
        type: text
        placeholder: "如：XX预算待审批, 需要XX部门配合"
        required: false
    prompt_template: |
      请撰写一份工作周报。
      
      时间范围：{week_range}
      本周完成：{completed}
      进行中：{in_progress}
      下周计划：{next_week}
      需协调问题：{problems}
```

#### 文件 3：`data/methodologies/official_writing_flow.yaml` — 写作方法论

```yaml
name: official_writing_flow
display_name: 公文写作流程
description: 标准的公文写作方法论，确保格式规范、语言得体、内容完整
steps:
  - name: requirement_analysis
    description: |
      分析写作需求：
      1. 确定文体类型（通知、请示、报告、总结、方案等）
      2. 明确受众和用途
      3. 确认核心要传达的信息
      4. 检查必要信息是否完整
  - name: structure_design
    description: |
      根据文体类型设计文档结构：
      - 通知：标题 → 主送 → 目的/背景 → 具体事项 → 要求 → 落款
      - 请示：标题 → 主送 → 原因 → 事项 → 方案 → 请批语 → 落款
      - 总结：标题 → 概述 → 主要工作 → 成绩/问题 → 计划 → 落款
      - 方案：标题 → 背景 → 目标 → 措施 → 保障 → 落款
  - name: content_drafting
    description: |
      按结构逐段撰写：
      - 首段简洁明了，直入主题
      - 中间段逻辑清晰，层次分明
      - 使用"一、二、三"或"（一）（二）（三）"分点
      - 措辞正式、准确、不带感情色彩
  - name: format_check
    description: |
      检查公文格式规范：
      - 标题：事由+文种（如"关于XXX的通知"）
      - 主送机关：顶格写，后加冒号
      - 正文：首行缩进两个字符
      - 落款：发文机关 + 成文日期（年月日用阿拉伯数字）
      - 附件：如有附件，在正文下空一行注明
  - name: language_polish
    description: |
      语言润色要点：
      - 删除口语化表达，替换为书面语
      - 检查"的地得"使用是否正确
      - 避免长难句，一句话一个意思
      - 公文惯用语：兹、特此、为、拟、现将
applicable_roles:
  - team-lead
  - writer
```

#### 文件 4：`data/skills/official_document.yaml` — 知识型技能

```yaml
name: official_document
display_name: 公文写作规范
icon: "📜"
category: knowledge
description: 中国机关公文写作的格式规范和语言要求
trigger:
  type: task_metadata
  key: scene_type
prompt_template: |
  === 公文写作规范（必须遵守）===
  
  一、标题规范
  - 发文机关 + 事由 + 文种，如"XX局关于召开年度总结会的通知"
  - 可省略发文机关，如"关于召开年度总结会的通知"
  
  二、正文规范
  - 开头：简述目的/依据，如"为进一步加强..."、"根据上级指示精神..."
  - 主体：条理分明，使用"一、""（一）""1.""（1）"四级标题
  - 结语：根据文种选用"特此通知"、"妥否，请批示"、"以上报告，请审阅"等
  
  三、语言要求
  - 使用第三人称和被动句式
  - 数字：正文中用汉字（如"三个方面"），数据用阿拉伯数字（如"增长15%"）
  - 时间表述：年月日用阿拉伯数字（如"2026年3月15日"）
  - 避免口语化：不用"我觉得"、"大家"，改用"我单位"、"全体干部职工"
  
  四、落款规范
  - 发文机关全称或规范简称
  - 成文日期：年月日用阿拉伯数字，右对齐
```

### 3.3 需要修改的文件

#### 修改 1：后端 — 场景模板 API

**新增文件：** `src/stores/scene_registry.py`

**作用：** 加载 `data/scenes/*.yaml`，提供 API 接口。

**数据结构：**
```python
@dataclass
class SceneField:
    id: str
    label: str
    type: str  # text / select / multiselect
    placeholder: str = ""
    required: bool = False
    options: list[str] = field(default_factory=list)

@dataclass
class SceneTemplate:
    id: str
    name: str
    description: str = ""
    fields: list[SceneField] = field(default_factory=list)
    prompt_template: str = ""

@dataclass
class SceneCategory:
    name: str
    display_name: str
    icon: str
    description: str
    methodology: str = ""  # 关联的方法论名称
    children: list[SceneTemplate] = field(default_factory=list)
```

**API 端点：**
- `GET /api/scenes` → 返回所有场景分类和模板
- 前端请求一次后缓存

#### 修改 2：后端 — 激活方法论

**文件：** `src/agents/team_lead.py`

**改动点：** 在 `execute_task` 中，当 task.metadata 包含 `scene_type` 时：

1. 从场景注册表找到对应的 `methodology` 名称
2. 从方法论库加载该方法论的 steps
3. 将 steps 注入到规划阶段的 prompt 中

```python
# 伪代码
scene_type = task.metadata.get("scene_type")
if scene_type:
    scene = scene_registry.get(scene_type)
    if scene and scene.methodology:
        methodology = methodology_lib.get(scene.methodology)
        if methodology:
            steps_text = "\n".join(f"- {s['name']}: {s['description']}" for s in methodology.steps)
            # 注入到 _stream_plan 的 prompt 中
```

#### 修改 3：后端 — 知识技能注入专家

**文件：** `src/agents/team_lead.py` 的 `_run_expert` 方法

**改动点：** 在构建专家的 system prompt 时，查找活跃的知识型技能，将 `prompt_template` 追加到 system prompt 中。

```python
# 伪代码 — 在 _run_expert 中
active_skills = skill_registry.resolve_active_skills(task_metadata=task.metadata)
knowledge_prompts = [
    s.prompt_template for s in active_skills
    if s.category == "knowledge" and s.prompt_template
]
if knowledge_prompts:
    expert_system_prompt += "\n\n" + "\n".join(knowledge_prompts)
```

#### 修改 4：前端 — 场景面板组件

**新增文件：** `frontend/src/components/ScenePanel.vue`

**渲染逻辑：**
1. 组件挂载时 `GET /api/scenes` 获取场景数据
2. 渲染场景卡片网格（icon + name + description）
3. 点击卡片展开子类型列表
4. 选择子类型后展示表单（复用 info_request 的字段渲染逻辑）
5. 用户填写表单后，拼接 `prompt_template` + 字段值，发送任务

**在 ChatArea.vue 中的集成：**
- 当前消息列表为空时（空白状态），替代 `exampleTasks` 展示 `ScenePanel`
- 用户发送任务后，ScenePanel 隐藏，恢复正常聊天界面

#### 修改 5：前端 — 复制按钮

**文件：** `frontend/src/components/MessageCard.vue`

**改动点：** 在 `isFinalAnswer` 为 true 的消息卡片右上角增加复制按钮：

```html
<button @click="copyContent('text')">📋 复制文本</button>
<button @click="copyContent('markdown')">📝 复制 Markdown</button>
```

使用 `navigator.clipboard.writeText()` API。

### 3.4 实现优先级

分三步走，每步独立可验证：

**Step 1：最小可用版本（MVP）— 不改后端核心逻辑**

只做前端场景面板 + prompt 拼接，验证"结构化收集 → 好结果"的核心假设：

1. 创建 `data/scenes/official_writing.yaml`（场景模板数据）
2. 后端增加 `GET /api/scenes` 接口（简单的文件读取）
3. 前端新增 `ScenePanel.vue`（卡片 + 表单 + prompt 拼接）
4. 前端 `ChatArea.vue` 集成场景面板
5. 前端 `MessageCard.vue` 增加复制按钮

**效果：** 用户能通过卡片入口发起写作任务，系统通过更精准的 prompt 产出更好的结果。

**Step 2：知识注入 — 激活睡眠资产**

让方法论和知识技能真正生效：

1. 创建 `data/methodologies/official_writing_flow.yaml`（写作方法论）
2. 创建 `data/skills/official_document.yaml`（公文知识技能）
3. 修改 `team_lead.py` — 加载方法论注入规划 prompt
4. 修改 `team_lead.py` — `_run_expert` 注入知识型技能的 prompt_template

**效果：** 专家在公文格式规范的指导下写作，输出质量显著提升。

**Step 3：体验闭环 — 迭代修改**

让用户能基于结果继续优化：

1. 前端最终回答下方增加"继续优化"输入区域
2. 后端支持携带上下文的追问（task.metadata 携带上一次的回答）
3. team-lead 识别"修改任务"，不重新分配专家，直接基于原文修改

**效果：** 用户完整的工作流闭环——从需求收集到反复打磨到最终交付。

### 3.5 验证清单

每一步完成后，用以下用例验证：

| 用例 | 预期结果 | 对应步骤 |
|---|---|---|
| 点击"公文写作" → "会议通知" → 填表 → 提交 | 产出格式规范的会议通知 | Step 1 |
| 同上，但故意留空必填项 | 按钮禁用，不可提交 | Step 1 |
| 输入"帮我写个通知"（不走卡片） | 系统通过 info_request 询问缺失信息 | 已有功能 |
| 写完通知后点击"复制文本" | 剪贴板中有纯文本 | Step 1 |
| 写会议通知，检查标题格式 | "关于召开XXX的通知" 格式正确 | Step 2 |
| 写请示报告，检查结尾 | 有"妥否，请批示" | Step 2 |
| 看完结果，输入"第二段换个更严肃的语气" | 只修改第二段，其他不变 | Step 3 |

### 3.6 第三轮结论

> 三步走策略：**Step 1 验证场景入口的价值（前端为主），Step 2 激活知识体系提升质量（后端为主），Step 3 补齐迭代修改闭环**。最关键的洞察是：方法论库和技能 prompt_template 是已有的"睡眠资产"，激活它们的 ROI 远高于从零构建新功能。而场景模板本质上是一个"前端到 prompt 的翻译器"——用结构化表单替代自由输入，让小白用户也能给出精准的需求描述。

---

## 附：全景文件清单

### 新增文件

| 文件 | 类型 | 用途 |
|---|---|---|
| `data/scenes/official_writing.yaml` | 配置 | 公文写作场景模板 |
| `data/scenes/daily_writing.yaml` | 配置 | 日常写作场景模板 |
| `data/methodologies/official_writing_flow.yaml` | 配置 | 公文写作方法论 |
| `data/skills/official_document.yaml` | 配置 | 公文格式规范知识 |
| `src/stores/scene_registry.py` | 后端 | 场景注册表 |
| `frontend/src/components/ScenePanel.vue` | 前端 | 场景选择面板 |

### 修改文件

| 文件 | 改动 |
|---|---|
| `src/api/routes.py` | 新增 `GET /api/scenes` 端点 |
| `src/init.py` | 初始化场景注册表 |
| `src/agents/team_lead.py` | 方法论加载 + 知识注入 |
| `frontend/src/components/ChatArea.vue` | 集成 ScenePanel |
| `frontend/src/components/MessageCard.vue` | 复制按钮 |
