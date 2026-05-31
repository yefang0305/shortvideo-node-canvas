from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = PROJECT_ROOT.parent


@dataclass(frozen=True)
class EnvironmentItem:
    name: str
    ok: bool
    detail: str
    path: str = ""


def check_environment() -> list[EnvironmentItem]:
    return [
        _check_python(),
        _check_ffmpeg(),
        _check_batch_ffmpeg(),
        _check_crtubeget(),
        _check_tool_dir("抖音主页链接采集", ["app.py", "core/profile_extractor.py"]),
        _check_tool_dir("抖音视频下载", ["app.py", "downloader.py"]),
        _check_tool_dir("抖音文案提取", ["cli.py", "asr_engine.py"]),
        _check_tool_dir("抖音批量视频生成", ["main.py", "core/video_composer.py"]),
        _check_mediapush(),
    ]


def _check_python() -> EnvironmentItem:
    return EnvironmentItem(
        name="Python",
        ok=True,
        detail=sys.version.split()[0],
        path=sys.executable,
    )


def _check_ffmpeg() -> EnvironmentItem:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return EnvironmentItem("FFmpeg", True, _version_line([ffmpeg, "-version"]), ffmpeg)
    candidates = [
        PROJECT_ROOT / "ffmpeg" / "ffmpeg.exe",
        TOOLS_ROOT / "抖音批量视频生成" / "ffmpeg" / "ffmpeg.exe",
        Path(r"J:\MagicTool\Standalone\VideoCut\video_tool\ffmpeg\ffmpeg.exe"),
    ]
    for bundled in candidates:
        if bundled.exists():
            return EnvironmentItem("FFmpeg", True, "可用 ffmpeg.exe", str(bundled))
    return EnvironmentItem("FFmpeg", False, "未在 PATH、画布项目、批量混剪项目或原工作台 ffmpeg/ 目录找到 ffmpeg")


def _check_batch_ffmpeg() -> EnvironmentItem:
    ffmpeg_dir = TOOLS_ROOT / "抖音批量视频生成" / "ffmpeg"
    ffmpeg = ffmpeg_dir / "ffmpeg.exe"
    ffprobe = ffmpeg_dir / "ffprobe.exe"
    dlls = list(ffmpeg_dir.glob("*.dll")) if ffmpeg_dir.exists() else []
    if ffmpeg.exists() and ffprobe.exists() and dlls:
        return EnvironmentItem("批量混剪 FFmpeg", True, f"ffmpeg.exe / ffprobe.exe / {len(dlls)} 个 DLL 已就绪", str(ffmpeg_dir))
    missing = []
    if not ffmpeg.exists():
        missing.append("ffmpeg.exe")
    if not ffprobe.exists():
        missing.append("ffprobe.exe")
    if not dlls:
        missing.append("FFmpeg DLL")
    return EnvironmentItem("批量混剪 FFmpeg", False, "缺少: " + ", ".join(missing), str(ffmpeg_dir))


def _check_crtubeget() -> EnvironmentItem:
    runtime = TOOLS_ROOT / "抖音视频下载" / "crtubeget_runtime"
    qjs = runtime / "qjs.exe"
    if qjs.exists():
        return EnvironmentItem("CR TubeGet Runtime", True, "qjs.exe 已就绪", str(runtime))
    return EnvironmentItem("CR TubeGet Runtime", False, "未找到 qjs.exe", str(runtime))


def _check_tool_dir(name: str, required_files: list[str]) -> EnvironmentItem:
    tool_dir = TOOLS_ROOT / name
    missing = [item for item in required_files if not (tool_dir / item).exists()]
    if not tool_dir.exists():
        return EnvironmentItem(name, False, "工具目录不存在", str(tool_dir))
    if missing:
        return EnvironmentItem(name, False, "缺少: " + ", ".join(missing), str(tool_dir))
    return EnvironmentItem(name, True, "目录和关键文件已就绪", str(tool_dir))


def _check_mediapush() -> EnvironmentItem:
    root = Path(r"J:\MagicTool\emdia\MediaPush")
    missing = [item for item in ["main.py", "inbox", "profiles", "data"] if not (root / item).exists()]
    if not root.exists():
        return EnvironmentItem("MediaPush", False, "MediaPush 项目目录不存在", str(root))
    if missing:
        return EnvironmentItem("MediaPush", False, "缺少: " + ", ".join(missing), str(root))
    return EnvironmentItem("MediaPush", True, "项目、inbox、profiles、data 已就绪", str(root))


def _version_line(cmd: list[str]) -> str:
    try:
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=5,
            startupinfo=startupinfo,
        )
    except Exception as exc:
        return f"可执行文件存在，但版本检查失败: {exc}"
    first_line = (result.stdout or result.stderr).splitlines()
    return first_line[0] if first_line else "可执行文件存在"
