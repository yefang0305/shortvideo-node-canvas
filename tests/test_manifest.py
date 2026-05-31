"""阶段 0：节点说明书（Node Manifest）完整性校验。"""

from __future__ import annotations

import json

from app.agent.planner import node_protocol_prompt
from app.manifest import PORT_TYPES, best_connection, describe_port, ports_compatible
from app.models import BUILTIN_NODE_SPECS, NODE_SPEC_BY_TYPE


def test_every_port_has_a_contract():
    """每个内置节点用到的端口名都必须在 PORT_TYPES 注册。"""
    for spec in BUILTIN_NODE_SPECS:
        for port in list(spec.inputs) + list(spec.outputs):
            assert port in PORT_TYPES, f"{spec.type} 的端口 {port} 未在 PORT_TYPES 登记"


def test_builtin_nodes_have_job_description():
    """每个内置节点都要有能力标签与“何时使用”，否则管家无从派活。"""
    for spec in BUILTIN_NODE_SPECS:
        assert spec.capability, f"{spec.type} 缺少 capability"
        assert spec.when_to_use, f"{spec.type} 缺少 when_to_use"
        assert spec.output_example is not None, f"{spec.type} 缺少 output_example"


def test_typical_neighbors_point_to_real_nodes():
    """典型上下游必须指向真实存在的节点类型。"""
    for spec in BUILTIN_NODE_SPECS:
        for neighbor in list(spec.typical_upstream) + list(spec.typical_downstream):
            assert neighbor in NODE_SPEC_BY_TYPE, f"{spec.type} 的相邻节点 {neighbor} 不存在"


def test_chain_is_connectable():
    """抖音链路相邻节点的输出端口应与下游输入端口契约一致。"""
    chain = [
        "douyin_profile_collect",
        "douyin_video_download",
        "asr_extract",
        "script_rewrite",
        "batch_mix",
        "mediapush_publish",
    ]
    for up, down in zip(chain, chain[1:]):
        up_outputs = set(NODE_SPEC_BY_TYPE[up].outputs)
        down_inputs = set(NODE_SPEC_BY_TYPE[down].inputs)
        assert up_outputs & down_inputs, f"{up} 输出与 {down} 输入端口不匹配"


def test_same_port_is_compatible():
    assert ports_compatible("video_files", "video_files")


def test_unrelated_ports_are_incompatible():
    assert not ports_compatible("profile_links", "clean_scripts")


def test_generic_port_is_permissive():
    assert ports_compatible("rendered_videos", "generic")
    assert ports_compatible("generic", "clean_scripts")


def test_best_connection_finds_matching_pair():
    dl = NODE_SPEC_BY_TYPE["douyin_video_download"]
    asr = NODE_SPEC_BY_TYPE["asr_extract"]
    assert best_connection(dl.outputs, asr.inputs) == ("video_files", "video_files")


def test_best_connection_rejects_mismatch():
    collect = NODE_SPEC_BY_TYPE["douyin_profile_collect"]
    asr = NODE_SPEC_BY_TYPE["asr_extract"]
    assert best_connection(collect.outputs, asr.inputs) is None


def test_describe_port_is_human_readable():
    assert describe_port("video_files") == "本地视频文件列表/file_list"


def test_protocol_prompt_is_valid_thick_manifest():
    """node_protocol_prompt 必须是合法 JSON，且每个节点带端口 Schema 与参数说明。"""
    data = json.loads(node_protocol_prompt())
    assert isinstance(data, list) and data
    for entry in data:
        for key in ("type", "capability", "when_to_use", "inputs", "outputs", "params"):
            assert key in entry, f"manifest 缺少字段 {key}"
        for port in entry["inputs"] + entry["outputs"]:
            assert {"port", "label", "kind", "item"} <= set(port)
