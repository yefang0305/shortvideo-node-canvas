# 项目进度总结

更新时间：2026-06-01（v2：万能节点工作台与 MCP 外部总控；新增通用网页抓取节点）

> 本轮重大演进详见下方「## 10. v2 演进」与 [docs/PRD_v2_万能节点工作台与管家总控.md](docs/PRD_v2_万能节点工作台与管家总控.md)。
> 早期（v1，抖音垂直链路）的记录保留在第 1–9 节，仍然有效。
> 未来新开 Codex 对话时，优先阅读 [docs/Codex入职文档-外部总控手册.md](docs/Codex入职文档-外部总控手册.md)，它是外部总控的上岗 SOP。

## 项目定位

短视频节点画布工作台已经从最初的 HTML UI 预览，推进到一个可运行的 PyQt5 本地桌面端 MVP，并在 v2 进一步升级为「可无限叠加工具节点的内容生产万能工作台」。当前产品方向：

- v1：面向短视频采集、文案提取、文案改写、批量混剪、自动发布的垂直工作流引擎。
- v2：不止短视频——任何能力（写公众号/小红书、配图、出图、发布……）只要提供一份自描述清单（Node Manifest）就能成为节点；总管像管家一样理解每个节点、挑人派活、对接上下游。
- 用无限画布承载节点编排，节点既能独立运行，也能通过连线把上游输出传给下游。
- 内置大模型总控，先做“辅助驾驶”：生成计划、创建节点、连接流程、诊断错误；高风险执行仍由用户确认。
- 不修改原有主工作台项目，所有拆分和集成都放在个人网站 tools 目录下。
- **铁律**：管家不在运行时自写代码并执行；新能力只走「提示词 skill → 脚本 skill → 人工连接器」三条路径（见 PRD v2 §9.8/§10）。

## 当前目录

主项目目录：

```text
J:\MagicTool\个人网站\tools\短视频节点画布工作台
```

已接入或依赖的独立工具目录：

```text
J:\MagicTool\个人网站\tools\抖音主页链接采集
J:\MagicTool\个人网站\tools\抖音视频下载
J:\MagicTool\个人网站\tools\抖音文案提取
J:\MagicTool\个人网站\tools\抖音批量视频生成
J:\MagicTool\个人网站\tools\抖音视频自动上传
J:\MagicTool\emdia\MediaPush
```

v2 新增「节点技能库」目录，存放已做成节点的 skill 副本（复制而非移动，原项目不受影响）：

```text
J:\MagicTool\个人网站\tools\节点技能库\
├── 公众号上传\                 (源自 J:\MagicTool\公众号写作\发布)
├── baoyu-cover-image\
├── baoyu-infographic\
├── baoyu-xhs-images\
├── baoyu-article-illustrator\
└── baoyu-image-gen\            (已在此位置 bun install 装好依赖)
```

baoyu skill 原始库（17 个子 skill，按需复制到节点技能库）：
`J:\MagicTool\风格化图片生成工具\baoyu-skills-main\skills`

## 已完成能力

### 1. 画布基础体验

- 已完成 PyQt5 桌面主窗口。
- 已实现深色无限画布风格，整体视觉接近 HTML 预览稿。
- 左侧节点库、中心画布、右侧参数/状态/环境/总控区域已经成型。
- 节点可拖拽、双击添加、移动、选中、删除。
- 节点之间可拖线连接，并校验输入输出类型。
- 已修复节点拖拽时留下拖拽痕迹的问题。
- 支持保存和加载工作流 JSON。
- 支持“运行当前节点”“从这里继续运行”“运行全部流程”。
- 无依赖节点可以并行启动。

### 2. 节点系统

当前已经具备这些节点：

| 节点 | 状态 | 说明 |
| --- | --- | --- |
| 抖音主页采集 | 已接入真实执行 | 输入抖音主页链接，输出作品链接和 Markdown |
| 抖音视频下载 | 已接入真实执行 | 批量下载作品视频，使用原工作台链路里的 CR TubeGet 方案 |
| ASR 文案提取 | 已接入真实执行 | 输入视频，输出纯口播 TXT，调试产物保留为副产物 |
| 文案改写/标题 | 已接入真实执行 | 可读取改写 SKILL，调用总控大模型配置，输出改写文案和标题 |
| 批量混剪生成 | 已接入真实执行 | 使用独立批量视频生成工具，支持 TTS、素材、BGM、封面、分段参数 |
| MediaPush 发布 | 已接入投递执行 | 写入 MediaPush inbox，由原 MediaPush 项目监听/发布 |

v2 新增的内容创作节点（均为 Skill 节点，由通用 skill_node 执行器驱动）：

| 节点 | 模式 | 输入 → 输出 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| 封面设计 | text | article_text → image_prompts | 已入库，配 Key 可跑 | baoyu-cover-image，出封面设计方案/提示词 |
| 信息图设计 | text | article_text → image_prompts | 已入库，配 Key 可跑 | baoyu-infographic |
| 小红书配图设计 | text | article_text → image_prompts | 已入库，配 Key 可跑 | baoyu-xhs-images |
| 文章配图方案 | text | article_text → image_prompts | 已入库，配 Key 可跑 | baoyu-article-illustrator 前半段（出方案，不出图）|
| 文生图 | external action / script fallback | image_prompts → image_list | 已改为 Codex 内置 imagegen 主路径 | 默认生成 `codex_imagegen` 外部动作请求，由外部 Codex 生图并回填；第三方 provider 仅显式备用 |
| 公众号草稿上传 | script | article_text → publish_records | 已真机验证上传到草稿箱 | 你的发布 skill，排版+上传草稿箱一步到位 |

v2 通用能力积木（领域无关，输入源层第一批）：

| 节点 | 模式 | 输入 → 输出 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| 网页正文抓取 | 双路（脚本 / external action）| `[]` → article_text | 已真机验证 | 给 URL 抓正文落本地 md。X/Twitter 链接走 x-markdown 脚本（解长文+下图）；普通网页发外部动作由大脑 WebFetch 抓取 |

> 这些节点真跑前提：text 模式需配总控 API Key；script 模式需 bun（已装 1.3.14）+ 对应 skill 已 `bun install` + 行动类 API Key。文生图默认由 Codex 内置 imagegen 接手，不再要求第三方图像 provider key；只有开启“允许第三方备用”时才需要图像 provider 凭证。微信 appid/secret 目前仍在发布脚本内。

### 3. 总控 Agent

- 已实现总控面板。
- 支持填写 OpenAI-compatible API 配置。
- 大模型可以根据自然语言目标生成结构化计划。
- 生成计划后可以应用到画布，自动创建节点并连线。
- 无 API Key 时有本地规则计划器兜底。
- 已实现失败诊断入口：读取节点错误，调用大模型或本地规则给出排查建议。
- 当前总控仍是辅助驾驶，不会绕过节点协议直接操作本地文件或账号。

### 4. 参数面板

- 节点参数已经控件化。
- `执行模式` 已改成下拉选择，区分模拟/真实。
- `设备` 已支持 CPU / GPU CUDA 下拉，手动填 GPU 也会归一化为 cuda。
- `音色` 已做下拉，来源参考原工作台音色列表。
- `分段模式` 已做下拉：按文案分段、按时长均分、按数量均分。
- 本地路径类参数已增加选择按钮：
  - 素材库
  - BGM 文件
  - 封面底图
  - 输出目录
  - 保存目录
  - Inbox 目录
  - Cookie 文件
  - 导出文件
  - 改写 SKILL 文件

### 5. ASR 输出规范

- ASR 节点最终给下游传递的是纯 TXT 文案。
- 已接入过滤器思路，避免把标题、时间戳、文件名等内容传给下游。
- 可开启 LLM 优化错别字和断句。
- `.md`、`.json` 等调试产物仍可保留，但不作为正式节点输出。

### 6. 文案改写到混剪任务

- 文案改写节点可以接收 ASR 的 `clean_scripts`。
- 支持引入改写 SKILL 文件。
- 输出两个核心结果：
  - 改写后的文案
  - 标题
- 同时生成批量混剪可消费的 `batch_tasks.json`。

### 7. 批量混剪执行链路

- 批量混剪节点已能接收文案改写节点输出。
- 支持 TTS 参数：
  - App ID
  - Token
  - Resource ID
  - 音色
  - 语速
  - 音量
- 支持分段参数：
  - 按文案分段
  - 按时长均分
  - 按数量均分
  - 最短分段秒数
- 支持素材、BGM、输出参数：
  - 素材库
  - BGM 文件或目录
  - BGM 音量
  - 输出分辨率
  - 输出帧率
  - 输出目录
  - 生成数量
  - 封面底图
- 已把 FFmpeg 运行时补齐到独立批量混剪项目，包含 exe 和 DLL。
- 已修复因缺少 FFmpeg DLL 导致视频处理失败的问题。
- 已增强失败判断：如果批量混剪 stdout 中出现失败或没有产出视频，会把节点标记为失败。

### 8. MediaPush 节点

- MediaPush 节点当前不是复制账号 cookie，而是对接原 MediaPush 项目。
- 节点会把待发布视频写入：

```text
J:\MagicTool\emdia\MediaPush\inbox
```

- 原 MediaPush 项目继续使用自己的 profiles 和 data。
- 只要原 MediaPush 程序运行或后续打开并扫描 inbox，就能处理画布投递的发布批次。
- 这种方式避免重复维护 cookie，也降低账号资料迁移风险。

### 9. 环境检测与运行日志

- 右侧环境检测已支持：
  - Python
  - FFmpeg
  - 批量混剪 FFmpeg
  - CR TubeGet
  - MediaPush
  - 外部工具目录
- FFmpeg 检测已扩展到：
  - PATH
  - 画布项目 ffmpeg 目录
  - 独立批量混剪项目 ffmpeg 目录
  - 原工作台 ffmpeg 目录
- 每次启动会生成运行日志：

```text
runs/run_YYYYMMDD_HHMMSS.log
```

- 右侧最近输出已显示输出时间，方便判断节点是否刚刚运行、是否还在工作。

## 10. v2 演进：万能节点工作台与管家总控

本轮把项目从「短视频垂直工具」推进到「可无限叠加节点的内容生产工作台」。核心动作只有一个：**把节点的自描述（Node Manifest）做厚**，其余能力都长在它上面。详细设计见 [PRD v2](docs/PRD_v2_万能节点工作台与管家总控.md)。

### 10.1 节点说明书（阶段 0，✅）

- 新增 [app/manifest.py](app/manifest.py)：`PortType`（端口数据契约）+ `ParamSpec`（参数说明书）+ `PORT_TYPES` 注册表。
- `NodeSpec` 扩成「岗位说明书」：新增 `capability / when_to_use / typical_upstream / typical_downstream / param_specs / output_example / keywords / skill_binding`（全部可选，零破坏）。
- 6 个抖音节点补全说明书；`node_protocol_prompt()` 升级为输出厚 Manifest（端口 Schema + 参数说明 + 何时使用 + 典型上下游 + 产物样例 + skill_mode + keywords）。
- 端口契约：`profile_links / video_files / clean_scripts / batch_scripts / rendered_videos / publish_records / generic` + 内容场景 `article_text / image_prompts / image_list / score_report`。

### 10.2 强 Schema 端口系统（阶段 1，✅）

- `inputs/outputs` 仍是端口名列表（画布/引擎零改动），Schema 通过 `PORT_TYPES` 旁挂查表。
- 连线校验从「端口名相等」升级为「数据契约兼容」：`ports_compatible / best_connection / describe_port`；失败提示给出契约级原因（如 `作品链接列表/json` vs `本地视频文件列表/file_list`）。
- 同名天然兼容 + `PORT_COMPATIBILITY` 显式声明兼容（扩展口）；`generic` 端口放行占位。

### 10.3 Skill 节点协议 + 管家造节点（阶段 4，✅ 后端+UI）

- `skill_binding` 三种执行模式（通用 [tool_executor.py](app/runtime/tool_executor.py) 的 `_run_skill_node`）：
  - **text**：skill 正文当 system prompt + 上游输入 → 调 LLM → 文本产物。
  - **image**：先出提示词再调图像后端（`/images/generations`），未配后端优雅降级。
  - **script**：运行 skill 自带脚本（`bun`/`py`），支持 `{input}`/`{output}` 占位、`env` 注入 API Key、按文件收集产物。
- 造节点器 [app/agent/node_builder.py](app/agent/node_builder.py)：读 SKILL.md frontmatter → 规则生成 Manifest（无 Key）/LLM 增强（有 Key）→ `write_custom_node` 写入 `custom_nodes.json`。
- UI（[main_window.py](app/ui/main_window.py) 总控面板「管家造节点」区）：选 skill → 填目标 → 选模式 → **预览** → **确认入库** → `reload_node_specs()` 原地热重载 + `NodeLibrary.reload()`，新节点立刻可拖可连可跑。
- 安全：先预览再写入；不生成业务代码；script/image 标 `requires_confirmation`。

### 10.4 baoyu skill 库接入（第一批，✅）

- 调研了 baoyu 全部 17 个子 skill（分「纯设计/提示词型」与「脚本型」）。
- 第一批做成节点：封面设计、信息图设计、小红书配图设计（text，零 bun）、文章配图方案（text）、文生图（script）、公众号草稿上传（script，源自你的发布 skill）。
- 运行时：装好 **bun 1.3.14**（`C:\Users\ASUS\.bun\bin\bun.exe`），`_find_bun()` 兜底默认位置；image-gen 已 `bun install`。
- 已把 6 个 skill 复制到 `节点技能库`，节点路径全部重指向新位置。

### 10.5 数据驱动总管（✅）

- `SimpleAgentPlanner` 从「硬编码 6 个抖音节点关键词」重写为**数据驱动**：按每个节点的 `名称/分组/keywords` 匹配目标，按端口兼容性（`best_connection`）自动排序连线。
- 效果：**所有现有与未来节点，总管自动认识**。实测「给文章配插图、出图、上传公众号」→ 准确挑出文章配图方案/文生图/公众号上传，自动连线 + 列出待补 API Key + 标注高风险节点。

### 10.6 测试

- 新增测试：`test_manifest`（端口契约/厚 Manifest）、`test_node_builder`（造节点）、`test_skill_script`（脚本参数/env/产物）、`test_planner`（数据驱动总管）。
- 全套 **34 测试全绿**（本机无 pytest，用临时 runner 直接调 `test_*`，详见记忆「运行时环境坑」）。

### 10.8 移除内置总控 + 统一凭证（✅）

决策：外部 agent（Claude Code/Codex）经 MCP/直接操作担任总控，内置总控/计划器无存在必要，移除。
（spec：docs/superpowers/specs/2026-05-31-移除内置总控与统一凭证-design.md）

- **删**：计划器 UI（生成计划/应用画布）、造节点 UI、`SimpleAgentPlanner`/`AgentPlan`/`parse_plan_json`、test_planner。
- **保留地基**：`node_protocol_prompt()` 厚 Manifest、`node_builder` 造节点后端、失败诊断（`LLMDiagnoser`）、`keywords`——给阶段 6 MCP 与外部总控用。
- 「总控」标签页 → 「**设置**」标签页（模型 API 配置 + 失败诊断）。
- **统一凭证文件** `config/credentials.json`（gitignored）：`model`（模型 API，自动迁移旧 agent_settings.json）+ `services`（各服务商 key）。新模块 `app/runtime/credentials.py`。
- 节点按名引用凭证：skill_binding 支持 `{cred:服务.字段}`；文生图去掉 10 个裸密钥参数改引用；参数面板对引用凭证的节点显示"需要凭证"口子；不需要 API 的节点零负担。
- 微信 appid/secret 仍在发布脚本内（待办：挪进 `services.wechat`）。

### 10.9 阶段 6：MCP 控制面（✅，2026-05-31）

阶段 6 让外部 agent（Claude Code / Codex）经 MCP 操控工作台：编排、运行、看过程、看产物、诊断、随时造节点。GUI 与 MCP 共用一套执行核，`workflows/active.json` 为单一真相源，PyQt 画布实时监听重绘。

**组件：**

| 组件 | 文件 | 职责 |
|------|------|------|
| WorkflowRunner | `app/runtime/runner.py` | 无 Qt DAG 执行核，模拟/真实分流，产物传递，失败阻断，确认闸门 |
| 工作流仓库 store | `app/mcp/store.py` | active.json 读写 + rev + add/connect/set/delete/run/造节点纯函数 |
| MCP server | `app/mcp/server.py` | FastMCP stdio 薄壳，注册 15 个工具调 store |
| GUI 适配 | `app/runtime/engine.py` | RuntimeEngine 改用 WorkflowRunner + 回调转 Qt 信号 |
| GUI 同步 | `app/ui/main_window.py` | 跑流程改走 engine.run_workflow；active.json autosave + QFileSystemWatcher 重载 |
| MCP 配置 | `.mcp.json` | Claude Code 接入，Python313 + `-m app.mcp.server` |

**15 个 MCP 工具：** `list_nodes` / `get_workflow` / `add_node` / `connect` / `set_params` / `delete_node` / `run_node` / `run_chain` / `run_all` / `get_output` / `get_logs` / `create_skill_node` / `reload_nodes` / `get_external_actions` / `complete_external_action`

**安全：** 高风险真实节点需 `confirm=true`；MCP 仅本机 stdio；不暴露凭证；造节点默认 preview。

**测试覆盖：**
- `tests/test_runner.py`：依赖排序、上游产物传递、确认闸门（3 tests）
- `tests/test_mcp_store.py`：load/save/rev、add/connect(校验)/set/delete、run/write-back、needs_confirmation、run_node 单节点、create_skill_node preview（8 tests）
- `tests/test_gui_smoke.py`：MainWindow 构造+跑链路、engine.run_node 上游注入、autosave+rev、外部 store 改动重载画布、autosave 无回环（5 tests）
- MCP stdio client smoke：initialize + list_tools 确认 13 tools
- 全部 16 tests + server import + mcp json 验证通过

**参考文档：** spec `docs/superpowers/specs/2026-05-31-阶段6-mcp控制面-design.md`，plan `docs/superpowers/plans/2026-05-31-阶段6-mcp控制面.md`

### 10.7 阶段进度对照

| 阶段 | 状态 |
| --- | --- |
| 0 节点说明书 | ✅ |
| 1 强 Schema 端口 | ✅ |
| 2 抖音链路做实 | ✅（用户已自测跑通）|
| 3 总管吃厚 Manifest 真编排 | 部分（规则计划器已数据驱动；LLM 计划器已拿到厚 Manifest，未做「解释为什么这么编排」）|
| 4 Skill 节点 + 管家造节点 | ✅（后端 + UI + 一批真实节点）|
| 5 横向复制更多领域 | 进行中（baoyu 第一批已接，第二档脚本节点待续）|
| 6 MCP 控制面（外部总控，Claude Code/Codex 当总控）| ✅ 已实现（2026-05-31）|
| 7 Codex 接管生图（外部动作协议）| ✅ 已实现（2026-06-01）|

## 已真实跑通的链路

用户已经手动跑通过一条完整链路：

```text
抖音主页采集
  -> 抖音视频下载
  -> ASR 文案提取
  -> 文案改写/标题
  -> 批量混剪生成
```

其中前面三个节点也曾一次性串联跑通：

```text
主页采集 -> 视频下载 -> ASR
```

后续又推进到了批量混剪，并定位/修复了 FFmpeg 缺失导致的视频处理失败问题。

2026-05-31 又真机跑通过一条公众号草稿链路：

```text
文章 MD 导入
  -> 文章配图方案
  -> 文生图
  -> 公众号文章装配
  -> 公众号草稿上传
```

本次真机验证暴露出两个关键问题并已处理：

- 即梦 provider 参数名错误：脚本把提示词传成 `prompt_text`，官方接口需要 `prompt`，导致生图与提示词脱钩，出现“番茄炒鸡蛋”类错误图。已在 `节点技能库/baoyu-image-gen` 修复并用单图实测确认提示词生效。
- 主产品架构调整：文生图节点默认不再调用第三方 provider，而是产出 `codex_imagegen` 外部动作请求，由 Codex 使用内置 imagegen 生图并通过 MCP 回填 `image_list`。

## 重要问题与处理记录

### 1. bat 启动闪退

已处理：

- 增加快速启动 bat。
- 规避中文路径带来的启动问题。
- 保留 `start_canvas.bat` 和 `启动.bat`。

### 2. ASR GPU 参数失败

问题：

- 用户在设备参数里填写 GPU，底层执行期望 cuda。

处理：

- 参数面板改成 CPU / GPU CUDA 下拉。
- 执行层增加归一化逻辑，`GPU` 会转成 `cuda`。

### 3. 批量混剪提示找不到文件

问题：

- 独立批量混剪项目里缺少 FFmpeg 完整运行时。

处理：

- 从原工作台复制完整 FFmpeg 目录。
- 包括 `ffmpeg.exe`、`ffprobe.exe` 和相关 DLL。
- 环境检测也增加了批量混剪 FFmpeg 检查。

### 4. 批量混剪提示分段视频处理失败

问题：

- 手动测试 FFmpeg 裁剪命令时确认缺 DLL 导致退出。

处理：

- 补齐 DLL 后手动裁剪测试通过。
- 视频生成链路恢复。

### 5. 环境检测 FFmpeg 不刷新/识别不到

处理：

- 扩展 FFmpeg 检测路径。
- 右侧刷新环境检测可以识别独立批量混剪项目中的 FFmpeg。

## 当前待办

### 本轮最新进展（2026-05-31）

- V1 批量混剪打磨：画布的“批量混剪生成”节点已新增字幕/字体参数，并会写入独立批量混剪工具的 `config/settings.json`：
  - 字幕字体、字号、颜色、位置 Y
  - 描边开关、描边颜色、描边粗细
  - 阴影开关、单行最大字数、字幕时间偏移
- V2 内容链路起步：新增“文章 MD 导入”内置节点，读取本地 `.md/.markdown` 文件并输出 `article_text`，可接封面设计、文章配图方案、文生图、公众号草稿上传等节点。
- V2 补齐关键缺口：新增“公众号文章装配”节点，接收 `article_text + image_list`，把首图作为封面、其余图片按段落插入正文，输出可直接交给“公众号草稿上传”的带图 Markdown 文件。
- 规则总管增强：多输入节点会等待本次计划中可用的所有输入生产者；当“公众号文章装配”存在时，“公众号草稿上传”会排在装配之后，避免直接上传未插图的原始文章。
- 文生图节点参数口子已扩展：支持服务商、模型、比例、尺寸、图片尺寸、质量，以及 OpenRouter/OpenAI/Google/DashScope/Replicate/Jimeng/Seedream 相关 API Key/Base URL 参数。
- 通过 codex-with-cc 只读研究任务确认：现有 `article_text / image_prompts / image_list / publish_records` 端口足够支撑“MD 文章 → 配图/封面 → 生图 → 上传”基础链路。
- 验证：临时测试 runner 全量 52 个测试通过；`compileall app tests` 通过。

### 本轮最新进展（2026-06-01）

- 文生图节点默认服务商改为 `codex_builtin`，主路径不再调用即梦/OpenRouter/OpenAI 等第三方出图服务。
- 新增 Codex 外部动作协议：
  - 文生图节点运行后输出 `external_action_request`。
  - Runner 将节点置为 `waiting_external`，summary 返回 `needs_external_action`。
  - MCP 新增 `get_external_actions` / `complete_external_action`。
  - Codex 生图完成后回填标准 `image_list`，下游“公众号文章装配/上传”无需改造。
- GUI 支持新状态：画布节点显示“等待 Codex”，运行器会触发刷新并从 running 集合移除。
- 第三方出图保留为显式备用：只有节点参数 `允许第三方备用=true` 时才走 baoyu-image-gen provider 路径。
- 继续保留前一轮稳定性修复：
  - Ark/部分 OpenAI-compatible 模型不支持 `response_format=json_object` 时自动重试无 `response_format`。
  - 即梦第三方备用模式批量 jobs 限制为 1，规避并发 429。
  - 公众号装配时清理失效的相对本地图片引用，避免把死图带进草稿。
- 新增 Codex 入职文档：`docs/Codex入职文档-外部总控手册.md`，沉淀新对话连接 MCP、读取节点 Manifest、编排链路、处理 Codex 生图回填、排查错误的上岗 SOP。
- 验证：临时测试 runner 全量 94 个测试通过；`compileall app tests` 通过；Codex 生图协议 smoke 通过。

### 本轮最新进展（2026-06-01 下午：通用能力积木 + 网页抓取）

跳出自媒体专用件，开始补**领域无关的通用节点**。第一批攻「输入源层」，落地一个高杠杆进料口节点。

- **external_action 协议通用化**（本轮真正的架构增量）：把外部动作完成回填从「生图专用」升级为按 `output_port` 分流的通用协议。
  - `complete_external_action(node_id, result)`：`image_list` 维持原样（校验图片文件）；新增 `article_text` 分支（接收 `{text,title,url}`，写 md 文件后产出 article_text）；未知 port 拒绝。
  - MCP 工具签名 `images` → `result`（兼容 list/dict/str）。
  - 意义：以后任何「工作台发起、大脑用原生能力完成」的活（抓取/搜索/OCR…）都能复用这条路，不绑定具体执行者。
- **新增「网页正文抓取」节点 `web_article_fetch`**（输入源组，`[] → article_text`）：给 URL 抓正文落本地 md，可直接接配图/改写/上传链路。真实运行**双路分流**：
  - **X/Twitter 链接**（x.com/twitter/fxtwitter/vxtwitter）→ 节点直接跑 `x-markdown` node 脚本，确定性解析长文 X Article + 下图，当场产出 `article_text`（`fetched_via=x-markdown`），不进 waiting_external。
  - **其它网页** → 发 `fetch_webpage` 外部动作，由大脑(Claude/Codex)用原生 WebFetch 抓取后回填。工作台运行时零网络依赖。
  - 设计精髓：节点只管「我要抓这个 URL」，由大脑/节点挑最合适的工具——X 用专用通道、普通网页用大脑。
- 新增节点参数 `X导入脚本`（默认指向本机 x-markdown 脚本，可覆盖）、`_is_x_url` 检测、`_run_x_markdown_import` 执行器；runner `_MOCK` 补 `web_article_fetch` 假数据。
- 验证：`test_web_fetch.py` 全新覆盖（节点加载/外部动作/X检测/X路由/非X回退/端到端回填）+ `test_mcp_store` 加 article_text/未知 port 用例；全量回归绿，生图 external_action 路径不回归。**真机验证**：苍何《万字保姆级教程 Hermes+Kimi K2.6》X Article，25 图，解析正确。
- 设计文档：`docs/superpowers/specs/2026-06-01-网页抓取节点与external-action通用化-design.md` + 实现计划 `docs/superpowers/plans/2026-06-01-网页抓取节点与external-action通用化.md`。

### v2 优先（内容创作链路）

1. **把 Codex 生图外部动作纳入完整自动续跑**：当前协议已能等待/回填 `image_list`；下一步让外部总控在完成 `complete_external_action` 后自动继续跑装配与上传节点。
2. **接第二档脚本节点**：baoyu-translate（翻译）、baoyu-format-markdown（排版美化）、baoyu-markdown-to-html（md 转公众号 HTML）等；逐个读 SKILL.md 正确接 args + `bun install`。
3. **API 配置（之前 defer 的细化）**：把发布脚本里硬编码的微信 appid/secret 抽成节点参数 + env 注入；第三方备用出图 provider key 仅作为高级备用配置。
4. **公众号内容质量闭环**：完善配图提示词、封面图、正文插图位置和上传前预览，减少“能上传但观感不稳定”的人工返工。
5. 阶段 3 收尾：外部总控不仅编排，还能解释为什么这么编排、哪些节点需要人工确认、哪些节点由 Codex 亲自接手。
6. 小瑕疵：规则计划器把无上游可接的悬空节点自动排到末尾（当前可能排在最前）。

### 高优先级（v1 遗留）

1. 批量混剪参数面板新增字体/字幕设置。
   - 字体名称
   - 字号
   - 字幕颜色
   - 字幕位置
   - 描边开关
   - 描边颜色
   - 描边粗细
   - 可选：阴影、最大字数、字幕时间偏移

2. 把新增字体/字幕参数写入独立批量混剪项目的配置，让真实视频生成时生效。

3. 为字体/字幕参数增加最小测试，避免参数面板有字段但执行层没有传递。

### 中优先级

1. 继续补齐更多节点真实执行能力。
2. 增强 MediaPush 节点状态回读，让画布能看到发布队列处理结果。
3. 给总控增加“运行前参数检查”，例如素材库为空、TTS Token 为空时提前提示。
4. 给节点执行增加更明显的进度状态，例如排队、运行中、成功、失败、耗时。

### 低优先级

1. 自定义节点配置做成更友好的 UI，而不是只靠 JSON 文件。
2. 工作流模板化，例如“对标采集到文案库”“文案到混剪成片”“成片到 MediaPush 发布”。
3. 后续如果要完全独立发布项目，再考虑复制 MediaPush 的 profiles 和 data，但当前不建议优先做。

## 下一步建议

最自然的下一步是先补“批量混剪字体/字幕参数”。这属于当前链路的直接增强，范围小、收益明显，也能让混剪产物更接近原工作台的可控程度。

推荐执行顺序：

1. 在 `app/models.py` 给批量混剪节点增加字体/字幕默认参数。
2. 在参数元数据里补充必要的下拉或布尔控件。
3. 在 `app/runtime/tool_executor.py` 把这些参数写入独立批量混剪工具的配置。
4. 增加测试验证参数映射。
5. 用原工作台 venv 跑单元测试和编译检查。

## 当前结论

这个项目已经不是单纯 UI 原型，而是一个能实际串起内容生产链路的本地 Agent 工作流 MVP。

v1 短视频闭环已成立：

```text
采集 -> 下载 -> ASR -> 改写/标题 -> 混剪 -> 投递发布
```

v2 把它升级为「万能节点工作台 + 管家总管」：节点靠厚 Manifest 自描述，端口有强 Schema，Skill 节点协议让任意 skill（提示词/脚本）零代码变节点，管家能造节点、且数据驱动地认识所有节点。内容创作链路已成形：

```text
文章 -> 文章配图方案 -> 文生图(Codex imagegen) -> 公众号文章装配 -> 公众号草稿上传
```

后续重点：让外部 Codex 总控把“等待外部动作 -> Codex 亲自完成 -> 回填 -> 继续下游”做成稳定闭环，继续按三条能力路径（提示词 skill / 脚本 skill / 人工连接器）叠加节点，并守住「工作台节点负责可审计执行，Codex 负责拆解、调度和自己擅长的能力」的产品边界。
