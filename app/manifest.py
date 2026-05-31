"""节点自描述协议的底层数据模型。

这是一个叶子模块，不依赖 app 内其它模块，供 models / planner 等导入。

- PortType：端口的数据契约（流过这个端口的数据长什么样）。
- ParamSpec：单个参数的填写说明书。
- PORT_TYPES：全局端口契约注册表，端口名即键。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PortType:
    """端口的数据契约。端口名（name）同时也是连线匹配键。"""

    name: str
    label: str
    kind: str  # file_list / text_list / json / records / image_list / text
    item: str
    description: str
    example: Any = None


@dataclass(frozen=True)
class ParamSpec:
    """单个参数的填写说明书，供总控理解“这个参数怎么配”。"""

    key: str
    label: str
    meaning: str
    how_to_fill: str
    consequence: str = ""
    widget: str = "text"  # text / number / bool / select / file / dir
    options: list[str] = field(default_factory=list)


# 端口契约注册表：所有节点 inputs/outputs 用到的端口名都应在此登记。
PORT_TYPES: dict[str, PortType] = {
    "profile_links": PortType(
        name="profile_links",
        label="作品链接列表",
        kind="json",
        item="一条抖音作品信息（链接 + 标题）",
        description="抖音主页采集得到的作品链接集合，是整条链路的起点数据。",
        example={
            "items": [
                {"url": "https://www.douyin.com/video/7xxxxxxx", "title": "示例作品标题"},
            ],
            "meta": {"count": 1, "source": "douyin_profile"},
        },
    ),
    "video_files": PortType(
        name="video_files",
        label="本地视频文件列表",
        kind="file_list",
        item="一个本地视频文件路径（.mp4）",
        description="下载或生成得到的本地视频文件路径集合。仅保存路径与统计，不内嵌大文件。",
        example={
            "items": ["outputs/downloads/7xxxxxxx.mp4"],
            "meta": {"count": 1, "failed": 0},
        },
    ),
    "clean_scripts": PortType(
        name="clean_scripts",
        label="纯口播文案列表",
        kind="file_list",
        item="一个纯口播文案 .txt 文件路径",
        description="ASR 提取并清洗后的纯文本口播文案。调试副产物（md/json）不走此端口。",
        example={
            "items": ["outputs/scripts/7xxxxxxx.txt"],
            "meta": {"count": 1, "format": "TXT纯文案"},
        },
    ),
    "batch_scripts": PortType(
        name="batch_scripts",
        label="混剪任务脚本",
        kind="json",
        item="一条可供混剪的任务（标题 + 分段文案）",
        description="文案改写后产出的结构化批量任务，供批量混剪节点消费（batch_tasks.json）。",
        example={
            "items": [
                {"title": "示例爆款标题", "segments": ["第一句口播", "第二句口播"]},
            ],
            "meta": {"count": 1, "tasks_file": "outputs/batch_tasks/batch_tasks.json"},
        },
    ),
    "rendered_videos": PortType(
        name="rendered_videos",
        label="成品视频列表",
        kind="file_list",
        item="一个成品视频文件路径（含封面/字幕/BGM）",
        description="批量混剪生成的成片集合，供发布节点消费。",
        example={
            "items": ["outputs/videos/0001.mp4"],
            "meta": {"count": 1, "resolution": "1080x1920"},
        },
    ),
    "publish_records": PortType(
        name="publish_records",
        label="发布记录",
        kind="records",
        item="一条发布记录（账号 / 状态 / 时间）",
        description="发布节点写入 inbox 后产生的发布记录，供后续核验与补发。",
        example={
            "items": [
                {"video": "0001.mp4", "status": "queued", "batch": "manual"},
            ],
            "meta": {"count": 1, "inbox": "...inbox/batch_xxx"},
        },
    ),
    "generic": PortType(
        name="generic",
        label="通用数据",
        kind="json",
        item="任意结构化数据",
        description="未声明具体契约的通用端口，用于自定义节点占位。",
        example={"items": [], "meta": {}},
    ),
    # —— 内容创作场景端口（阶段 4 Skill 节点用）——
    "article_text": PortType(
        name="article_text",
        label="文章正文",
        kind="text_list",
        item="一篇文章的纯文本/Markdown",
        description="公众号、小红书等写作类 skill 的输入或产物正文。",
        example={"items": ["# 标题\n\n正文段落……"], "meta": {"count": 1}},
    ),
    "image_prompts": PortType(
        name="image_prompts",
        label="配图方案/提示词",
        kind="json",
        item="一条配图建议（位置 + 提示词 + 风格）",
        description="配图类 skill 产出的图像生成方案，可直接喂给图像后端。",
        example={
            "items": [{"position": "开头", "prompt": "极简蓝图风格的流程示意", "style": "blueprint"}],
            "meta": {"count": 1},
        },
    ),
    "image_list": PortType(
        name="image_list",
        label="图片文件列表",
        kind="image_list",
        item="一个本地图片文件路径",
        description="图像后端真实出图后的图片文件集合。",
        example={"items": ["outputs/images/0001.png"], "meta": {"count": 1}},
    ),
    "score_report": PortType(
        name="score_report",
        label="评分报告",
        kind="records",
        item="一条评分结果（维度 + 分数 + 建议）",
        description="评分类 skill（如公众号文章评分）产出的结构化报告。",
        example={
            "items": [{"dimension": "标题吸引力", "score": 8, "advice": "可加数字钩子"}],
            "meta": {"count": 1, "total": 82},
        },
    ),
}


# 显式声明的端口兼容关系：键 = 下游输入端口名，值 = 可接受的上游输出端口名集合。
# 端口名相同时天然兼容，无需在此登记；这里只登记“名字不同但数据契约可对接”的关系。
# 例如未来若有节点输出 generic 文本想接入 clean_scripts，可在此声明。
PORT_COMPATIBILITY: dict[str, set[str]] = {}


def describe_port(port_name: str) -> str:
    """把端口名渲染成人类可读的契约描述，用于连线提示。"""
    port = PORT_TYPES.get(port_name)
    return f"{port.label}/{port.kind}" if port else port_name


def ports_compatible(output_port: str, input_port: str) -> bool:
    """判断上游输出端口能否接入下游输入端口（同名天然兼容 + 显式声明兼容）。"""
    if output_port == input_port:
        return True
    if input_port == "generic" or output_port == "generic":
        return True  # 通用端口作为占位，放行
    return output_port in PORT_COMPATIBILITY.get(input_port, set())


def best_connection(outputs: list[str], inputs: list[str]) -> tuple[str, str] | None:
    """在上游输出与下游输入之间找一对可兼容的端口；找不到返回 None。"""
    for out_port in outputs:
        for in_port in inputs:
            if ports_compatible(out_port, in_port):
                return out_port, in_port
    return None
