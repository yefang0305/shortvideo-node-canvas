# 短视频节点画布工作台

本项目是一个本地桌面端的内容生产 Agent 工作流画布。把采集、下载、ASR、文案改写、批量混剪、发布，以及公众号/小红书/配图/出图等能力抽象成节点；节点可独立运行，也可连线把上游输出传给下游。

形态：**Coze 的身体（可视化节点画布）+ Claude 的脑子（外部 agent 经 MCP 操控）**。内置总控已移除——由外部 Claude Code / Codex 经 MCP 控制面「指哪打哪」，操作在画布上实时可见。

## 已实现

画布与执行：

- PyQt5 桌面无限画布、节点库、拖拽/双击添加、移动/选中/连线/删除
- 参数控件化（执行模式下拉、数字、布尔、下拉、文件/目录选择）
- 单节点 / 从此继续 / 运行全部，无依赖节点并行
- 默认模拟执行；改「真实」才调外部工具，高风险节点运行前确认
- 流程 JSON 保存加载、节点最近输出缓存、运行日志 `runs/run_*.log`
- 环境检测面板（Python / FFmpeg / CR TubeGet / bun 等）

节点协议（v2 地基）：

- **厚 Manifest**：节点自描述含端口数据契约 Schema、参数说明、何时使用、典型上下游、产物样例、触发关键词
- **强 Schema 端口**：连线按数据契约校验兼容性，失败给契约级原因
- **Skill 节点三模式**：`text`（调 LLM）/ `image`（出图后端）/ `script`（跑 skill 自带脚本，bun/python，`{cred:*}` 注入密钥）
- **声明与执行解耦**：造声明（写 `custom_nodes.json`）与跑执行（通用 `skill_node` 执行器）分离，新增 skill 节点不写业务代码

外部总控（MCP）：

- 工作台作为 MCP 服务器，Claude Code / Codex 经 stdio 操控编排/运行/看产物/造节点
- `workflows/active.json + rev` 单一真相源，画布监听实时重绘
- 高风险动作需显式 `confirm` 才执行；凭证集中、gitignored、不回传

真实节点：抖音链路 6 个（采集→下载→ASR→改写→混剪→发布）+ 公众号上传 + baoyu 配图/出图一批。统一凭证文件 `config/credentials.json`（节点按 `{cred:服务.字段}` 引用）。

## 运行方式

```powershell
cd "J:\MagicTool\个人网站\tools\短视频节点画布工作台"
python main.py
```

如果当前系统 Python 没有 PyQt5，可以使用原工作台虚拟环境验证：

```powershell
& "J:\MagicTool\Standalone\VideoCut\video_tool\venv\Scripts\python.exe" main.py
```

## 使用说明

- 从左侧节点库拖拽节点到画布，或双击节点快速添加。
- 选中节点后，在右侧“参数”面板编辑参数。
- 从节点右侧绿色输出端口拖到另一个节点左侧输入端口，即可建立连线。
- 也可以选择一个节点后点击“连接选中节点”，再选择目标节点并再次点击，作为备用连接方式。
- 连线会校验输入输出类型，不匹配时会拒绝并在日志里提示原因。
- 选中节点后点击“删除节点”，或在画布里按 Delete / Backspace 删除。
- “运行当前节点”只运行选中节点。
- “从这里继续运行”会运行当前节点，并按连线依赖继续触发下游。
- “运行全部流程”会从无上游依赖的节点开始运行。
- “设置”面板配置模型 API（Base / 模型名 / API Key），保存到 `config/credentials.json` 的 `model` 段（gitignored）。其它服务密钥（出图/发布等）填在同文件的 `services` 段，节点按 `{cred:服务.字段}` 引用。
- 每个节点参数里都有“执行模式”下拉框。默认是“模拟”；改成“真实”后才会调用外部工具。
- 需要确认的真实节点会在运行前弹出确认框，避免误触发重任务。
- 节点失败后，选中该节点并点击“诊断失败”，会读取错误信息并给出处理建议（配 API Key 时调大模型，否则本地规则）。
- 在“环境”面板点击“刷新环境检测”，可以查看真实链路所需依赖是否就绪。
- 节点运行成功后，右侧“参数”面板会显示“最近输出”，用于查看产物路径、报告路径和元数据。
- 运行日志会同步写入 `runs/` 目录，方便后续排查真实任务失败原因。

## 总控

内置计划器总控已移除。总控角色交给**外部 agent（Claude Code / Codex）经 MCP 控制面**承担——见下方「MCP 控制面」。本体只保留：

- 模型 API 配置（「设置」面板，给 text/image skill 节点和失败诊断用）
- 失败诊断（选中失败节点点「诊断失败」）

`node_protocol_prompt()` 输出的厚 Manifest 既给外部总控理解节点，也是 MCP 工具发现的协议。

## 真实节点接入

当前已接入前三个真实节点：

| 节点 | 调用项目 | 说明 |
|------|----------|------|
| 抖音主页采集 | `J:\MagicTool\个人网站\tools\抖音主页链接采集` | 调用核心提取函数，输出作品链接与 Markdown |
| 抖音视频下载 | `J:\MagicTool\个人网站\tools\抖音视频下载` | 调用下载器，默认使用内置 CR TubeGet 运行时 |
| ASR 文案提取 | `J:\MagicTool\个人网站\tools\抖音文案提取` | 调用 CLI，节点正式输出只传纯文案 `.txt`，`.md/.json` 仅作为调试副产物 |
| 文案改写/标题 | 画布内置执行器 | 可引入改写 SKILL，优先调用总控大模型配置，输出改写文案、标题和 `batch_tasks.json` |
| 批量混剪生成 | `J:\MagicTool\个人网站\tools\抖音批量视频生成` | 调用 `python main.py batch --tasks ...`，任务携带 TTS、分段、素材、BGM、分辨率、封面参数 |
| MediaPush 发布 | `J:\MagicTool\个人网站\tools\抖音视频自动上传` | 写入 inbox 批次和 `manifest.json`，由 MediaPush 自动发现 |

真实链路建议：

1. 把“抖音主页采集”“抖音视频下载”“ASR 文案提取”连起来。
2. 分别把这三个节点的“执行模式”改成“真实”。
3. 在“抖音主页采集”里填写主页链接。
4. 点击“从这里继续运行”。
5. 需要继续生产时，把“ASR 文案提取 -> 文案改写/标题 -> 批量混剪生成”连起来，并给改写节点填写 SKILL、给混剪节点填写素材库/TTS/BGM/输出目录等参数。

注意：

- 视频下载、ASR 都是重任务，运行前确认输出目录。
- ASR 首次运行可能下载模型，耗时较长。
- 混剪节点需要有效素材库、TTS 配置和 FFmpeg。
- MediaPush 节点只负责写入 inbox 批次；实际发布需要 MediaPush 工作台正在运行或后续打开。

## 新增节点预留口

后续新增节点有两个入口：

1. 临时配置型节点：复制 `app/nodes/custom_nodes.example.json` 为 `app/nodes/custom_nodes.json`，按示例增加节点声明，重启后会出现在左侧节点库。
2. 真实执行型节点：在 `app/runtime/tool_executor.py` 里为新的 `node.type` 增加执行器分支。

节点声明只负责让画布、外部总控和参数面板认识这个节点；真实执行逻辑由通用 `skill_node` 执行器（skill 节点）或 `tool_executor.py` 分支（原生节点）实现。

## MCP 控制面（外部总控）

工作台可作为 MCP 服务器，让 Claude Code / Codex 等外部 agent 操控编排、运行、看产物、诊断。

启用方式：项目根目录有 `.mcp.json`，Claude Code 会自动识别。

```json
{
  "mcpServers": {
    "video-workbench": {
      "command": "C:\\Users\\ASUS\\AppData\\Local\\Programs\\Python\\Python313\\python.exe",
      "args": ["-m", "app.mcp.server"],
      "cwd": "J:\\MagicTool\\个人网站\\tools\\短视频节点画布工作台"
    }
  }
}
```

依赖：`mcp` 包（FastMCP stdio），需安装到 Python313：
```powershell
& "C:\Users\ASUS\AppData\Local\Programs\Python\Python313\python.exe" -m pip install mcp
```

Codex 接入（用 `--env PYTHONPATH` 替代 cwd，让 `app` 包在任意目录可导入）：
```powershell
codex mcp add video-workbench --env "PYTHONPATH=J:\MagicTool\个人网站\tools\短视频节点画布工作台" -- "C:\Users\ASUS\AppData\Local\Programs\Python\Python313\python.exe" -m app.mcp.server
```
注意措辞区分：让 Codex **亲自当大脑**就说「用 video-workbench MCP 搭/跑…」（主线程直接调工具）；让 DeepSeek 干脏活才说「委派子代理」（走 codex_with_cc 插件），两者别混。

暴露 13 个 MCP 工具：`list_nodes` / `get_workflow` / `add_node` / `connect` / `set_params` / `delete_node` / `run_node` / `run_chain` / `run_all` / `get_output` / `get_logs` / `create_skill_node` / `reload_nodes`。

架构：
```text
Claude Code / Codex ──stdio──> app/mcp/server.py (FastMCP 薄壳)
                                   │ 调用
                                   ▼
                          app/mcp/store.py (工作流仓库：active.json 读写 + rev + 编排操作)
                                   │ 运行
                                   ▼
                          app/runtime/runner.py (WorkflowRunner，无 Qt)
                                   └─ ToolExecutor (已有，纯 Python)
                                   ▲
                      workflows/active.json (单一真相源，带 rev)
                                   ▲ 监听重绘 (QFileSystemWatcher)
                          PyQt 画布 (GUI 改走 Runner + 监听 active.json)
```

安全机制：
- 高风险真实节点需显式 `confirm=true` 才执行
- MCP 仅本机 stdio，无网络端口
- 不暴露凭证：`{cred:}` 只在脚本子进程注入，MCP 不回传密钥
- 造节点默认 `write=false` 预览

GUI 实时同步：画布结构/状态改动自动写入 `workflows/active.json`（带 `rev` 自增），`QFileSystemWatcher` 监听外部 MCP 修改，rev 比对后防抖重载，避免回环。

详细设计见 `docs/superpowers/specs/2026-05-31-阶段6-mcp控制面-design.md`。

## 目录结构

```text
短视频节点画布工作台/
├── app/
│   ├── agent/          # Agent 计划器占位层
│   ├── mcp/            # MCP 控制面：server + store + 工作流仓库
│   ├── nodes/          # 自定义节点声明预留口
│   ├── runtime/        # 节点运行引擎 (runner/engine/tool_executor)
│   └── ui/             # PyQt 界面与画布
├── docs/               # PRD 文档 + superpowers specs/plans
├── preview/            # HTML 静态 UI 预览
├── workflows/          # active.json (单一真相源) + 用户保存的流程文件
├── tests/              # 测试 (无 pytest，用 exec 临时 runner)
├── .mcp.json           # Claude Code MCP 接入配置
├── main.py
└── requirements.txt
```

## 下一步

- 真机验证内容链路：文章 → 配图 → 出图 → 上传公众号（真出图/真发需配各 provider key）
- 接第二档脚本 Skill 节点（翻译、排版美化、md 转公众号 HTML 等）
- 多工作流/会话管理、网络化 MCP、权限分级
