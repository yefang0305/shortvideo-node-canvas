# 网页正文抓取节点 + external_action 通用化 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `web_article_fetch` 节点，给 URL 走 external_action 让大脑(Claude/Codex)用 WebFetch 抓正文回填 article_text；并把 external_action 的完成回填从生图专用通用化为按 `output_port` 分流。

**Architecture:** 节点真实运行时不自己抓网页，而是落一个 `external_action_request`（action=`fetch_webpage`，output_port=`article_text`），节点转 `waiting_external`；大脑经 MCP `get_external_actions` 取请求、用 WebFetch 抓取、`complete_external_action` 回填。`complete_external_action` 按待办请求的 `output_port` 分流产物形态（image_list 维持原样，article_text 写文件产出）。

**Tech Stack:** Python 3.13（纯 stdlib，无新增依赖）、现有 app/ 模块、临时 runner 跑测试（本机无 pytest）。

---

## 运行环境约定（实现者必读）

- **不要用 `python`**：本机 `python` 是 Windows 商店坏 stub（exit 49 无输出）。真实解释器：
  `C:\Users\ASUS\AppData\Local\Programs\Python\Python313\python.exe`
- **无 pytest**。测试用临时 runner 调用 `test_*` 函数，给用了 `tmp_path` 的测试注入临时目录。
- 跑单个测试文件的临时 runner（PowerShell，设 UTF-8）：

```powershell
$env:PYTHONIOENCODING="utf-8"
$PY="C:\Users\ASUS\AppData\Local\Programs\Python\Python313\python.exe"
& $PY -X utf8 -c @'
import sys, inspect, tempfile, importlib.util
from pathlib import Path
sys.path.insert(0, ".")
mod_path = sys.argv[1]
spec = importlib.util.spec_from_file_location("t", mod_path)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
fails=0
for name, fn in inspect.getmembers(m, inspect.isfunction):
    if not name.startswith("test_"): continue
    kw={}
    if "tmp_path" in inspect.signature(fn).parameters:
        kw["tmp_path"]=Path(tempfile.mkdtemp())
    try:
        fn(**kw); print("PASS", name)
    except Exception as e:
        fails+=1; print("FAIL", name, repr(e))
sys.exit(1 if fails else 0)
'@ tests\test_mcp_store.py
```

把末尾的 `tests\test_mcp_store.py` 换成目标测试文件即可。Git 提交信息结尾加：
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## File Structure（改动地图）

| 文件 | 职责 | 改动 |
|------|------|------|
| `app/models.py` | 节点 Manifest 定义 | 在 `BUILTIN_NODE_SPECS` 增 `web_article_fetch` spec |
| `app/runtime/tool_executor.py` | 节点真实执行器 | `execute()` 加分支 + 新增 `_run_web_article_fetch` |
| `app/runtime/runner.py` | 无 Qt 执行核 | `_MOCK` 加 `web_article_fetch` 假数据 |
| `app/mcp/store.py` | 工作流仓库 | `complete_external_action` 按 `output_port` 分流 |
| `app/mcp/server.py` | MCP 工具层 | `complete_external_action` 签名 `images`→`result` |
| `tests/test_web_fetch.py` | 新测试 | 节点加载 + 执行器 external_action 输出 |
| `tests/test_mcp_store.py` | 现有测试 | 加 article_text 完成 + 未知 port 用例 |

实现顺序：先做 store 通用化（②③，含回归），再做节点（④⑤⑥），最后端到端串测（⑦）。每个 Task 独立可测、独立提交。

---

## Task 1: store.complete_external_action 按 output_port 分流（保留生图回归）

**Files:**
- Modify: `app/mcp/store.py`（`complete_external_action` 函数）
- Test: `tests/test_mcp_store.py`

- [ ] **Step 1: 写失败测试（article_text 完成 + 未知 port）**

在 `tests/test_mcp_store.py` 末尾追加：

```python
def test_complete_external_article_action_writes_article_text(tmp_path):
    p = tmp_path / "active.json"
    node_id = S.add_node("web_article_fetch", path=p)["id"]
    out_md = tmp_path / "web_x.md"

    wf = S.load_workflow(p)
    wf["nodes"][0]["status"] = "waiting_external"
    wf["nodes"][0]["last_output"] = {
        "type": "external_action_request",
        "items": [str(tmp_path / "request.json")],
        "meta": {
            "action": "fetch_webpage",
            "output_port": "article_text",
            "tasks": [{"id": "1", "url": "https://example.com/post",
                       "output_path": str(out_md)}],
        },
    }
    S.save_workflow(wf, p)

    result = S.complete_external_action(
        node_id,
        {"text": "# 标题\n\n正文 markdown", "title": "标题", "url": "https://example.com/post"},
        path=p,
    )

    assert result["completed"] is True
    output = S.get_output(node_id, path=p)["last_output"]
    assert output["type"] == "article_text"
    assert output["items"] == [str(out_md)]
    assert Path(out_md).read_text(encoding="utf-8").startswith("# 标题")
    assert output["meta"]["source_url"] == "https://example.com/post"
    assert output["meta"]["title"] == "标题"


def test_complete_external_unknown_port_rejected(tmp_path):
    p = tmp_path / "active.json"
    node_id = S.add_node("web_article_fetch", path=p)["id"]
    wf = S.load_workflow(p)
    wf["nodes"][0]["status"] = "waiting_external"
    wf["nodes"][0]["last_output"] = {
        "type": "external_action_request",
        "items": [],
        "meta": {"action": "weird", "output_port": "score_report", "tasks": []},
    }
    S.save_workflow(wf, p)
    result = S.complete_external_action(node_id, {"text": "x"}, path=p)
    assert result["completed"] is False
    assert "output_port" in result["reason"]
```

文件顶部确认已 `from pathlib import Path`（已有）。

- [ ] **Step 2: 跑测试确认失败**

用「运行环境约定」的临时 runner 跑 `tests\test_mcp_store.py`。
预期：两个新测试 FAIL（当前 `complete_external_action` 只处理图片，article_text 请求会因缺 path 报错或产出 image_list）；旧测试仍 PASS。

- [ ] **Step 3: 改 `complete_external_action` 按 output_port 分流**

把 `app/mcp/store.py` 的 `complete_external_action` 整体替换为：

```python
def complete_external_action(
    node_id: str,
    result: list[dict[str, str]] | list[str] | dict[str, str] | str,
    path: Path | None = None,
) -> dict[str, Any]:
    """外部大脑完成动作后回写产物，按请求的 output_port 分流形态。

    - image_list：result 为 [{id,path}] 或 [path]，校验文件存在。
    - article_text：result 为 {text,title?,url?} 或纯文本，写文件后产出 article_text。
    """
    wf = load_workflow(path)
    for nd in wf["nodes"]:
        if nd["id"] != node_id:
            continue
        last = nd.get("last_output") or {}
        if last.get("type") != "external_action_request":
            return {"completed": False, "reason": f"节点不是外部动作等待态：{node_id}"}
        meta = last.get("meta", {})
        output_port = meta.get("output_port", "image_list")

        if output_port == "image_list":
            built = _build_image_list_output(result, meta)
        elif output_port == "article_text":
            built = _build_article_text_output(result, meta)
        else:
            return {"completed": False, "reason": f"不支持的 output_port：{output_port}"}
        if not built.get("ok"):
            return {"completed": False, "reason": built["reason"]}

        nd["status"] = "success"
        nd["error"] = ""
        nd["last_output"] = built["output"]
        save_workflow(wf, path)
        return {"completed": True, "id": node_id, **built.get("extra", {})}
    return {"completed": False, "reason": f"节点不存在：{node_id}"}


def _build_image_list_output(result: Any, meta: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, list):
        return {"ok": False, "reason": "image_list 动作需要图片列表 [{id,path}]"}
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(result):
        if isinstance(item, dict):
            img_id = str(item.get("id") or index)
            img_path = str(item.get("path") or item.get("output_path") or "")
        else:
            img_id = str(index)
            img_path = str(item)
        if not img_path:
            return {"ok": False, "reason": f"第 {index + 1} 张图片缺少 path"}
        if not Path(img_path).exists():
            return {"ok": False, "reason": f"图片不存在：{img_path}"}
        normalized.append({"id": img_id, "path": img_path})
    return {
        "ok": True,
        "extra": {"count": len(normalized)},
        "output": {
            "type": "image_list",
            "items": [img["path"] for img in normalized],
            "meta": {
                "images": normalized,
                "count": len(normalized),
                "completed_from": "external_action_request",
                "action": meta.get("action", ""),
            },
        },
    }


def _build_article_text_output(result: Any, meta: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result, dict):
        text = str(result.get("text") or result.get("markdown") or "")
        title = str(result.get("title") or "")
        url = str(result.get("url") or "")
    else:
        text = str(result or "")
        title = ""
        url = ""
    if not text.strip():
        return {"ok": False, "reason": "article_text 动作需要非空正文 text"}

    tasks = meta.get("tasks") or []
    if tasks and tasks[0].get("output_path"):
        out_path = Path(tasks[0]["output_path"])
    else:
        out_dir = PROJECT_ROOT / "outputs" / "web_fetch"
        out_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        out_path = out_dir / f"web_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text.strip() + "\n", encoding="utf-8")
    if not url and tasks:
        url = str(tasks[0].get("url", ""))
    return {
        "ok": True,
        "output": {
            "type": "article_text",
            "items": [str(out_path)],
            "meta": {
                "source_url": url,
                "title": title,
                "format": "markdown",
                "completed_from": "external_action_request",
                "action": meta.get("action", ""),
            },
        },
    }
```

确认 `store.py` 顶部已 `from typing import Any`、`from pathlib import Path`、有 `PROJECT_ROOT`（已有）。

- [ ] **Step 4: 跑测试确认通过**

临时 runner 跑 `tests\test_mcp_store.py`。
预期：全 PASS（含原 `test_complete_external_image_action_writes_image_list` 回归 + 两个新用例）。

- [ ] **Step 5: 提交**

```bash
git add app/mcp/store.py tests/test_mcp_store.py
git commit -m "feat: external_action 完成回填按 output_port 分流（支持 article_text）"
```

---

## Task 2: MCP server 工具签名泛化（images → result）

**Files:**
- Modify: `app/mcp/server.py`（`complete_external_action` 工具）

- [ ] **Step 1: 改工具签名**

把 `app/mcp/server.py` 中：

```python
@mcp.tool()
def complete_external_action(node_id: str, images: list[dict] | list[str]) -> dict:
    """外部 Codex 完成动作后回写产物；生图时 images 为 [{id,path}]。"""
    return S.complete_external_action(node_id, images)
```

替换为：

```python
@mcp.tool()
def complete_external_action(node_id: str, result: list | dict | str) -> dict:
    """外部大脑完成动作后回写产物。生图：result=[{id,path}]；网页抓取：result={text,title,url}。"""
    return S.complete_external_action(node_id, result)
```

- [ ] **Step 2: 冒烟导入检查**

```powershell
$env:PYTHONIOENCODING="utf-8"
& "C:\Users\ASUS\AppData\Local\Programs\Python\Python313\python.exe" -X utf8 -c "import app.mcp.server; print('server import ok')"
```
预期：输出 `server import ok`，无异常。

- [ ] **Step 3: 提交**

```bash
git add app/mcp/server.py
git commit -m "refactor: complete_external_action MCP 工具签名 images→result"
```

---

## Task 3: 新增 web_article_fetch 节点 Manifest

**Files:**
- Modify: `app/models.py`（`BUILTIN_NODE_SPECS`）
- Test: `tests/test_web_fetch.py`（新建）

- [ ] **Step 1: 写失败测试（节点加载 + 端口/字段）**

新建 `tests/test_web_fetch.py`：

```python
import sys, os
from pathlib import Path
try:
    _TEST_FILE = Path(__file__).resolve()
except NameError:
    _TEST_FILE = Path(os.getcwd()) / "tests" / "test_web_fetch.py"
sys.path.insert(0, str(_TEST_FILE.parents[1]))

from app.models import NODE_SPEC_BY_TYPE


def test_web_article_fetch_spec_registered():
    spec = NODE_SPEC_BY_TYPE["web_article_fetch"]
    assert spec.inputs == []
    assert spec.outputs == ["article_text"]
    assert "网址" in spec.default_params
    assert spec.requires_confirmation is False
```

- [ ] **Step 2: 跑测试确认失败**

临时 runner 跑 `tests\test_web_fetch.py`。
预期：FAIL，`KeyError: 'web_article_fetch'`。

- [ ] **Step 3: 加节点 spec**

在 `app/models.py` 的 `BUILTIN_NODE_SPECS` 列表里（紧跟 `article_md_import` 之后）插入：

```python
    NodeSpec(
        type="web_article_fetch",
        name="网页正文抓取",
        group="输入源",
        icon="网",
        color="#3a6ea5",
        description="给一个网页 URL，抓取可读正文（Markdown）作为文章正文输入",
        inputs=[],
        outputs=["article_text"],
        default_params={"执行模式": "模拟", "网址": "", "输出格式": "markdown"},
        capability="fetch_web_article",
        when_to_use="内容链路起点。当你有一个文章/网页 URL，需要把正文抓成 article_text 交给改写、配图或上传节点时使用。抓取由外部大脑(Claude/Codex)用 WebFetch 完成。",
        typical_upstream=[],
        typical_downstream=[
            "skill_baoyu_article_illustrator",
            "skill_wechat_upload",
            "script_rewrite",
        ],
        param_specs={
            "网址": ParamSpec("网址", "网页地址", "要抓取正文的网页 URL", "粘贴文章完整链接，形如 https://...", "留空或非 http(s) 链接无法抓取", "text"),
            "输出格式": ParamSpec("输出格式", "输出格式", "正文抓取后的文本格式", "默认 markdown，也可纯文本", "格式不影响下游，按需选择", "select", ["markdown", "纯文本"]),
        },
        output_example={"items": ["outputs/web_fetch/web_20260601_120000.md"], "meta": {"source_url": "https://example.com/post", "title": "示例标题", "format": "markdown"}},
        keywords=["网页", "抓取", "url", "正文", "爬取", "链接", "采集"],
    ),
```

确认 `ParamSpec` 已在 `models.py` 定义（已有）。

- [ ] **Step 4: 跑测试确认通过**

临时 runner 跑 `tests\test_web_fetch.py`。预期：PASS。

- [ ] **Step 5: 提交**

```bash
git add app/models.py tests/test_web_fetch.py
git commit -m "feat: 新增网页正文抓取节点 web_article_fetch Manifest"
```

---

## Task 4: web_article_fetch 真实执行器（发 external_action）

**Files:**
- Modify: `app/runtime/tool_executor.py`（`execute()` 分支 + 新增方法）
- Test: `tests/test_web_fetch.py`

- [ ] **Step 1: 写失败测试（真实运行产出 external_action_request）**

在 `tests/test_web_fetch.py` 追加：

```python
from app.models import WorkflowNode
from app.runtime.tool_executor import ToolExecutor, ToolExecutionError


def test_fetch_real_emits_external_action(tmp_path):
    spec = NODE_SPEC_BY_TYPE["web_article_fetch"]
    node = WorkflowNode(spec, 0, 0)
    node.params = {"执行模式": "真实", "网址": "https://example.com/post", "输出格式": "markdown"}
    out = ToolExecutor().execute(node, [])
    assert out["type"] == "external_action_request"
    assert out["meta"]["action"] == "fetch_webpage"
    assert out["meta"]["output_port"] == "article_text"
    assert out["meta"]["tasks"][0]["url"] == "https://example.com/post"
    assert out["meta"]["count"] == 1
    req = Path(out["meta"]["request_file"])
    assert req.exists()


def test_fetch_rejects_empty_url():
    spec = NODE_SPEC_BY_TYPE["web_article_fetch"]
    node = WorkflowNode(spec, 0, 0)
    node.params = {"执行模式": "真实", "网址": "", "输出格式": "markdown"}
    try:
        ToolExecutor().execute(node, [])
        assert False, "应抛 ToolExecutionError"
    except ToolExecutionError:
        pass
```

确认 `WorkflowNode` 构造签名（`spec, x, y`）与现有用法一致（见 test_gui_smoke 用 `WorkflowNode(NODE_SPEC_BY_TYPE[...], 0, 0)`）。

- [ ] **Step 2: 跑测试确认失败**

临时 runner 跑 `tests\test_web_fetch.py`。
预期：新两个测试 FAIL（`execute` 命中 `raise ToolExecutionError("...还没有真实执行器")`）。

- [ ] **Step 3: 加 execute 分支 + 执行器方法**

在 `app/runtime/tool_executor.py` 的 `execute()` 里，`article_md_import` 分支旁边加：

```python
        if node.spec.type == "web_article_fetch":
            return _stamp_output_finished_at(self._run_web_article_fetch(node))
```

在类内新增方法（可放 `_run_article_md_import` 附近）：

```python
    def _run_web_article_fetch(self, node: WorkflowNode) -> dict[str, Any]:
        url = str(node.params.get("网址", "")).strip()
        if not url or not url.lower().startswith(("http://", "https://")):
            raise ToolExecutionError("网址为空或不是 http(s) 链接，无法抓取")
        fmt = str(node.params.get("输出格式", "markdown")).strip() or "markdown"

        work_dir = _absolute_path("outputs/web_fetch")
        work_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = (work_dir / f"web_{stamp}.md").resolve()
        request_path = work_dir / f"web_fetch_request_{stamp}.json"

        task = {"id": "1", "url": url, "format": fmt, "output_path": str(output_path)}
        request_payload = {
            "action": "fetch_webpage",
            "node_type": node.spec.type,
            "output_port": "article_text",
            "tasks": [task],
        }
        request_path.write_text(json.dumps(request_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "type": "external_action_request",
            "items": [str(request_path)],
            "meta": {
                "action": "fetch_webpage",
                "output_port": "article_text",
                "request_file": str(request_path),
                "tasks": [task],
                "count": 1,
                "note": "等待外部大脑(Claude/Codex)用 WebFetch 抓取正文后回写 article_text",
            },
        }
```

确认文件顶部已 import `json`、`datetime`，且有 `_absolute_path`、`_stamp_output_finished_at`（均已有，生图执行器在用）。

- [ ] **Step 4: 跑测试确认通过**

临时 runner 跑 `tests\test_web_fetch.py`。预期：全 PASS。

- [ ] **Step 5: 提交**

```bash
git add app/runtime/tool_executor.py tests/test_web_fetch.py
git commit -m "feat: web_article_fetch 真实执行器发起 fetch_webpage 外部动作"
```

---

## Task 5: 模拟模式 mock 数据

**Files:**
- Modify: `app/runtime/runner.py`（`_MOCK`）
- Test: `tests/test_runner.py`

- [ ] **Step 1: 写失败测试（模拟模式产出 article_text）**

在 `tests/test_runner.py` 末尾追加（参照该文件现有 import 风格；若已 import `WorkflowRunner`/`WorkflowNode`/`WorkflowEdge` 则复用）：

```python
def test_web_fetch_mock_outputs_article_text():
    from app.models import NODE_SPEC_BY_TYPE, WorkflowNode
    from app.runtime.runner import WorkflowRunner
    spec = NODE_SPEC_BY_TYPE["web_article_fetch"]
    node = WorkflowNode(spec, 0, 0)
    node.params = {"执行模式": "模拟", "网址": "https://example.com"}
    nodes = {node.id: node}
    summary = WorkflowRunner().run_sync(nodes, [], start_ids=[node.id])
    assert node.id in summary["ran"]
    assert node.status == "success"
    assert node.last_output["type"] == "article_text"
```

- [ ] **Step 2: 跑测试确认失败**

临时 runner 跑 `tests\test_runner.py`。
预期：FAIL（mock 落到默认 `["outputs/result.json"]`，但 `type` 取自 `spec.outputs[0]` = `article_text`，断言 type 可能已过——实际失败点是 mock items 不像文章）。
> 注：若 `type` 断言已通过，本任务主要价值是给 mock 一份像样的假正文文件路径，避免下游误解。仍按下step加 mock 条目。

- [ ] **Step 3: 加 mock 条目**

在 `app/runtime/runner.py` 的 `_MOCK` 字典里加一行：

```python
    "web_article_fetch": ["outputs/web_fetch/mock-article.md"],
```

- [ ] **Step 4: 跑测试确认通过**

临时 runner 跑 `tests\test_runner.py`。预期：PASS。

- [ ] **Step 5: 提交**

```bash
git add app/runtime/runner.py tests/test_runner.py
git commit -m "feat: web_article_fetch 模拟模式 mock 数据"
```

---

## Task 6: 端到端串测 + 全量回归

**Files:**
- Test: 全量 `tests/`

- [ ] **Step 1: 端到端 store 流（真实运行→waiting_external→回填→success）**

在 `tests/test_web_fetch.py` 追加：

```python
def test_fetch_end_to_end_via_store(tmp_path):
    from app.mcp import store as S
    p = tmp_path / "active.json"
    nid = S.add_node("web_article_fetch", params={"执行模式": "真实", "网址": "https://example.com/x"}, path=p)["id"]

    summary = S.run(start_ids=[nid], cascade=True, confirm=True, path=p)
    assert any(a["id"] == nid for a in summary["needs_external_action"])

    actions = S.get_external_actions(path=p)
    assert actions and actions[0]["action"] == "fetch_webpage"

    done = S.complete_external_action(
        nid, {"text": "# 抓到的标题\n\n正文", "title": "抓到的标题", "url": "https://example.com/x"}, path=p,
    )
    assert done["completed"] is True
    out = S.get_output(nid, path=p)["last_output"]
    assert out["type"] == "article_text"
    assert Path(out["items"][0]).read_text(encoding="utf-8").startswith("# 抓到的标题")
```

- [ ] **Step 2: 跑该文件确认通过**

临时 runner 跑 `tests\test_web_fetch.py`。预期：全 PASS。

- [ ] **Step 3: 全量回归**

依次用临时 runner 跑全部 `tests\test_*.py`（重点：`test_mcp_store.py`、`test_image_gen_batch.py`、`test_Marker_pipeline.py`、`test_runner.py`、`test_gui_smoke.py`、`test_manifest.py`）。
预期：全绿，生图 external_action 路径不回归。
> GUI 测试需 `QT_QPA_PLATFORM=offscreen`（文件内已设）。

- [ ] **Step 4: 提交**

```bash
git add tests/test_web_fetch.py
git commit -m "test: web_article_fetch 端到端 + 外部动作回填串测"
```

---

## 验收标准

1. `web_article_fetch` 出现在节点库，端口 `[] → article_text`，可经 MCP `add_node`/`connect`。
2. 真实运行 → 节点 `waiting_external`，`get_external_actions` 列出 `fetch_webpage` 请求带 url。
3. `complete_external_action(node_id, {"text":...})` → 节点 `success`，产出 `article_text`，正文写入 `outputs/web_fetch/*.md`，meta 带 source_url/title。
4. 生图 `image_list` 完成路径回归通过。
5. 未知 output_port 被拒。
6. 全量测试绿。

## 边界（YAGNI，不在本计划）

- 批量多 URL、上游 URL 列表输入。
- 本地静态抓取备用（requests/headless）。
- 抓取重试/超时/反爬处理（由大脑 WebFetch 自行承担）。
