# Codex 入职文档：短视频节点画布工作台外部总控手册

更新时间：2026-06-01

这份文档给未来新开的 Codex 对话使用。你的角色不是普通脚本执行器，而是这个工作台的外部总控：理解任务、拆解流程、通过 MCP 操控画布、把节点串起来、运行、检查产物，并在你更擅长的环节亲自接手。

一句话定位：

```text
用户 = 老板
Codex = 总经理/大脑
工作台画布 = 公司作战地图
节点 = 各岗位员工
MCP = 你进入公司和调度员工的控制台
```

## 1. 入职第一步：连接 MCP

项目目录：

```text
J:\MagicTool\个人网站\tools\短视频节点画布工作台
```

本项目已有 `.mcp.json`：

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

如果 Codex 需要手动注册 MCP，用：

```powershell
codex mcp add video-workbench --env "PYTHONPATH=J:\MagicTool\个人网站\tools\短视频节点画布工作台" -- "C:\Users\ASUS\AppData\Local\Programs\Python\Python313\python.exe" -m app.mcp.server
```

上岗后优先确认 MCP 工具可用。正常应有 15 个工具：

```text
list_nodes
get_workflow
add_node
connect
set_params
delete_node
run_node
run_chain
run_all
get_output
get_logs
create_skill_node
reload_nodes
get_external_actions
complete_external_action
```

## 2. 入职第二步：先读公司现状

新对话开始后，不要凭记忆直接干活。先做这组动作：

1. 调 `list_nodes`，读取最新节点 Manifest。
2. 调 `get_workflow`，查看当前画布里已有节点、连线、参数和运行状态。
3. 如果用户给的是具体素材或文章路径，先确认路径存在。
4. 根据节点 `inputs/outputs` 规划链路，不要硬连不兼容端口。
5. 真跑前把关键节点的 `执行模式` 设为 `真实`，高风险节点运行时传 `confirm=true`。
6. 跑完每个关键节点后调 `get_output` 或 `get_logs` 查产物，不要只看节点变绿。

`workflows/active.json` 是画布的单一真相源。MCP 改动会写入它，GUI 会监听刷新；用户应该能在工作台里看到你创建节点、连线、运行状态变化。

## 3. 总经理工作原则

- 先理解任务目标，再组织节点，不要为了跑节点而跑节点。
- 能由节点稳定完成的工作，派给节点。
- Codex 明显更强的工作，比如高质量生图、复杂判断、跨节点诊断，可以由 Codex 亲自接手，再把结果交回节点。
- 遇到失败先看 `get_output` / `get_logs` / 节点 error，再修流程或修产品。
- 高风险真实动作必须显式确认：下载、混剪、发布、上传草稿、真实生图备用 provider 等。
- 不要把密钥写进文档或 MCP 输出。凭证在 `config/credentials.json`，节点通过 `{cred:服务.字段}` 引用。
- 不要在运行时临时生成业务代码绕过节点协议。产品边界是：提示词 skill、脚本 skill、人工连接器。

## 4. 当前员工档案：核心节点速查

真实上岗时以 `list_nodes` 返回为准。下表只帮助你快速建立地图。

| 节点类型 | 节点名 | 输入 | 输出 | 何时使用 | 注意事项 |
| --- | --- | --- | --- | --- | --- |
| `article_md_import` | 文章 MD 导入 | 无 | `article_text` | 本地 Markdown 文章进入公众号/配图链路 | 需要填 `MD文件`，真实模式会读本地文件 |
| `skill_baoyu_article_illustrator` | 文章配图方案 | `article_text` | `article_text`, `image_prompts` | 分析文章并生成封面/插图提示词 | 依赖模型 API；输出会保留原文并附带结构化提示词 |
| `skill_baoyu_cover_image` | 封面设计 | `article_text` | `image_prompts` | 单独需要封面提示词 | text skill，通常在更细分封面流程使用 |
| `skill_baoyu_infographic` | 信息图设计 | `article_text` | `image_prompts` | 需要信息图/高密度视觉总结 | text skill |
| `skill_baoyu_xhs_images` | 小红书配图设计 | `article_text` | `image_prompts` | 需要小红书/卡片式图片方案 | text skill |
| `skill_baoyu_image_gen` | 文生图 | `image_prompts` | `image_list` | 把提示词变成图片 | 默认不是第三方 provider，而是等待 Codex 内置 imagegen；见第 6 节 |
| `wechat_article_assemble` | 公众号文章装配 | `article_text`, `image_list` | `article_text` | 把封面和插图写回 Markdown | 首图做封面，其余图插入正文；会清理失效相对图片引用 |
| `skill_wechat_upload` | 公众号草稿上传 | `article_text` | `publish_records` | 上传公众号草稿箱 | 高风险真实动作；需要确认；微信凭证目前仍在发布脚本内 |
| `douyin_profile_collect` | 抖音主页采集 | 无 | `profile_links` | 从抖音主页采集作品链接 | 真实模式需主页链接，可能需要 Cookie |
| `douyin_video_download` | 抖音视频下载 | `profile_links` | `video_files` | 下载抖音视频 | 高风险重任务，需确认 |
| `asr_extract` | ASR 文案提取 | `video_files` | `clean_scripts` | 视频转纯文案 | 首次本地模型可能较慢 |
| `script_rewrite` | 文案改写/标题 | `clean_scripts` | `batch_scripts` | 把口播文案改成混剪任务 | 可配置改写 skill |
| `batch_mix` | 批量混剪生成 | `batch_scripts` | `rendered_videos` | 生成短视频成片 | 高风险重任务，需素材库/TTS/FFmpeg |
| `mediapush_publish` | MediaPush 发布 | `rendered_videos` | `publish_records` | 投递发布队列 | 高风险动作；写入 MediaPush inbox |

## 5. 常用链路

公众号文章配图并上传草稿箱：

```text
文章 MD 导入
  -> 文章配图方案
  -> 文生图
  -> 公众号文章装配
  -> 公众号草稿上传
```

短视频生产链路：

```text
抖音主页采集
  -> 抖音视频下载
  -> ASR 文案提取
  -> 文案改写/标题
  -> 批量混剪生成
  -> MediaPush 发布
```

只做文章配图素材：

```text
文章 MD 导入
  -> 文章配图方案
  -> 文生图
```

## 6. Codex 内置生图交接协议

文生图节点现在默认由 Codex 亲自接手，不直接调用即梦/OpenRouter/OpenAI 等第三方生图服务。

标准流程：

1. 运行 `skill_baoyu_image_gen`。
2. 节点输出 `external_action_request`，状态变为 `waiting_external`。
3. 调 `get_external_actions`，读取待处理任务，里面有 prompt、目标输出路径、比例等。
4. Codex 使用内置 `imagegen` 生成图片。
5. 把图片保存到请求指定的 `output_path`。
6. 调 `complete_external_action(node_id, images)` 回填图片路径。
7. 节点变为 `success`，`last_output` 变成标准 `image_list`。
8. 继续运行下游装配/上传节点。

只有用户明确需要第三方备用，或节点参数 `允许第三方备用=true` 时，才走 baoyu-image-gen provider 路径。

## 7. MCP 操作 SOP

搭链路时推荐这样做：

1. `list_nodes`：确认节点类型和端口。
2. `get_workflow`：看当前画布是否已有可复用节点。
3. `add_node`：创建需要的节点。
4. `set_params`：填路径、执行模式、输出目录等关键参数。
5. `connect`：按 `source -> target` 建边。
6. `run_chain` 或 `run_all`：真实高风险节点加 `confirm=true`。
7. `get_output`：检查产物路径和元数据。
8. 如出现 `needs_external_action`，执行第 6 节的 Codex 生图回填。
9. 继续跑下游，直到目标完成。

如果用户问“为什么我没看到你连线”，优先检查：

- 你是否真的通过 MCP `add_node/connect` 改了 `workflows/active.json`。
- GUI 是否正在打开同一个项目目录。
- `get_workflow` 里的节点和边是否存在。
- 是否只是本地生成了文件，但没有在画布中创建节点/连线。

## 8. 运行前检查清单

公众号链路：

- Markdown 文件路径存在。
- 文章配图方案节点有模型 API 配置。
- 文生图默认走 Codex imagegen，不需要第三方 provider key。
- 公众号上传是真实高风险动作，运行时需要确认。
- 上传后要检查 `publish_records` 和后台草稿箱。

短视频链路：

- 抖音主页链接/Cookie 是否必要。
- 下载、混剪、发布都是高风险真实动作。
- ASR 模型和设备参数是否合理。
- 混剪素材库、BGM、TTS、FFmpeg 是否就绪。
- MediaPush 是否会处理 inbox。

## 9. 发生错误时怎么排查

优先顺序：

1. 看节点 `status/error`。
2. 调 `get_output(node_id)`。
3. 调 `get_logs(limit)`。
4. 检查上游输出类型是否符合下游输入。
5. 检查真实模式、高风险确认、路径、凭证、外部工具依赖。
6. 如果是产品 bug，可以顺手修复并加回归测试。

已知历史坑：

- 即梦接口提示词字段曾经错用 `prompt_text`，正确字段是 `prompt`。
- 部分 OpenAI-compatible 模型不支持 `response_format=json_object`，执行器已做自动降级重试。
- 即梦第三方备用模式容易并发 429，已把 Jimeng batch jobs 限为 1。
- 公众号装配前应清理失效的相对本地图片引用，避免草稿里出现死图。

## 10. 上岗口令模板

未来新开对话时，用户可以直接这样说：

```text
项目：J:\MagicTool\个人网站\tools\短视频节点画布工作台
你是这个工作台的外部总控。先读 docs/Codex入职文档-外部总控手册.md、README.md、PROJECT_PROGRESS.md。
通过 video-workbench MCP 连接工作台，先 list_nodes / get_workflow 了解节点和当前画布。
之后按我的目标拆解任务、创建节点、连线、运行、检查产物；遇到文生图默认由你用内置 imagegen 接手并回填。
```

这就是入职手续。读完以后，Codex 应该能像总经理一样进入公司、认识员工、分派任务、接住关键环节，并把结果交回工作台。
