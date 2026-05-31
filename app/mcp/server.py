"""workbench MCP server（stdio）。工具只做参数校验 + 调 app.mcp.store。"""
from __future__ import annotations
from mcp.server.fastmcp import FastMCP
from app.mcp import store as S

mcp = FastMCP("video-workbench")

@mcp.tool()
def list_nodes() -> str:
    """列出全部可用节点类型及其能力/端口/参数（厚 Manifest JSON）。"""
    return S.list_nodes()

@mcp.tool()
def get_workflow() -> dict:
    """当前画布：节点/连线/状态/产物。"""
    return S.load_workflow()

@mcp.tool()
def add_node(type: str, params: dict | None = None, x: int = 120, y: int = 320) -> dict:
    return S.add_node(type, params=params, x=x, y=y)

@mcp.tool()
def connect(source_id: str, target_id: str) -> dict:
    return S.connect(source_id, target_id)

@mcp.tool()
def set_params(node_id: str, params: dict) -> dict:
    return S.set_params(node_id, params)

@mcp.tool()
def delete_node(node_id: str) -> dict:
    return S.delete_node(node_id)

@mcp.tool()
def run_node(node_id: str, confirm: bool = False) -> dict:
    return S.run(start_ids=[node_id], cascade=False, confirm=confirm)

@mcp.tool()
def run_chain(node_id: str, confirm: bool = False) -> dict:
    return S.run(start_ids=[node_id], cascade=True, confirm=confirm)

@mcp.tool()
def run_all(confirm: bool = False) -> dict:
    return S.run(confirm=confirm)

@mcp.tool()
def get_output(node_id: str) -> dict:
    return S.get_output(node_id)

@mcp.tool()
def get_logs(limit: int = 50) -> str:
    return S.get_logs(limit)

@mcp.tool()
def create_skill_node(skill_file: str, mode: str = "text", instruction: str = "", write: bool = False) -> dict:
    return S.create_skill_node(skill_file, mode=mode, instruction=instruction, write=write)

@mcp.tool()
def reload_nodes() -> dict:
    from app.models import reload_node_specs
    reload_node_specs(); return {"reloaded": True}

def main() -> None:
    mcp.run()  # stdio

if __name__ == "__main__":
    main()
