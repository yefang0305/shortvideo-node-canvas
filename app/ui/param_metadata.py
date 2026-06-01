from __future__ import annotations


VOICE_OPTIONS = [
    ("Vivi 2.0 - 清晰标准女声", "zh_female_vv_uranus_bigtts"),
    ("小何 2.0 - 温柔女声", "zh_female_xiaohe_uranus_bigtts"),
    ("云舟 2.0 - 成熟男声", "zh_male_m191_uranus_bigtts"),
    ("小天 2.0 - 青年男声", "zh_male_taocheng_uranus_bigtts"),
    ("刘飞 2.0 - 活力男声", "zh_male_liufei_uranus_bigtts"),
    ("魅力苏菲 2.0 - 知性女声", "zh_male_sophie_uranus_bigtts"),
    ("孙悟空 2.0 - 活泼男声", "zh_male_sunwukong_uranus_bigtts"),
    ("白玉堂 2.0 - 清冷女声", "zh_female_baiyutang_uranus_bigtts"),
    ("诸葛亮 2.0 - 智慧男声", "zh_male_zhugeliang_uranus_bigtts"),
    ("小燕 2.0 - 甜美女声", "zh_female_xiaoyan_uranus_bigtts"),
    ("Sandy 2.0 - 沉稳男声", "zh_male_sandy_uranus_bigtts"),
    ("知梦 2.0 - 温柔女声", "zh_female_zhimeng_uranus_bigtts"),
    ("东东 2.0 - 正太男声", "zh_male_dongdong_uranus_bigtts"),
    ("悠悠 2.0 - 可爱女声", "zh_female_youyou_uranus_bigtts"),
    ("小丸子 2.0 - 活力女声", "zh_female_xiaowanzi_uranus_bigtts"),
    ("Luna 2.0 - 神秘女声", "zh_female_luna_uranus_bigtts"),
    ("大壹 2.0 - 大气男声", "zh_male_dayi_uranus_bigtts"),
    ("黑猫侦探社咪仔 2.0 - 可爱女声", "zh_female_heimaozhentan_uranus_bigtts"),
    ("鸡汤女 2.0 - 温暖女声", "zh_female_jitangnv_uranus_bigtts"),
    ("魅力女友 2.0 - 温柔女声", "zh_female_meilinvyou_uranus_bigtts"),
    ("流畅女声 2.0 - 自然女声", "zh_female_liuchangnv_uranus_bigtts"),
    ("儒雅逸辰 2.0 - 儒雅男声", "zh_male_ruyayichen_uranus_bigtts"),
    ("Tim - 英文男声", "en_male_tim_uranus_bigtts"),
    ("Dacey - 英文女声", "en_female_dacey_uranus_bigtts"),
    ("Stokie - 英文女声", "en_female_stokie_uranus_bigtts"),
]

SEGMENT_MODE_OPTIONS = [
    ("按文案分段", "按文案分段"),
    ("按时长均分", "按时长均分"),
    ("按数量均分", "按数量均分"),
]
INSERT_IMAGE_OPTIONS = [
    ("按段落均匀插入", "按段落均匀插入"),
    ("追加到文末", "追加到文末"),
]

DEVICE_OPTIONS = [("CPU", "cpu"), ("GPU (CUDA)", "cuda")]
BOOLEAN_SELECT_OPTIONS = [("开启", True), ("关闭", False)]
IMAGE_PROVIDER_OPTIONS = [
    ("Codex 内置 Imagegen", "codex_builtin"),
    ("OpenRouter", "openrouter"),
    ("OpenAI", "openai"),
    ("Google Gemini", "google"),
    ("DashScope 通义万象", "dashscope"),
    ("Replicate", "replicate"),
    ("Jimeng 即梦", "jimeng"),
    ("Seedream 豆包", "seedream"),
]
IMAGE_QUALITY_OPTIONS = [("2K", "2k"), ("普通", "normal")]

FILE_KEYS = {"BGM文件", "封面底图", "Cookie文件", "导出文件", "改写SKILL文件", "MD文件", "封面图"}
DIRECTORY_KEYS = {"素材库", "保存目录", "输出目录", "Inbox目录"}


def options_for_key(key: str) -> list[tuple[str, str]]:
    if key == "音色":
        return VOICE_OPTIONS
    if key == "分段模式":
        return SEGMENT_MODE_OPTIONS
    if key == "插图策略":
        return INSERT_IMAGE_OPTIONS
    if key == "设备":
        return DEVICE_OPTIONS
    if key in {"字幕描边", "字幕阴影"}:
        return BOOLEAN_SELECT_OPTIONS
    if key == "服务商":
        return IMAGE_PROVIDER_OPTIONS
    if key == "质量":
        return IMAGE_QUALITY_OPTIONS
    return []


def editor_kind_for_key(key: str) -> str:
    if key in FILE_KEYS:
        return "file"
    if key in DIRECTORY_KEYS:
        return "directory"
    if options_for_key(key):
        return "select"
    return "default"
