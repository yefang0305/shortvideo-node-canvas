"""失败诊断的大模型客户端。

内置计划器已移除；此处仅保留失败诊断（读节点错误，给可执行排查建议）。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from app.agent.settings import AgentSettings


class LLMClientError(RuntimeError):
    pass


class LLMDiagnoser:
    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings

    def diagnose_error(self, node_name: str, node_type: str, error: str) -> str:
        if not self.settings.api_key.strip():
            raise LLMClientError("未配置 API Key")

        payload = {
            "model": self.settings.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是短视频自动化工作台的故障诊断助手。"
                        "请用中文给出简短、可执行的排查建议。"
                        "不要建议绕过平台风控、验证码或账号安全机制。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"节点名称：{node_name}\n节点类型：{node_type}\n错误信息：{error}",
                },
            ],
            "temperature": 0.2,
        }
        endpoint = self.settings.api_base.rstrip("/") + "/chat/completions"
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            raise LLMClientError(f"诊断失败: {exc}") from exc
