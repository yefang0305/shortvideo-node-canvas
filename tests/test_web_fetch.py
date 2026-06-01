"""网页正文抓取节点 web_article_fetch + external_action article_text 通用化测试。"""
import sys, os
from pathlib import Path
try:
    _TEST_FILE = Path(__file__).resolve()
except NameError:
    _TEST_FILE = Path(os.getcwd()) / "tests" / "test_web_fetch.py"
sys.path.insert(0, str(_TEST_FILE.parents[1]))

from app.models import NODE_SPEC_BY_TYPE, WorkflowNode
from app.runtime.tool_executor import ToolExecutor, ToolExecutionError


def test_web_article_fetch_spec_registered():
    spec = NODE_SPEC_BY_TYPE["web_article_fetch"]
    assert spec.inputs == []
    assert spec.outputs == ["article_text"]
    assert "网址" in spec.default_params
    assert spec.requires_confirmation is False


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
