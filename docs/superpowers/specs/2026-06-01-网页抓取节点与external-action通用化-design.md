# 设计：网页正文抓取节点 + external_action 通用化

日期：2026-06-01
状态：已与用户确认，待写实现计划
关联：通用能力积木 - 输入源层（第一批）

## 背景与动机

现有节点几乎全是自媒体专用件（抖音采集/下载、公众号配图/装配/上传）。要让工作台成为**通用工作台**，缺的是领域无关的原子块。用户选定先补**输入源层**，第一批只做一个高杠杆节点：**网页正文抓取**（给 URL → 可读正文 → `article_text`），它能直接接现有的改写/配图/上传链路，组合出"抓文章 → 改写 → 配图 → 发公众号"。

抓取实现方式上，用户选择**复用总控（大脑）的抓取能力**，而不是节点自己装 requests/headless 依赖：节点发起一个外部动作，由作为大脑的 Claude/Codex 用原生 WebFetch 抓取后回填。这与现有"生图走 external_action 让 Codex 内置 imagegen 出图"一脉相承。

值得注意：网页抓取这类动作 **Claude 当大脑就能自己完成**（有 WebFetch），不像生图必须依赖 Codex 内置能力。这正好验证 external_action 协议**不绑定具体由谁执行**。

## 决策（已确认）

| 决策 | 选择 |
|------|------|
| 第一批分层 | 输入源层 |
| 第一批节点 | 仅「网页正文抓取」一个 |
| 抓取策略 | 复用大脑 WebFetch，走 external_action（零依赖） |
| 节点形态 | builtin 节点 + 执行器（类比 `article_md_import`），非 skill |
| 架构增量 | 把 external_action 从「生图专用」通用化为「通用外部动作协议」 |

**YAGNI 砍掉（留待以后）**：批量多 URL、本地静态抓取备用（类比生图的"允许第三方备用"）、headless 渲染。第一版单 URL、纯走大脑。

## 架构：external_action 通用化（本次真正的增量）

当前 external_action 机制是**生图专用**的：
- `get_external_actions` 列出 `status=waiting_external` 且 `last_output.type=external_action_request` 的节点（已通用，无需改）。
- `complete_external_action(node_id, images)` **写死了图片语义**：只接收 `[{id,path}]`，校验图片文件存在，固定产出 `image_list`。

改造为按请求里的 `output_port` 分流产物形态：

- 请求 payload 已带 `output_port`（生图为 `image_list`，抓取为 `article_text`），无需新增字段。
- `complete_external_action(node_id, result)` 改为按节点待办请求的 `output_port` 分流：
  - `output_port == "image_list"`：维持现逻辑（`result` 为 `[{id,path}]` 或 `[path]`，校验文件存在，产出 `image_list`）。
  - `output_port == "article_text"`：`result` 为文本/结构（见数据契约），store 把正文写到 `outputs/web_fetch/<stamp>.md`，产出 `article_text`，`items=[文件路径]`，meta 带 url/title。
  - 其它/未知 `output_port`：返回 `{"completed": false, "reason": "不支持的 output_port: ..."}`。
- 向后兼容：生图现有调用 `complete_external_action(node_id, [{id,path}])` 行为不变（该节点请求的 output_port 即 image_list）。

## 新节点 `web_article_fetch`

### Manifest（models.py，BUILTIN_NODE_SPECS）
- type: `web_article_fetch`
- name: 网页正文抓取
- group: 输入源
- inputs: `[]`
- outputs: `["article_text"]`
- default_params: `{"执行模式": "模拟", "网址": "", "输出格式": "markdown"}`
- risk_level: low，requires_confirmation: false
- capability: `fetch_web_article`
- when_to_use: 内容链路起点。当你有一个文章/网页 URL，需要把正文抓成 article_text 交给改写/配图/上传节点时使用。
- typical_downstream: `["skill_baoyu_article_illustrator", "skill_wechat_upload", "script_rewrite"]`
- param_specs：`网址`(text，必填，URL)、`输出格式`(select: markdown/纯文本)
- output_example: `{"items": ["outputs/web_fetch/web_20260601_120000.md"], "meta": {"source_url": "https://...", "title": "...", "format": "markdown"}}`
- keywords: 网页、抓取、URL、正文、爬取、链接、采集

### 执行器 `_run_web_article_fetch`（tool_executor.py）
真实运行时**不自己抓**，而是构造外部动作请求并返回：

```json
{
  "type": "external_action_request",
  "items": ["<request_file 路径>"],
  "meta": {
    "action": "fetch_webpage",
    "output_port": "article_text",
    "request_file": "<...>/web_fetch_request.json",
    "tasks": [{"id": "1", "url": "<网址>", "format": "markdown", "output_path": "<...>.md"}],
    "count": 1,
    "note": "等待外部大脑(Claude/Codex)用 WebFetch 抓取正文后回写 article_text"
  }
}
```

- 校验 `网址` 非空且为 http(s)，否则 `ToolExecutionError`。
- 工作目录 `outputs/web_fetch/`，request 文件落盘（与生图 request 同构，便于大脑读取）。
- runner 见 `type=external_action_request` → 节点转 `waiting_external` → 进 `summary["needs_external_action"]`（现有逻辑，无需改 runner）。

## 数据契约

### web_article_fetch 外部动作请求
```json
{
  "action": "fetch_webpage",
  "node_type": "web_article_fetch",
  "output_port": "article_text",
  "tasks": [{"id": "1", "url": "https://example.com/post", "format": "markdown", "output_path": "outputs/web_fetch/web_<stamp>.md"}]
}
```

### complete_external_action 的 article_text 回填入参
大脑调用时传文本（任一形态，store 归一化）：
- `result = {"text": "# 标题\n\n正文 markdown...", "title": "标题", "url": "https://..."}`
- 或 `result = "纯 markdown 文本"`（store 视为 text，title/url 留空）

store 行为：把 `text` 写到 `tasks[0].output_path`（或 `outputs/web_fetch/web_<stamp>.md`），产出：
```json
{"type": "article_text", "items": ["<写入的 md 路径>"],
 "meta": {"source_url": "...", "title": "...", "format": "markdown", "completed_from": "external_action_request", "action": "fetch_webpage"}}
```

## 大脑侧工作流（人/Claude/Codex 经 MCP）
1. `run_chain`/`run_node` 跑到 fetch 节点 → 返回 `needs_external_action`，节点 `waiting_external`。
2. `get_external_actions` → 看到 `action=fetch_webpage`，拿到 url。
3. 大脑用原生 WebFetch 抓取 url，提炼可读正文 markdown。
4. `complete_external_action(node_id, {"text": ..., "title": ..., "url": ...})` 回填。
5. 节点变 `success`，下游可继续。

## 组件改动清单
1. **app/models.py**：`BUILTIN_NODE_SPECS` 增 `web_article_fetch`（含 param_specs/manifest 字段）。
2. **app/runtime/tool_executor.py**：
   - `execute()` 增 `web_article_fetch` 分支 → `_run_web_article_fetch`。
   - 新增 `_run_web_article_fetch`（构造 fetch external_action_request）。
3. **app/mcp/store.py**：`complete_external_action` 按 `output_port` 分流，新增 article_text 分支（写文件 + 产出 article_text）。
4. **app/mcp/server.py**：`complete_external_action` 工具签名由 `images` 泛化为 `result`（兼容 list/dict）。
5. **runner.py / get_external_actions**：无需改（已通用）。

## 测试
- **test_mcp_store**：
  - `complete_external_action` 对 article_text 请求：传 text → 节点变 success，产出 article_text，items 为存在的 md 文件，meta 带 url/title。
  - 未知 output_port → `completed: false`。
  - 回归：生图 image_list 完成路径仍通过。
- **test_runner**（或 tool_executor 单测）：fetch 节点真实运行 → `external_action_request`，runner 置 `waiting_external`、进 `needs_external_action`。
- **test 节点加载**：`web_article_fetch` 出现在 NODE_SPEC_BY_TYPE，端口/manifest 字段正确。
- 全量临时 runner 跑通，旧测试不回归。

## 风险与边界
- request 文件与生图同构，大脑读取方式一致，降低协议复杂度。
- complete 入参形态分流靠 `output_port`，是单一真相源（请求里写死），避免大脑乱传。
- 不引入网络依赖到工作台运行时，保持 runtime 纯净。
- 单 URL、无并发、无重试——第一版边界明确，足够验证协议通用性。
