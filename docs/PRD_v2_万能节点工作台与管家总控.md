# PRD v2：万能节点工作台与管家总控

> 本文是 [PRD_短视频节点画布工作台.md](PRD_短视频节点画布工作台.md) 的演进版。
> v1 验证了"短视频生产链路可以节点化"。v2 的目标是把它从一个垂直短视频工具，
> 升级为一个**可无限叠加工具节点的内容生产工作台**，并让大模型总控像管家一样
> 真正"理解每一个节点"。

## 1. 愿景

一句话定位升级：

> 从"短视频节点画布"升级为"内容生产万能工作台"——任何一个能力（写公众号、写小红书、
> 做视频、发视频、配图、做封面、文章评分、电商图、数据报表、数据复盘、私信管理……）
> 都能封装成一个自描述节点挂上画布；总控像一个了解每位员工的管家，理解目标后挑人、
> 派活、对接上下游产物。

两个支柱，本质是同一块地基：

- **支柱一（管家记忆）**：总控了解每个节点干什么、输入是什么、输出是什么、参数怎么配、
  什么时候该用它、产物交给谁。这相当于给总控一份"员工花名册 + 岗位说明书"。
- **支柱二（无限叠加）**：新能力只要提供一份自描述清单（Manifest）就能成为节点，
  总控自动认识它、会用它，无需改总控代码。

这两件事靠同一个东西成立：**厚的节点自描述协议（Node Manifest）**。
做厚 Manifest = 同时点亮支柱一和支柱二。

## 2. 现状盘点（v1 结束时）

已具备：

- 画布、节点、连线、参数面板、运行引擎、模拟/真实双执行模式（见 v1 PRD 验收）。
- 6 个抖音链路节点：主页采集 → 视频下载 → ASR → 文案改写 → 批量混剪 → MediaPush 发布。
- 总控雏形：规则计划器 + OpenAI-compatible 大模型计划器。
- 节点协议雏形：[planner.py](../app/agent/planner.py) 的 `node_protocol_prompt()`
  已经把节点 `type/name/description/inputs/outputs/default_params/risk` 序列化喂给大模型。

现状的核心短板——**节点自描述太薄，只够"认人"，不够"派活"**：

| 现在有 | 管家真正需要的（v2 要补） |
|--------|--------------------------|
| 节点叫什么、干什么一句话 | 什么时候该用它（适用场景 / 触发条件） |
| 端口只有一个名字（如 `profile_links`） | 端口的**数据契约 Schema**（数据形态、字段、样例） |
| 默认参数键值 | 每个参数的含义、怎么填、填错后果 |
| risk 等级 | 典型上游 / 典型下游（前面接谁、后面交给谁） |
| —— | 一段真实产物样例（让大模型"见过世面"） |

## 3. 关键设计决策（已与用户确认）

1. **端口用强 Schema**：每个端口绑定一份明确的数据契约（类型 + 字段结构 + 样例），
   连线按 Schema 校验兼容性，大模型据此判断"两个节点能不能接"，而不是靠名字猜。
2. **先深做一条链路**：先把"抖音视频"这条链路从采集到发布真实跑通、打磨透，
   沉淀出节点扩展的标准范式，再横向复制到其他领域。
3. **统一 Skill 节点协议**：定义一种"Skill 节点"标准，任意 skill（如 baoyu 配图、
   db 评分）按约定包一层（输入 → 调用 → 输出 + 一份 Manifest）即可成为节点，
   之后接 skill 近乎零成本。

## 4. 总体架构

整条演进只有一个核心动作：**把节点的自描述做厚**，其余能力都长在它上面。

```text
                ┌─────────────────────────────────────┐
                │  Node Manifest（岗位说明书）           │  ← 支柱一 + 支柱二的共同地基
                │  端口 Schema · 参数说明书 · 何时使用    │
                │  典型上下游 · 产物样例 · 能力标签       │
                └─────────────────────────────────────┘
                    ↓                ↓                ↓
              强 Schema 端口      管家总控          Skill 节点协议
              （能不能连）        （派活给谁）       （无限叠加）
                    ↓                ↓                ↓
            ───── 先在"抖音视频"这一条链路上验证全部范式 ─────
                                     ↓
                   横向复制 → 公众号 / 小红书 / 电商 / 数据报表 / 私信
```

## 5. 演进路线（分阶段）

### 阶段 0：节点说明书升级（Node Manifest）★ 龙头

**目标**：把 `NodeSpec` 从"名片"扩成"岗位说明书"，做完即点亮支柱一。

交付物：

1. 新增端口类型注册表 `PortType` / `PORT_TYPES`：每个端口名绑定一份数据契约
   （`label / kind / item / description / example`）。
2. 新增参数说明结构 `ParamSpec`：`label / meaning / how_to_fill / consequence / widget`。
3. 扩展 `NodeSpec`，新增可选字段（带默认值，**不破坏现有实例化与画布/引擎**）：
   `capability`（能力标签）、`when_to_use`（何时使用）、
   `typical_upstream` / `typical_downstream`（典型上下游）、
   `param_specs`（参数说明书）、`output_example`（产物样例）。
4. 为 6 个抖音链路节点补全上述说明书字段。
5. 升级 `node_protocol_prompt()`：输出厚 Manifest（含端口 Schema、参数说明、
   何时使用、典型上下游、产物样例）。
6. 新增 `tests/test_manifest.py`：校验每个端口名都有 `PortType`、每个节点都有
   `capability` 与 `when_to_use`、协议 prompt 能正常构建为合法 JSON。

约束（保持简单）：

- `inputs` / `outputs` 仍是 `list[str]` 端口名，Schema 通过 `PORT_TYPES` 旁挂查表，
  画布连线与引擎代码零改动。
- `param_specs` 优先覆盖关键参数；非关键参数（如混剪节点的全部 TTS 旋钮）随
  阶段 2 各节点做实时再逐步补全。

验收：

- `python -c "from app.agent.planner import node_protocol_prompt; node_protocol_prompt()"`
  输出包含端口 Schema 与参数说明的厚 Manifest。
- `tests/test_manifest.py` 全绿。
- 现有画布、连线、运行、保存加载功能不回归。

### 阶段 1：强 Schema 端口系统

**目标**：连线时按端口数据契约校验兼容性，总控据实判断节点可连性。

- 连线校验从"端口名相等"升级为"端口 Schema 兼容"（名相等仍是最强匹配，
  另允许声明显式兼容关系）。
- 校验失败的提示带上 Schema 差异原因。
- 把现有 6 节点端口迁移到 `PORT_TYPES`（阶段 0 已建表，此处接入画布校验）。

验收：不兼容的端口连线被拒绝并给出 Schema 级原因；兼容的链路正常连通。

### 阶段 2：抖音视频链路做实做通 ★ 分水岭

**目标**：6 个节点从采集到发布**真实**跑通一遍，用真实负载验证 Manifest + Schema。

- 逐节点把执行器从模拟切到真实，补全各自 `param_specs`。
- 跑通"主页链接 → 作品链接 → 下载 → ASR → 改写 → 混剪 → 发布"端到端。

验收：一条真实链路端到端成功产出并发布（发布步骤仍需人工确认）。

### 阶段 3：总控进化成真管家

**目标**：LLM 计划器吃厚 Manifest，从"关键词拼接"进化为"理解—挑人—派活—对接"。

- 用厚 Manifest 取代现有 `SimpleAgentPlanner` 的关键词匹配主路径。
- 计划产出：挑对节点 + 自动填参 + Schema 校验过的连线 + 缺参提醒 +
  **能解释"为什么这么编排"**。

验收：给定跨节点目标，总控产出合理且 Schema 自洽的节点图，并能说明编排理由。

### 阶段 4：Skill 节点协议（跨领域第一步）

**目标**：定义"Skill 节点"标准，让任意 skill 包一层即成节点。

- 定义 Skill 节点的 Manifest 约定 + 适配器（输入 → 调用 skill → 结构化输出）。
- 首批落地两个真实 skill 节点：**baoyu 配图**、**db 文章评分**，
  验证"非抖音、非视频"能力也能无缝挂上。

验收：baoyu 配图、db 评分作为节点出现在画布并真实运行；总控能识别并编排它们。

### 阶段 5：横向复制到其他领域

**目标**：进入"无限叠加工作台"形态。

- 复用 Manifest + Skill 协议，批量铺设：公众号写作、小红书、做封面/插图、
  电商图、数据报表、数据复盘、私信管理等节点。
- 形成跨领域工作流模板库。

验收：至少 3 个非短视频领域各有可运行节点，并能由总控编排出端到端流程。

## 6. 数据模型（阶段 0 落地）

### 6.1 端口类型 PortType

```python
@dataclass(frozen=True)
class PortType:
    name: str          # 端口名，也是连线匹配键，如 "profile_links"
    label: str         # 人类可读名，如 "作品链接列表"
    kind: str          # 数据形态：file_list / text_list / json / records / image_list / text
    item: str          # 单个元素说明
    description: str    # 这个端口流的是什么
    example: Any        # 一段真实样例，喂给大模型
```

全局 `PORT_TYPES: dict[str, PortType]` 注册所有端口契约；端口名即键。

### 6.2 参数说明 ParamSpec

```python
@dataclass(frozen=True)
class ParamSpec:
    key: str
    label: str
    meaning: str            # 这个参数是什么
    how_to_fill: str        # 怎么填
    consequence: str = ""   # 填错 / 不填的后果
    widget: str = "text"    # text / number / bool / select / file / dir
    options: list[str] = []  # widget=select 时的候选
```

### 6.3 NodeSpec 扩展（新增可选字段）

```python
capability: str = ""                       # 能力标签，如 "download_douyin_videos"
when_to_use: str = ""                       # 什么时候该用它
typical_upstream: list[str] = []            # 典型上游节点 type
typical_downstream: list[str] = []          # 典型下游节点 type
param_specs: dict[str, ParamSpec] = {}      # 参数说明书（键 = 参数名）
output_example: Any = None                  # 一段真实产物样例
```

### 6.4 厚 Manifest 输出格式（node_protocol_prompt）

```json
{
  "type": "douyin_video_download",
  "name": "抖音视频下载",
  "capability": "download_douyin_videos",
  "description": "...",
  "when_to_use": "已经拿到作品链接、需要把视频下到本地时使用",
  "inputs":  [{ "port": "profile_links", "label": "...", "kind": "...", "item": "...", "example": ... }],
  "outputs": [{ "port": "video_files",   "label": "...", "kind": "...", "item": "...", "example": ... }],
  "typical_upstream":   ["douyin_profile_collect"],
  "typical_downstream": ["asr_extract"],
  "params": [{ "key": "保存目录", "label": "...", "meaning": "...", "how_to_fill": "...", "consequence": "..." }],
  "default_params": { ... },
  "output_example": { ... },
  "risk_level": "medium",
  "requires_confirmation": true
}
```

## 7. 非目标（v2 阶段 0-1）

- 不在阶段 0 就改造画布连线校验逻辑（留给阶段 1）。
- 不在阶段 0 强求每个参数都写满 `param_specs`（关键参数优先，其余随阶段 2 补）。
- 不在阶段 0-1 引入 Skill 节点（留给阶段 4）。
- 不做循环、复杂表达式、条件分支等工作流增强（延续 v1 非目标）。

## 8. 风险与应对

- **范式未验证就铺广**：最大风险。以阶段 2 跑通为分水岭，之前不大规模铺新领域节点。
- **Manifest 膨胀拖慢节奏**：阶段 0 只做结构 + 6 节点高层字段 + 关键参数说明，
  细节随节点做实时补，避免一次写满。
- **Skill 协议过早抽象**：先用 baoyu/db 两个真实例子打磨协议（阶段 4），
  再大规模复用（阶段 5）。

## 9. 阶段 4 详细设计：Skill 节点协议与管家造节点

> 目标：让管家能"自己造工具"——给它一个 skill 文件，它生成一个能拖、能连、能真跑的
> 节点放进节点库。本节是阶段 4 的可落地设计。

### 9.1 核心拆解：声明与执行解耦

"造工具"拆成两件难度天差地别的事，关键是**不让管家生成执行器代码**：

- **造声明（容易）**：管家读 skill 的 `SKILL.md`，生成一条节点 Manifest（绑定该 skill），
  写入 `app/nodes/custom_nodes.json`，重载后节点出现在列表。复用现成的
  `load_node_specs()` 声明式注册口。
- **跑执行（靠通用执行器，不生成代码）**：新增**一个**通用 `skill_node` 执行器，
  所有 skill 节点共用它。执行器读节点绑定的 skill 文本当提示词、拼接上游输入、
  调用模型、把产物落盘到输出端口。新增 skill 节点不需要改执行器代码。

### 9.2 skill_node 绑定结构

`NodeSpec` 新增可选字段 `skill_binding`，自定义节点 JSON 可声明：

```json
{
  "type": "wechat_article_illustrate",
  "name": "公众号文章配图",
  "group": "公众号",
  "inputs": ["article_text"],
  "outputs": ["image_prompts"],
  "skill_binding": {
    "skill_file": "J:/.../baoyu-skills-main/skills/baoyu-article-illustrator/SKILL.md",
    "mode": "text",                  // text=文字产物 / image=出图
    "input_port": "article_text",     // 读哪个上游端口的数据当输入
    "output_port": "image_prompts",   // 产物写到哪个输出端口
    "instruction": "为文章生成配图方案与提示词"
  }
}
```

### 9.3 通用 Skill 执行器（三种模式）

skill 本身分两类：**提示词型（思考：分析/写作/打分/出方案）**与
**脚本型（行动：真转换/出图/上传，目录里带 `scripts/`）**。执行器对应三种模式：

- **text 模式 / 提示词型**（db 评分、公众号/小红书写作、文案改写、生成配图提示词……）：
  `system = skill 正文`，`user = instruction + 上游输入`，调用现有 OpenAI-compatible
  链路，文本产物落盘为 `.md/.txt`，写入输出端口。**纯软件，全自动跑通。已实现。**
- **image 模式**（真出图，无脚本 skill 时的内置兜底）：先得到图像提示词，再调用可配置
  图像后端（OpenAI-compatible `/images/generations`），落盘图片写入 `image_list`。
  **未配置后端时优雅降级**为只产出提示词。已实现。
- **script 模式 / 脚本型**（排版、文生图、传公众号、发微博/X……，关键补强）：
  执行器**运行 skill 自带的脚本**（如 `bun {baseDir}/scripts/main.ts <args>`），
  把上游输入与 API 配置作为参数/环境变量传入，捕获脚本产物（文件/JSON）写入输出端口。
  **我们不写、不生成任何业务代码——脚本是 skill 作者写好、随 skill 分发的**；
  我们只负责调用，沿用本项目既有的"subprocess 调外部工具"范式（见 tool_executor）。
  依赖：需要运行时（bun/npx）+ 该能力的 API 配置；纳入环境检测面板。

### 9.4 管家造节点流程（先预览再写入）

1. 用户在总控里给一个 skill 路径 + 一句目标（"给公众号文章造个配图节点"）。
2. 造节点器读取 `SKILL.md` 的 frontmatter（`name`/`description`）与正文。
3. 调模型生成候选 Manifest（端口、参数、`when_to_use`、`skill_binding`）；
   无 API Key 时用规则兜底（直接用 frontmatter 的 name/description + 默认端口）。
4. **把候选 Manifest 预览给用户**（不直接写盘）。
5. 用户确认后，追加写入 `custom_nodes.json` 并热重载节点库，新节点入列表。

### 9.5 新增端口契约

为内容创作场景补充端口类型：`article_text`（文章正文）、`image_prompts`（配图方案/提示词）、
`image_list`（图片文件列表）、`score_report`（评分报告）等，登记进 `PORT_TYPES`。

### 9.6 安全边界

- 造节点默认只写 `custom_nodes.json`，不生成可执行代码、不改 `tool_executor.py`。
- 写盘前必须用户确认（先预览再写入）。
- skill 节点执行默认 `执行模式=模拟`；image 模式与外部发布类 skill 标 `requires_confirmation`。
- 造节点器只读取用户显式给出的 skill 文件，不扫描或读取协议外的敏感文件。

### 9.7 阶段 4 验收

- 给定 `baoyu-article-illustrator` 的 SKILL.md，管家能产出候选 Manifest 并预览。
- 确认后节点出现在节点库，可拖、可连、可在 text 模式真跑出配图提示词。
- 通用 Skill 执行器对任意 text 类 skill 复用，无需改执行器代码。

### 9.8 新能力来源的三条路径（按优先级）

一个新能力进入工作台，按以下优先级，越靠前越省力、越安全：

1. **提示词 skill → text 模式执行器**。思考类（分析/写作/打分）。零代码、零外部依赖。
2. **脚本 skill → script 模式执行器**。行动类（排版/文生图/上传）。**不写任何业务代码**，
   只装运行时 + 配 API；脚本由 skill 作者提供。覆盖面极广（整个 baoyu 库）。
3. **连接器节点 → 人工写一次的可复用连接器**。仅当某能力**既无 skill 也无现成工具**时，
   由人（或"管家起草 + 人工审核"）写一个连接器，写一次永久复用。少见、且必须人工把关。

**铁律**：管家**不在运行时自写代码并直接执行**。脚本要么是 skill 自带、要么是人工审核过的
连接器；管家只负责"调用"，不负责"现写"。这是与通用编码 agent 的根本分界（见 §10）。

## 10. 产品定位与边界（重要：决定我们不做什么）

> 这一节是护城河，迭代中最容易被遗忘，必须显式守住。

### 10.1 我们在 Claude Code 与 n8n 之间

本工作台借用了 Claude Code 的架构骨架，但刻意做成更受约束、更可视化的另一种东西：

| 维度 | Claude Code（开放编码 agent） | 本工作台总管 | n8n/Coze（可视化工作流） |
|------|------|------|------|
| 工具本质 | 写代码、跑任意命令，无边界 | **带类型端口的可视化节点** | 预制节点 |
| 智能层 | 理解+推理+执行融为一体 | **管家理解目标、编排节点** | 规则/手工编排为主 |
| 造工具 | 现写新代码 | **接线 skill / 人工连接器**，不现写代码 | 基本不造 |
| 自动度 | 自主 loop 执行 | **辅助驾驶，人确认**（重任务/高风险必确认） | 手工触发 |
| 产物 | 一次性 agent 动作 | **可存、可复用、可分享的可视化工作流** | 工作流 |

一句话：**有 Claude Code 那样"懂工具、会编排、能扩展工具"的大脑，但身体是带类型的可视化
节点画布，造工具靠"接线 skill"而非"写代码"。**

### 10.2 明确不做（守住边界）

- **不让管家在运行时自写代码并执行**。新能力只能走 §9.8 三条路径。
- **不追求"什么都能干的本地 Claude Code"**。一旦允许自写自跑、自动执行高风险动作，
  就丢了"安全、可视、可复用、运营者能看懂"这几条命根子，反而是个更差的 Claude Code。
- **不做完全自动驾驶**：发布、上传、删除、覆盖等动作必须人工确认。
- **不绕过节点抽象**：管家不直接操作本地文件系统/外部系统，只能通过节点执行器。

### 10.3 为什么这是优势而非妥协

目标用户是**内容运营者**，不是开发者。可视化、节点看得见摸得着、工作流能沉淀复用、
动作可控——这些恰恰是命令行 agent 给不了的。守住边界，它才是个独立的好产品。

## 11. 阶段 6：MCP 控制面（外部总控）

> 目标：把工作台暴露成一个 MCP 服务器，让 Claude Code / Codex 作为**外部总控**接入，
> 实现"编排 + 执行 + 看过程 + 诊断 + 随时造节点"的自主循环。本节是阶段 6 的设计依据。

### 11.1 动机：两层总控

总控分两层，互补而非二选一：

| | 内置总控（已做） | 外部总控 via MCP（本阶段） |
|---|---|---|
| 谁来当 | 应用内 LLM 计划器 | Claude Code / Codex |
| 能力 | 生成计划 → 应用画布 | 编排 + 执行 + 观察日志 + 诊断 + 改代码 + 造节点，自主循环 |
| 面向 | 内容运营者（开箱即用、自包含） | 建设者/开发者（边建边调、全能） |
| 安全姿态 | 辅助驾驶、人确认 | 开放、强大 |

关键洞察：MCP 客户端连入第一件事就是"发现工具及其用途/输入输出"，这**正是
`node_protocol_prompt()` 输出的厚 Manifest**——阶段 0 的成果几乎 1:1 复用为 MCP 工具发现。

### 11.2 与 §10 边界的关系（不冲突）

§10 的铁律（"管家不自写自跑代码"）约束的是**出厂给运营者的产品形态**。
MCP 控制面是**建设者/高级模式**的控制通道：

- 出厂产品：内置总控 + 可视化画布 + 安全边界，承诺不变。
- 建设模式：Claude Code 经 MCP 自由编排、造节点、改代码——这是开发工具，不是出厂承诺。
- 二者通过"模式/人群"区分，不互相污染产品定位。

### 11.3 架构：核心与 GUI 解耦 + 单一真相源

前提：把核心（models / engine / node_builder / 工作流状态）与 PyQt **彻底解耦**
（现状已接近，仅 main_window/canvas 依赖 PyQt）。

```text
Claude Code / Codex（MCP 客户端）
   └─ MCP 工具调用 → workbench MCP server（app/mcp_server.py）
                        ├─ 读写 workflow.json（单一真相源）
                        └─ 调 engine 跑节点 / node_builder 造节点 / reload 节点库
   ┌─ PyQt 画布 App 监听 workflow.json 变化 → 实时重绘（满足"看过程"）
```

单一真相源用 `workflow.json`（或本地小服务）：MCP 改它、GUI 监听它，避免双写冲突。

### 11.4 暴露的 MCP 工具（草案）

| 工具 | 作用 |
|------|------|
| `list_nodes()` | 返回厚 Manifest（复用 `node_protocol_prompt`），让外部总控理解全部节点 |
| `get_canvas_state()` | 当前节点/连线/状态 |
| `add_node(type, params, x, y)` / `connect(source, target)` | 编排 |
| `set_params(id, params)` | 配参 |
| `run_node(id)` / `run_chain(id)` | 执行（含模拟/真实模式与确认策略） |
| `get_output(id)` / `get_logs()` | 看产物、看过程、看报错 |
| `create_skill_node(skill_file, mode, ...)` | 随时造节点（复用 `node_builder`）|
| `reload_nodes()` | 热重载节点库 |

资源（resources）：`workflow.json`、`runs/*.log`、节点产物目录。

### 11.5 阶段拆分

- **6a Headless MCP（先做）**：核心解耦 + `app/mcp_server.py` 暴露上述工具，
  Claude Code 用 `claude mcp add` 连入，全程操控工作流（产物落文件）。
  最快验证"Claude Code 当总控"成立。依赖：`uv pip install mcp`（FastMCP，stdio）。
- **6b 实时画布**：GUI 监听 `workflow.json`，把 6a 的操作实时画出来，满足"看过程"。
- **6c 安全策略**：真实/高风险动作即便经 MCP 也保留确认或显式 allow 列表；
  MCP 控制面默认仅在本机 stdio，不开放网络。

### 11.6 风险与开放问题

- **并发/双写**：GUI 与 MCP 同时改状态 → 必须单一真相源 + 文件锁/版本号。
- **解耦工作量**：engine 当前与 PyQt 信号耦合（`RuntimeEngine` 基于 QObject/pyqtSignal），
  headless 化需要一个不依赖 Qt 的执行入口。
- **客户端选择**：Claude Code 与 Codex 均支持 MCP；优先 Claude Code（`.mcp.json` 配置成熟）。
- **确认策略**：MCP 调 `run_node` 真实模式时如何确认（自动 allow 列表 vs 回传待确认）。

### 11.7 阶段 6 验收

- Claude Code 连上 workbench MCP 后，能 `list_nodes` 理解全部节点，
  并通过 MCP 工具搭出"文章→配图→出图→上传公众号"链路、触发运行、读取产物与日志。
- 能经 `create_skill_node` 在会话中造出新节点并立即可用。
- （6b）上述操作在 PyQt 画布上实时可见。
