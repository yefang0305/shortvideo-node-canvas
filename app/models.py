from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.manifest import ParamSpec, PortType, PORT_TYPES


@dataclass(frozen=True)
class NodeSpec:
    type: str
    name: str
    group: str
    icon: str
    color: str
    description: str
    inputs: list[str]
    outputs: list[str]
    default_params: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "low"
    requires_confirmation: bool = False
    # 岗位说明书字段（v2 阶段 0）：让总控像管家一样理解每个节点。
    capability: str = ""
    when_to_use: str = ""
    typical_upstream: list[str] = field(default_factory=list)
    typical_downstream: list[str] = field(default_factory=list)
    param_specs: dict[str, ParamSpec] = field(default_factory=dict)
    output_example: Any = None
    # 触发关键词：供规则计划器/总管按自然语言匹配该节点。
    keywords: list[str] = field(default_factory=list)
    # Skill 节点绑定（阶段 4）：非 None 时由通用 skill_node 执行器运行。
    skill_binding: dict[str, Any] | None = None

    def port_type(self, port_name: str) -> PortType:
        """查端口契约；未登记的端口回退到 generic。"""
        return PORT_TYPES.get(port_name, PORT_TYPES["generic"])


@dataclass
class WorkflowNode:
    spec: NodeSpec
    x: float
    y: float
    id: str = field(default_factory=lambda: f"node_{uuid4().hex[:8]}")
    status: str = "idle"
    params: dict[str, Any] = field(default_factory=dict)
    last_output: dict[str, Any] | None = None
    error: str = ""

    def __post_init__(self) -> None:
        if not self.params:
            self.params = dict(self.spec.default_params)


@dataclass
class WorkflowEdge:
    source_id: str
    target_id: str
    id: str = field(default_factory=lambda: f"edge_{uuid4().hex[:8]}")


BUILTIN_NODE_SPECS: list[NodeSpec] = [
    NodeSpec(
        type="article_md_import",
        name="文章 MD 导入",
        group="文章",
        icon="文",
        color="#2f6f9f",
        description="读取本地 Markdown 文档，作为文章正文输入内容链路",
        inputs=[],
        outputs=["article_text"],
        default_params={"执行模式": "模拟", "MD文件": ""},
        capability="import_markdown_article",
        when_to_use="内容链路起点。当你有一篇本地 Markdown 文章，需要交给配图、封面、排版或上传节点时使用。",
        typical_upstream=[],
        typical_downstream=[
            "skill_baoyu_article_illustrator",
            "skill_baoyu_cover_image",
            "skill_wechat_upload",
        ],
        param_specs={
            "MD文件": ParamSpec("MD文件", "Markdown 文件", "要导入的本地文章 .md/.markdown 文件", "选择或填写文章 Markdown 文件路径", "文件不存在或不是 Markdown 时无法导入", "file"),
        },
        output_example={"items": ["# 标题\n\n正文段落……"], "meta": {"source_file": "articles/demo.md", "format": "markdown"}},
        keywords=["md", "markdown", "文章", "导入", "文档"],
    ),
    NodeSpec(
        type="wechat_article_assemble",
        name="公众号文章装配",
        group="公众号",
        icon="装",
        color="#178f6b",
        description="把封面和插图写回 Markdown，输出可直接上传公众号草稿的带图文章",
        inputs=["article_text", "image_list"],
        outputs=["article_text"],
        default_params={
            "执行模式": "模拟",
            "封面图": "",
            "插图策略": "按段落均匀插入",
            "输出目录": "outputs/articles",
        },
        capability="assemble_wechat_markdown_article",
        when_to_use="公众号文章上传前使用。把原始 Markdown 正文与文生图产物合并：首图作为封面，其余图片插入正文，输出新的 Markdown 文件给公众号草稿上传节点。",
        typical_upstream=["article_md_import", "skill_baoyu_image_gen"],
        typical_downstream=["skill_wechat_upload"],
        param_specs={
            "封面图": ParamSpec("封面图", "封面图", "手动指定封面图片路径；留空时使用上游 image_list 的第一张图", "可留空自动取第一张图，也可填本地图片绝对路径", "路径不存在会导致上传封面失败", "file"),
            "插图策略": ParamSpec("插图策略", "插图策略", "正文插图的插入位置策略", "默认按段落均匀插入；也可选择追加到文末", "策略不合适会影响阅读节奏", "select", ["按段落均匀插入", "追加到文末"]),
            "输出目录": ParamSpec("输出目录", "输出目录", "装配后 Markdown 文件保存目录", "默认 outputs/articles", "目录不可写会失败", "dir"),
        },
        output_example={
            "items": ["outputs/articles/assembled_20260531_120000.md"],
            "meta": {"cover_image": "outputs/images/cover.png", "inline_count": 3},
        },
        keywords=["公众号", "装配", "排版", "插入图片", "插图", "封面", "带图文章"],
    ),
    NodeSpec(
        type="douyin_profile_collect",
        name="抖音主页采集",
        group="采集",
        icon="采",
        color="#13776e",
        description="输入主页链接，提取作品链接并导出文档",
        inputs=[],
        outputs=["profile_links"],
        default_params={"执行模式": "模拟", "主页链接": "", "最大采集数量": 50, "Cookie文件": "", "导出文件": "outputs/links.md"},
        capability="collect_douyin_profile_links",
        when_to_use="链路起点。当你只有一个抖音主页链接、需要拿到该账号下的作品链接列表时使用。",
        typical_upstream=[],
        typical_downstream=["douyin_video_download"],
        param_specs={
            "主页链接": ParamSpec("主页链接", "主页链接", "要采集的抖音账号主页 URL", "粘贴目标账号主页完整链接，形如 https://www.douyin.com/user/xxx", "留空则无法采集，运行直接失败", "text"),
            "最大采集数量": ParamSpec("最大采集数量", "最大采集数量", "本次最多采集多少条作品", "按需填数字，默认 50", "过大可能触发风控或耗时变长", "number"),
            "Cookie文件": ParamSpec("Cookie文件", "Cookie 文件", "登录态 Cookie 文件路径，用于采集受限内容", "可留空；需要登录态时指向导出的 cookie 文件", "留空时部分主页可能采集不全", "file"),
            "导出文件": ParamSpec("导出文件", "导出文件", "作品链接导出的 Markdown 路径", "默认 outputs/links.md，可改", "路径不可写会导出失败", "text"),
        },
        output_example={"items": [{"url": "https://www.douyin.com/video/7xxxxxxx", "title": "示例作品标题"}], "meta": {"count": 1}},
    ),
    NodeSpec(
        type="douyin_video_download",
        name="抖音视频下载",
        group="下载",
        icon="下",
        color="#2459a8",
        description="批量下载抖音作品，支持 CR TubeGet 运行时",
        inputs=["profile_links"],
        outputs=["video_files"],
        default_params={"执行模式": "模拟", "保存目录": "outputs/downloads", "并发数": 3, "跳过已下载": True},
        risk_level="medium",
        requires_confirmation=True,
        capability="download_douyin_videos",
        when_to_use="已经拿到作品链接（profile_links）、需要把视频下载到本地时使用。",
        typical_upstream=["douyin_profile_collect"],
        typical_downstream=["asr_extract"],
        param_specs={
            "保存目录": ParamSpec("保存目录", "保存目录", "视频下载到本地的目录", "默认 outputs/downloads，可改为绝对路径", "目录不可写会下载失败", "dir"),
            "并发数": ParamSpec("并发数", "并发数", "同时下载的任务数", "默认 3，网络好可调高", "过高易触发风控或限速", "number"),
            "跳过已下载": ParamSpec("跳过已下载", "跳过已下载", "是否跳过目录中已存在的视频", "建议开启以便断点续传", "关闭会重复下载、浪费时间", "bool"),
        },
        output_example={"items": ["outputs/downloads/7xxxxxxx.mp4"], "meta": {"count": 1, "failed": 0}},
    ),
    NodeSpec(
        type="asr_extract",
        name="ASR 文案提取",
        group="文案",
        icon="字",
        color="#9b5a10",
        description="导入视频或音频，输出纯口播文案 TXT",
        inputs=["video_files"],
        outputs=["clean_scripts"],
        default_params={
            "执行模式": "模拟",
            "ASR 模式": "本地模型",
            "模型": "small",
            "设备": "cpu",
            "启用过滤器": True,
            "LLM优化错别字断句": True,
            "输出格式": "TXT纯文案",
            "输出目录": "outputs/scripts",
        },
        capability="extract_speech_script",
        when_to_use="拿到本地视频/音频（video_files）后，需要把口播内容转成纯文本文案时使用。",
        typical_upstream=["douyin_video_download"],
        typical_downstream=["script_rewrite"],
        param_specs={
            "ASR 模式": ParamSpec("ASR 模式", "ASR 模式", "用本地模型还是云端引擎转写", "默认本地模型，无网络/要省钱时合适", "云端模式需配置密钥", "select", ["本地模型", "火山引擎"]),
            "模型": ParamSpec("模型", "模型", "本地 Whisper 模型规格", "默认 small（速度/精度均衡），可选 base/medium/large", "越大越准但越慢、越吃内存", "select", ["base", "small", "medium", "large"]),
            "设备": ParamSpec("设备", "设备", "推理设备", "默认 cpu；有可用 GPU 可填 cuda", "cuda 无效环境会回退或报错", "select", ["cpu", "cuda"]),
            "LLM优化错别字断句": ParamSpec("LLM优化错别字断句", "LLM 优化", "是否调大模型修正错别字与断句", "建议开启以提升文案质量", "开启会增加一次大模型调用耗时", "bool"),
            "输出目录": ParamSpec("输出目录", "输出目录", "文案 txt 的输出目录", "默认 outputs/scripts", "目录不可写会失败", "dir"),
        },
        output_example={"items": ["outputs/scripts/7xxxxxxx.txt"], "meta": {"count": 1, "format": "TXT纯文案"}},
    ),
    NodeSpec(
        type="script_rewrite",
        name="文案改写/标题",
        group="文案",
        icon="改",
        color="#6650b8",
        description="生成短视频风格标题与可混剪脚本",
        inputs=["clean_scripts"],
        outputs=["batch_scripts"],
        default_params={"执行模式": "模拟", "改写SKILL文件": "", "改写风格": "爆款短视频", "标题规则": "≤16字", "每条输出": 1, "输出目录": "outputs/batch_tasks"},
        capability="rewrite_script_and_title",
        when_to_use="拿到口播文案（clean_scripts）后，需要改写成爆款风格并生成标题、整理成可混剪任务时使用。",
        typical_upstream=["asr_extract"],
        typical_downstream=["batch_mix"],
        param_specs={
            "改写SKILL文件": ParamSpec("改写SKILL文件", "改写 Skill 文件", "改写风格遵循的 skill/提示词文件", "可留空用默认风格；指向自定义 skill 文件可定制风格", "留空则用内置默认改写策略", "file"),
            "改写风格": ParamSpec("改写风格", "改写风格", "目标文案风格", "如“爆款短视频”“知识口播”", "风格与素材不匹配会影响成片效果", "text"),
            "标题规则": ParamSpec("标题规则", "标题规则", "标题生成约束", "如“≤16字”“带数字钩子”", "规则过松标题可能偏长", "text"),
            "每条输出": ParamSpec("每条输出", "每条输出", "每条文案改写出几个版本", "默认 1，要 A/B 测试可调高", "调高会成倍增加下游混剪量", "number"),
            "输出目录": ParamSpec("输出目录", "输出目录", "batch_tasks.json 的输出目录", "默认 outputs/batch_tasks", "目录不可写会失败", "dir"),
        },
        output_example={"items": [{"title": "示例爆款标题", "segments": ["第一句口播", "第二句口播"]}], "meta": {"count": 1}},
    ),
    NodeSpec(
        type="batch_mix",
        name="批量混剪生成",
        group="生产",
        icon="剪",
        color="#1f7a4a",
        description="素材、BGM、字幕、封面组合输出成片",
        inputs=["batch_scripts"],
        outputs=["rendered_videos"],
        default_params={
            "执行模式": "模拟",
            "TTS App ID": "",
            "TTS Token": "",
            "TTS Resource ID": "seed-tts-2.0",
            "音色": "zh_female_zhimeng_uranus_bigtts",
            "语速": "1.0",
            "音量": 100,
            "分段模式": "按文案分段",
            "均分时长秒数": "3.0",
            "均分段数": 6,
            "最短分段秒数": "1.8",
            "素材库": "materials",
            "BGM文件": "",
            "BGM音量": 30,
            "输出分辨率": "1080x1920",
            "输出帧率": 30,
            "生成数量": 1,
            "输出目录": "outputs/videos",
            "封面底图": "",
            "字幕字体": "Microsoft YaHei",
            "字幕字号": 52,
            "字幕颜色": "&H00FFFFFF",
            "字幕位置Y": 80,
            "字幕描边": True,
            "描边颜色": "&H00000000",
            "描边粗细": 2,
            "字幕阴影": True,
            "最大字数": 0,
            "字幕偏移秒": "0.15",
        },
        risk_level="medium",
        requires_confirmation=True,
        capability="batch_render_videos",
        when_to_use="拿到混剪任务（batch_scripts）、且素材库/TTS/FFmpeg 就绪后，批量合成成品视频时使用。",
        typical_upstream=["script_rewrite"],
        typical_downstream=["mediapush_publish"],
        param_specs={
            "TTS App ID": ParamSpec("TTS App ID", "TTS App ID", "火山 TTS 应用 ID", "从 TTS 控制台获取", "缺失则无法生成配音", "text"),
            "TTS Token": ParamSpec("TTS Token", "TTS Token", "火山 TTS 访问令牌", "从 TTS 控制台获取", "缺失则无法生成配音", "text"),
            "音色": ParamSpec("音色", "音色", "TTS 发音人", "填音色 ID，默认 zh_female_zhimeng_uranus_bigtts", "音色 ID 无效会合成失败", "text"),
            "素材库": ParamSpec("素材库", "素材库", "随机匹配画面用的视频素材目录", "指向有效素材目录，默认 materials", "素材不足会导致成片重复或失败", "dir"),
            "BGM文件": ParamSpec("BGM文件", "BGM 文件", "背景音乐文件", "可留空；指向音频文件可加 BGM", "留空则无背景音乐", "file"),
            "输出分辨率": ParamSpec("输出分辨率", "输出分辨率", "成片分辨率", "默认 1080x1920（竖屏）", "与素材比例不符会有黑边", "text"),
            "生成数量": ParamSpec("生成数量", "生成数量", "本次生成几条成片", "默认 1，按需调高", "调高会显著增加耗时", "number"),
            "输出目录": ParamSpec("输出目录", "输出目录", "成片输出目录", "默认 outputs/videos", "目录不可写会失败", "dir"),
            "字幕字体": ParamSpec("字幕字体", "字幕字体", "ASS 字幕使用的系统字体名", "默认 Microsoft YaHei；可填系统已安装字体", "字体不存在时可能回退或显示异常", "text"),
            "字幕字号": ParamSpec("字幕字号", "字幕字号", "ASS 字幕字号", "默认 52；竖屏常用 48-64", "过大容易遮挡画面", "number"),
            "字幕颜色": ParamSpec("字幕颜色", "字幕颜色", "ASS 字幕颜色（ABGR 格式）", "默认 &H00FFFFFF；例如黄色可填 &H0000FFFF", "格式错误会导致字幕颜色异常", "text"),
            "字幕位置Y": ParamSpec("字幕位置Y", "字幕位置 Y", "字幕垂直位置百分比，越大越靠底部", "默认 80；底部附近可填 80-90", "过高或过低会遮挡主体/越界", "number"),
            "字幕描边": ParamSpec("字幕描边", "字幕描边", "是否给字幕加描边", "建议开启，复杂画面中更清晰", "关闭后浅色背景可能看不清", "select", ["开启", "关闭"]),
            "描边颜色": ParamSpec("描边颜色", "描边颜色", "ASS 描边颜色（ABGR 格式）", "默认黑色 &H00000000", "格式错误会导致描边异常", "text"),
            "描边粗细": ParamSpec("描边粗细", "描边粗细", "字幕描边粗细", "默认 2；需要强对比可调到 3-4", "过粗会显得笨重", "number"),
            "字幕阴影": ParamSpec("字幕阴影", "字幕阴影", "是否给字幕加阴影", "默认开启", "关闭后字幕层次感降低", "select", ["开启", "关闭"]),
            "最大字数": ParamSpec("最大字数", "最大字数", "单行字幕最大字数，0 表示自动按宽度计算", "默认 0；想强制短行可填 10-16", "过小会频繁换行", "number"),
            "字幕偏移秒": ParamSpec("字幕偏移秒", "字幕偏移秒", "字幕相对语音的时间偏移", "默认 0.15；字幕慢/快时微调", "偏移过大会明显不同步", "number"),
        },
        output_example={"items": ["outputs/videos/0001.mp4"], "meta": {"count": 1, "resolution": "1080x1920"}},
    ),
    NodeSpec(
        type="mediapush_publish",
        name="MediaPush 发布",
        group="发布",
        icon="发",
        color="#9f3838",
        description="多账号定时发布、失败记录与补发",
        inputs=["rendered_videos"],
        outputs=["publish_records"],
        default_params={"执行模式": "模拟", "Inbox目录": "J:\\MagicTool\\emdia\\MediaPush\\inbox", "发布时间": "", "时段名": "manual", "复制文件": True},
        risk_level="high",
        requires_confirmation=True,
        capability="publish_via_mediapush",
        when_to_use="链路终点。拿到成品视频（rendered_videos）后，写入 MediaPush 发布队列时使用。高风险动作。",
        typical_upstream=["batch_mix"],
        typical_downstream=[],
        param_specs={
            "Inbox目录": ParamSpec("Inbox目录", "Inbox 目录", "MediaPush 监听的投递目录", "指向 MediaPush 的 inbox 目录", "路径错误会导致 MediaPush 发现不到批次", "dir"),
            "发布时间": ParamSpec("发布时间", "发布时间", "定时发布时间，留空为立即", "留空立即；定时填如 2026-06-01 20:00", "格式错误会被忽略或排期失败", "text"),
            "时段名": ParamSpec("时段名", "时段名", "批次时段标签，便于归类", "默认 manual，可填 morning/evening 等", "仅用于归类，不影响发布", "text"),
            "复制文件": ParamSpec("复制文件", "复制文件", "投递时复制还是移动成片", "建议复制以保留源文件", "选移动会从输出目录搬走原文件", "bool"),
        },
        output_example={"items": [{"video": "0001.mp4", "status": "queued", "batch": "manual"}], "meta": {"count": 1}},
    ),
]


def load_node_specs() -> list[NodeSpec]:
    specs = list(BUILTIN_NODE_SPECS)
    custom_path = Path(__file__).resolve().parent / "nodes" / "custom_nodes.json"
    if custom_path.exists():
        data = json.loads(custom_path.read_text(encoding="utf-8"))
        for item in data.get("nodes", []):
            specs.append(
                NodeSpec(
                    type=item["type"],
                    name=item["name"],
                    group=item.get("group", "自定义"),
                    icon=item.get("icon", "节"),
                    color=item.get("color", "#2459a8"),
                    description=item.get("description", ""),
                    inputs=list(item.get("inputs", [])),
                    outputs=list(item.get("outputs", ["generic"])),
                    default_params=dict(item.get("default_params", {"执行模式": "模拟"})),
                    risk_level=item.get("risk_level", "low"),
                    requires_confirmation=bool(item.get("requires_confirmation", False)),
                    when_to_use=item.get("when_to_use", ""),
                    capability=item.get("capability", ""),
                    typical_upstream=list(item.get("typical_upstream", [])),
                    typical_downstream=list(item.get("typical_downstream", [])),
                    output_example=item.get("output_example"),
                    keywords=list(item.get("keywords", [])),
                    skill_binding=item.get("skill_binding"),
                )
            )
    return specs


NODE_SPECS = load_node_specs()
NODE_SPEC_BY_TYPE = {spec.type: spec for spec in NODE_SPECS}


def reload_node_specs() -> list[NodeSpec]:
    """重新加载节点库（含新造的自定义节点），原地更新全局对象。

    必须 mutate 现有 list/dict 而非重新赋值——其它模块以引用方式 import 了它们。
    """
    specs = load_node_specs()
    NODE_SPECS.clear()
    NODE_SPECS.extend(specs)
    NODE_SPEC_BY_TYPE.clear()
    NODE_SPEC_BY_TYPE.update({spec.type: spec for spec in specs})
    return NODE_SPECS
