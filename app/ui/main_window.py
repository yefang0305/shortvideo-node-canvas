from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QFileSystemWatcher, QMimeData, QPointF, QSize, Qt, QTimer
from PyQt5.QtGui import QDrag
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QComboBox,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.agent.llm_client import LLMClientError, LLMDiagnoser
from app.agent.settings import AgentSettings, load_agent_settings, save_agent_settings
from app.mcp import store as workflow_store
from app.models import NODE_SPEC_BY_TYPE, NODE_SPECS, WorkflowEdge, WorkflowNode
from app.runtime.engine import RuntimeEngine
from app.runtime.environment import check_environment
from app.runtime.output_summary import format_output_summary
from app.runtime.run_logger import RunLogger
from app.ui.canvas import CanvasScene, CanvasView
from app.ui.param_metadata import editor_kind_for_key, options_for_key
from app.ui.theme import APP_QSS


class NodeLibrary(QListWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setDragEnabled(True)
        self.setSpacing(6)
        self._populate()

    def _populate(self) -> None:
        groups: dict[str, list] = {}
        for spec in NODE_SPECS:
            groups.setdefault(spec.group, []).append(spec)

        for group, specs in groups.items():
            header = QListWidgetItem(group)
            header.setFlags(Qt.NoItemFlags)
            header.setSizeHint(QSize(220, 26))
            header.setData(Qt.UserRole, "")
            header.setData(Qt.UserRole + 1, "group")
            self.addItem(header)
            for spec in specs:
                item = QListWidgetItem(f"{spec.icon}  {spec.name}\n{spec.description}")
                item.setSizeHint(QSize(220, 58))
                item.setData(Qt.UserRole + 1, "node")
                item.setData(Qt.UserRole + 2, spec.color)
                item.setData(Qt.UserRole, spec.type)
                self.addItem(item)

    def reload(self) -> None:
        """节点库热重载（造节点入库后调用）。"""
        self.clear()
        self._populate()

    def current_node_type(self) -> str | None:
        item = self.currentItem()
        if not item or item.data(Qt.UserRole + 1) != "node":
            return None
        return item.data(Qt.UserRole)

    def startDrag(self, actions) -> None:
        node_type = self.current_node_type()
        if not node_type:
            return
        mime = QMimeData()
        mime.setData("application/x-videoops-node", node_type.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec_(Qt.CopyAction)


class MetricCard(QFrame):
    def __init__(self, title: str, value: str = "0") -> None:
        super().__init__()
        self.setObjectName("MetricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("MetricValue")
        title_label = QLabel(title)
        title_label.setObjectName("Muted")
        layout.addWidget(self.value_label)
        layout.addWidget(title_label)

    def set_value(self, value: int | str) -> None:
        self.value_label.setText(str(value))


class MainWindow(QMainWindow):
    def __init__(self, active_path=None) -> None:
        super().__init__()
        self.setWindowTitle("短视频节点画布工作台")
        self.resize(1440, 860)
        self.scene = CanvasScene()
        self.view = CanvasView(self.scene)
        self.engine = RuntimeEngine()
        self.run_logger = RunLogger(Path(__file__).resolve().parents[2] / "runs")
        self.agent_settings = load_agent_settings()
        self.current_node_id: str | None = None
        self._active_path = active_path if active_path is not None else workflow_store.ACTIVE_PATH
        self._last_rev = 0
        self._loading_active = False
        self._active_watcher = QFileSystemWatcher(self)
        self._active_reload_timer = QTimer(self)
        self._active_reload_timer.setSingleShot(True)
        self._active_reload_timer.setInterval(150)

        self._build_ui()
        self._connect_signals()
        self._setup_active_sync()
        self._load_active_or_seed()
        self._update_metrics()
        self._refresh_environment()
        self._log(f"运行日志文件：{self.run_logger.path}")

    def _build_ui(self) -> None:
        root = QSplitter(Qt.Horizontal)
        root.addWidget(self._build_sidebar())
        root.addWidget(self.view)
        root.addWidget(self._build_inspector())
        root.setSizes([280, 820, 360])
        self.setCentralWidget(root)
        self._build_toolbar()

    def _build_toolbar(self) -> None:
        self.run_node_btn = QPushButton("运行当前节点")
        self.run_node_btn.setObjectName("PrimaryButton")
        self.run_downstream_btn = QPushButton("从这里继续运行")
        self.run_all_btn = QPushButton("运行全部流程")
        self.connect_btn = QPushButton("连接选中节点")
        self.delete_btn = QPushButton("删除节点")
        self.diagnose_btn = QPushButton("诊断失败")
        self.save_btn = QPushButton("保存流程")
        self.load_btn = QPushButton("加载流程")
        self._last_connect_source: str | None = None
        bar = self.addToolBar("主工具栏")
        bar.addWidget(self.run_node_btn)
        bar.addWidget(self.run_downstream_btn)
        bar.addWidget(self.run_all_btn)
        bar.addSeparator()
        bar.addWidget(self.connect_btn)
        bar.addWidget(self.delete_btn)
        bar.addWidget(self.diagnose_btn)
        bar.addSeparator()
        bar.addWidget(self.save_btn)
        bar.addWidget(self.load_btn)

    def _build_sidebar(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        title = QLabel("节点库")
        title.setObjectName("Muted")
        count = QLabel(f"{len(NODE_SPECS)} 个核心节点")
        count.setObjectName("Muted")
        title_row = QHBoxLayout()
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(count)
        self.library = NodeLibrary()
        layout.addLayout(title_row)
        layout.addWidget(self.library)
        hint = QLabel("拖拽节点到画布，或双击快速添加。")
        hint.setObjectName("Muted")
        layout.addWidget(hint)
        return panel

    def _build_inspector(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        self.tabs = QTabWidget()
        self.param_tab = QWidget()
        param_layout = QVBoxLayout(self.param_tab)
        self.node_card = QFrame()
        self.node_card.setObjectName("NodeCard")
        node_card_layout = QVBoxLayout(self.node_card)
        self.node_title = QLabel("未选择节点")
        self.node_title.setObjectName("NodeTitle")
        self.node_desc = QLabel("在画布中选择一个节点后编辑参数。")
        self.node_desc.setObjectName("Muted")
        self.node_desc.setWordWrap(True)
        node_card_layout.addWidget(self.node_title)
        node_card_layout.addWidget(self.node_desc)
        metric_row = QHBoxLayout()
        self.metric_total = MetricCard("节点")
        self.metric_running = MetricCard("运行中")
        self.metric_failed = MetricCard("失败")
        metric_row.addWidget(self.metric_total)
        metric_row.addWidget(self.metric_running)
        metric_row.addWidget(self.metric_failed)
        self.param_form_widget = QWidget()
        self.param_form = QFormLayout(self.param_form_widget)
        self.output_preview = QTextEdit()
        self.output_preview.setReadOnly(True)
        self.output_preview.setMinimumHeight(160)
        param_layout.addWidget(self.node_card)
        param_layout.addLayout(metric_row)
        param_layout.addWidget(self.param_form_widget)
        param_layout.addWidget(QLabel("最近输出"))
        param_layout.addWidget(self.output_preview)
        param_layout.addStretch(1)
        self.agent_tab = self._build_agent_tab()
        self.env_tab = self._build_env_tab()
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.tabs.addTab(self.param_tab, "参数")
        self.tabs.addTab(self.agent_tab, "设置")
        self.tabs.addTab(self.env_tab, "环境")
        self.tabs.addTab(self.log_box, "运行")
        layout.addWidget(self.tabs)
        return panel

    def _build_agent_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.api_base_input = QLineEdit(self.agent_settings.api_base)
        self.model_input = QLineEdit(self.agent_settings.model)
        self.api_key_input = QLineEdit(self.agent_settings.api_key)
        self.api_key_input.setEchoMode(QLineEdit.Password)
        settings_form = QFormLayout()
        settings_form.addRow(QLabel("API Base"), self.api_base_input)
        settings_form.addRow(QLabel("模型"), self.model_input)
        settings_form.addRow(QLabel("API Key"), self.api_key_input)
        cred_hint = QLabel("其它服务密钥（出图/发布等）在 config/credentials.json 配置。")
        cred_hint.setObjectName("Muted")
        cred_hint.setWordWrap(True)
        self.agent_output = QTextEdit()
        self.agent_output.setReadOnly(True)
        layout.addWidget(QLabel("模型 API 配置"))
        layout.addLayout(settings_form)
        layout.addWidget(cred_hint)
        layout.addWidget(QLabel("失败诊断"))
        layout.addWidget(self.agent_output)
        return tab

    def _build_env_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.env_summary = QLabel("尚未检测")
        self.env_summary.setObjectName("NodeTitle")
        self.env_output = QTextEdit()
        self.env_output.setReadOnly(True)
        self.env_refresh_btn = QPushButton("刷新环境检测")
        self.env_refresh_btn.setObjectName("PrimaryButton")
        layout.addWidget(self.env_summary)
        layout.addWidget(self.env_refresh_btn)
        layout.addWidget(self.env_output)
        return tab

    def _connect_signals(self) -> None:
        self.library.itemDoubleClicked.connect(self._add_library_node)
        self.view.node_dropped.connect(self.scene.add_node)
        self.scene.node_selected.connect(self._show_node_params)
        self.scene.selection_cleared.connect(self._clear_params)
        self.scene.node_changed.connect(self._update_metrics)
        self.scene.node_changed.connect(self._autosave)
        self.scene.edge_rejected.connect(self._log)
        self.run_node_btn.clicked.connect(self._run_current_node)
        self.run_downstream_btn.clicked.connect(self._run_from_current)
        self.run_all_btn.clicked.connect(self._run_all)
        self.connect_btn.clicked.connect(self._connect_selected_nodes)
        self.delete_btn.clicked.connect(self._delete_selected_nodes)
        self.diagnose_btn.clicked.connect(self._diagnose_current_error)
        self.save_btn.clicked.connect(self._save_workflow)
        self.load_btn.clicked.connect(self._load_workflow)
        self.env_refresh_btn.clicked.connect(self._refresh_environment)
        self.engine.node_started.connect(lambda node_id: (self._refresh_node(node_id), self._autosave()))
        self.engine.node_finished.connect(lambda node_id, _: (self._refresh_node(node_id), self._autosave()))
        self.engine.node_failed.connect(lambda node_id, _: (self._refresh_node(node_id), self._autosave()))
        self.engine.log.connect(self._log)
        self._active_watcher.fileChanged.connect(self._on_active_file_changed)
        self._active_reload_timer.timeout.connect(self._reload_from_disk)

    def _setup_active_sync(self) -> None:
        self._watch_active_path()

    def _watch_active_path(self) -> None:
        path = str(self._active_path)
        for watched in self._active_watcher.files():
            if watched != path:
                self._active_watcher.removePath(watched)
        if self._active_path.exists() and path not in self._active_watcher.files():
            self._active_watcher.addPath(path)

    def _load_active_or_seed(self) -> None:
        data = workflow_store.load_workflow(self._active_path)
        if data.get("nodes"):
            self._load_workflow_data(data, preserve_ids=True)
            self._last_rev = int(data.get("rev", 0))
            self._watch_active_path()
            return
        self._seed_demo()
        self._autosave()

    def _seed_demo(self) -> None:
        first = self.scene.add_node("douyin_profile_collect", QPointF(80, 100))
        second = self.scene.add_node("douyin_video_download", QPointF(360, 100))
        third = self.scene.add_node("asr_extract", QPointF(640, 100))
        self.scene.add_edge(first.id, second.id)
        self.scene.add_edge(second.id, third.id)

    def _add_library_node(self, item: QListWidgetItem) -> None:
        if item.data(Qt.UserRole + 1) != "node":
            return
        offset = 80 + len(self.scene.nodes) * 26
        self.scene.add_node(item.data(Qt.UserRole), QPointF(offset, offset))

    def _show_node_params(self, node_id: str) -> None:
        self.current_node_id = node_id
        node = self.scene.nodes[node_id]
        self.node_title.setText(node.spec.name)
        self.node_desc.setText(node.spec.description)
        while self.param_form.rowCount():
            self.param_form.removeRow(0)
        self.param_form.addRow(QLabel("节点"), QLabel(node.spec.name))
        self.param_form.addRow(QLabel("状态"), QLabel(node.status))
        for key, value in node.params.items():
            self.param_form.addRow(QLabel(str(key)), self._param_editor(key, value))
        for name in self._credential_refs(node):
            self.param_form.addRow(QLabel("需要凭证"), QLabel(f"{name}（在 config/credentials.json 配置）"))
        if node.last_output:
            self.param_form.addRow(QLabel("最近输出"), QLabel(node.last_output["type"]))
        if node.error:
            self.param_form.addRow(QLabel("错误"), QLabel(node.error))
        self.output_preview.setPlainText(format_output_summary(node.last_output))

    @staticmethod
    def _credential_refs(node: WorkflowNode) -> list[str]:
        """从节点 skill_binding 的 env/args 里解析出引用的凭证服务名（去重）。"""
        binding = node.spec.skill_binding or {}
        refs: list[str] = []
        values = list((binding.get("env") or {}).values()) + list(binding.get("args") or [])
        for raw in values:
            text = str(raw)
            if text.startswith("{cred:") and text.endswith("}"):
                refs.append(text[len("{cred:"):-1].split(".")[0])
        return list(dict.fromkeys(refs))

    def _clear_params(self) -> None:
        self.current_node_id = None
        self.node_title.setText("未选择节点")
        self.node_desc.setText("在画布中选择一个节点后编辑参数。")
        while self.param_form.rowCount():
            self.param_form.removeRow(0)
        self.output_preview.setPlainText("暂无输出。")

    def _update_param(self, key: str, value: str) -> None:
        if not self.current_node_id:
            return
        node = self.scene.nodes[self.current_node_id]
        node.params[key] = value
        self.scene.node_items[node.id].update()
        self._autosave()

    def _param_editor(self, key: str, value):
        if key == "执行模式":
            combo = QComboBox()
            combo.addItems(["模拟", "真实"])
            combo.setCurrentText(str(value) if str(value) in {"模拟", "真实"} else "模拟")
            combo.currentTextChanged.connect(lambda text, key=key: self._update_param(key, text))
            return combo
        options = options_for_key(key)
        if options:
            combo = QComboBox()
            for label, data in options:
                combo.addItem(label, data)
            current = str(value)
            index = combo.findData(current)
            if index < 0:
                index = combo.findText(current)
            combo.setCurrentIndex(max(index, 0))
            combo.currentIndexChanged.connect(
                lambda _, key=key, combo=combo: self._update_param(key, combo.currentData() or combo.currentText())
            )
            return combo
        if isinstance(value, bool):
            combo = QComboBox()
            combo.addItems(["True", "False"])
            combo.setCurrentText("True" if value else "False")
            combo.currentTextChanged.connect(lambda text, key=key: self._update_param(key, text == "True"))
            return combo
        if isinstance(value, int):
            spin = QSpinBox()
            spin.setRange(0, 100000)
            spin.setValue(value)
            spin.valueChanged.connect(lambda number, key=key: self._update_param(key, number))
            return spin
        kind = editor_kind_for_key(key)
        if kind in {"file", "directory"}:
            return self._path_editor(key, value, kind)
        edit = QLineEdit(str(value))
        edit.editingFinished.connect(lambda key=key, edit=edit: self._update_param(key, edit.text()))
        return edit

    def _path_editor(self, key: str, value, kind: str) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        edit = QLineEdit(str(value))
        button = QPushButton("选择")
        button.setFixedWidth(54)
        edit.editingFinished.connect(lambda key=key, edit=edit: self._update_param(key, edit.text()))
        button.clicked.connect(lambda _, key=key, edit=edit, kind=kind: self._browse_path(key, edit, kind))
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return wrapper

    def _browse_path(self, key: str, edit: QLineEdit, kind: str) -> None:
        current = edit.text().strip()
        start = str(Path(current).parent if current and kind == "file" else Path(current or "."))
        if kind == "directory":
            selected = QFileDialog.getExistingDirectory(self, f"选择{key}", start)
        else:
            selected, _ = QFileDialog.getOpenFileName(self, f"选择{key}", start, "所有文件 (*.*)")
        if selected:
            edit.setText(selected)
            self._update_param(key, selected)

    def _run_current_node(self) -> None:
        node = self._current_node()
        if node and self._confirm_node_run(node):
            self.engine.run_node(node, self._upstream_outputs(node.id))

    def _run_from_current(self) -> None:
        node = self._current_node()
        if node:
            self._run_chain([node.id])

    def _run_all(self) -> None:
        roots = [node_id for node_id in self.scene.nodes if not self._incoming(node_id)]
        self._run_chain(roots or list(self.scene.nodes))

    def _run_chain(self, start_ids: list[str]) -> None:
        scope: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in scope:
                return
            scope.add(node_id)
            for edge in self.scene.edges:
                if edge.source_id == node_id:
                    visit(edge.target_id)

        for start_id in start_ids:
            visit(start_id)

        for node_id in scope:
            self.scene.nodes[node_id].status = "idle"
            self.scene.node_items[node_id].update()

        # 预确认高风险真实节点
        confirmed_ids: list[str] = []
        for node_id in scope:
            node = self.scene.nodes[node_id]
            if self._confirm_node_run(node):
                confirmed_ids.append(node_id)
            else:
                node.status = "failed"
                node.error = "用户取消高风险真实运行"
                self._refresh_node(node_id)

        self.engine.run_workflow(
            self.scene.nodes,
            list(self.scene.edges),
            start_ids=start_ids,
            confirm=confirmed_ids,
        )

    def _connect_selected_nodes(self) -> None:
        node_id = self.scene.selected_node_id()
        if not node_id:
            self._log("请先选中一个节点")
            return
        if not self._last_connect_source:
            self._last_connect_source = node_id
            self._log("已选择连线起点，请再选中目标节点后点击连接")
            return
        self.scene.add_edge(self._last_connect_source, node_id)
        if any(edge.source_id == self._last_connect_source and edge.target_id == node_id for edge in self.scene.edges):
            self._log(f"已连接：{self.scene.nodes[self._last_connect_source].spec.name} -> {self.scene.nodes[node_id].spec.name}")
        self._last_connect_source = None

    def _refresh_environment(self) -> None:
        items = check_environment()
        ok_count = sum(1 for item in items if item.ok)
        self.env_summary.setText(f"环境检测：{ok_count} / {len(items)} 项就绪")
        lines = [f"检测时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
        for item in items:
            mark = "OK" if item.ok else "MISSING"
            lines.append(f"[{mark}] {item.name}")
            lines.append(f"  {item.detail}")
            if item.path:
                lines.append(f"  {item.path}")
            lines.append("")
        self.env_output.setPlainText("\n".join(lines).strip())

    def _confirm_node_run(self, node: WorkflowNode) -> bool:
        is_real = str(node.params.get("执行模式", "模拟")).strip() == "真实"
        if not is_real or not node.spec.requires_confirmation:
            return True
        text = (
            f"节点「{node.spec.name}」将以真实模式运行。\n\n"
            f"风险等级：{node.spec.risk_level}\n"
            "它可能执行批量下载、生成或发布等重任务。确认继续？"
        )
        result = QMessageBox.warning(
            self,
            "确认真实运行",
            text,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return result == QMessageBox.Yes

    def _delete_selected_nodes(self) -> None:
        deleted = self.scene.delete_selected_nodes()
        if deleted:
            self._last_connect_source = None
            self._log(f"已删除 {len(deleted)} 个节点")

    def _diagnose_current_error(self) -> None:
        node = self._current_node()
        if not node:
            self.agent_output.setPlainText("请先选择一个需要诊断的节点。")
            self.tabs.setCurrentWidget(self.agent_tab)
            return
        if not node.error:
            self.agent_output.setPlainText(f"节点「{node.spec.name}」当前没有错误信息。")
            self.tabs.setCurrentWidget(self.agent_tab)
            return

        self._save_agent_settings_from_ui()
        fallback = self._fallback_diagnosis(node)
        if self.agent_settings.api_key.strip():
            try:
                advice = LLMDiagnoser(self.agent_settings).diagnose_error(
                    node_name=node.spec.name,
                    node_type=node.spec.type,
                    error=node.error,
                )
            except LLMClientError as exc:
                advice = f"模型诊断失败，已使用本地建议：\n{exc}\n\n{fallback}"
        else:
            advice = fallback
        self.agent_output.setPlainText(advice)
        self.tabs.setCurrentWidget(self.agent_tab)

    def _fallback_diagnosis(self, node: WorkflowNode) -> str:
        hints = [f"节点「{node.spec.name}」失败：{node.error}", "", "建议："]
        if "主页链接" in node.error:
            hints.append("- 检查节点参数里的抖音主页链接是否已填写。")
        if "没有可下载链接" in node.error or "上游" in node.error:
            hints.append("- 先运行上游节点，确认它已经成功产出输出缓存。")
        if "Cookie" in node.error or "403" in node.error:
            hints.append("- 检查 Cookie 是否有效，或先在浏览器里确认该视频可以正常访问。")
        if "ASR" in node.spec.name or "模型" in node.error:
            hints.append("- 检查 FFmpeg、模型名称、设备参数和输出目录。")
        hints.append("- 如果是重任务，建议先切回“模拟”模式确认流程结构，再运行真实模式。")
        return "\n".join(hints)

    def _save_agent_settings_from_ui(self) -> None:
        self.agent_settings = AgentSettings(
            api_base=self.api_base_input.text().strip() or "https://api.openai.com/v1",
            api_key=self.api_key_input.text().strip(),
            model=self.model_input.text().strip() or "gpt-4o-mini",
        )
        save_agent_settings(self.agent_settings)

    def _save_workflow(self) -> None:
        default_path = str(Path.cwd() / "workflows" / "workflow.json")
        Path(default_path).parent.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "保存流程", default_path, "Workflow JSON (*.json)")
        if not path:
            return
        data = {
            "version": "0.1.0",
            "nodes": [
                {
                    "id": node.id,
                    "type": node.spec.type,
                    "x": node.x,
                    "y": node.y,
                    "params": node.params,
                    "status": node.status,
                    "last_output": node.last_output,
                }
                for node in self.scene.nodes.values()
            ],
            "edges": [
                {"id": edge.id, "source_id": edge.source_id, "target_id": edge.target_id}
                for edge in self.scene.edges
            ],
        }
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self._log(f"流程已保存：{path}")

    def _load_workflow(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "加载流程", str(Path.cwd() / "workflows"), "Workflow JSON (*.json)")
        if not path:
            return
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.scene.clear_workflow()
        old_to_new: dict[str, str] = {}
        for item in data.get("nodes", []):
            node = self.scene.add_node(item["type"], QPointF(float(item["x"]), float(item["y"])))
            old_to_new[item["id"]] = node.id
            node.params.update(item.get("params", {}))
            node.status = item.get("status", "idle")
            node.last_output = item.get("last_output")
            self.scene.node_items[node.id].update()
        for edge in data.get("edges", []):
            source = old_to_new.get(edge["source_id"])
            target = old_to_new.get(edge["target_id"])
            if source and target:
                self.scene.add_edge(source, target)
        self._log(f"流程已加载：{path}")

    def _current_node(self) -> WorkflowNode | None:
        node_id = self.current_node_id or self.scene.selected_node_id()
        return self.scene.nodes.get(node_id) if node_id else None

    def _incoming(self, node_id: str):
        return [edge for edge in self.scene.edges if edge.target_id == node_id]

    def _upstream_outputs(self, node_id: str) -> list[dict]:
        outputs = []
        for edge in self._incoming(node_id):
            output = self.scene.nodes[edge.source_id].last_output
            if output:
                outputs.append(output)
        return outputs

    def _refresh_node(self, node_id: str) -> None:
        if node_id not in self.scene.node_items:
            return
        self.scene.node_items[node_id].update()
        self._update_metrics()
        if self.current_node_id == node_id:
            self._show_node_params(node_id)

    def _workflow_data(self) -> dict:
        return {
            "version": "0.1.0",
            "rev": self._last_rev,
            "nodes": [
                {
                    "id": node.id,
                    "type": node.spec.type,
                    "x": node.x,
                    "y": node.y,
                    "params": node.params,
                    "status": node.status,
                    "last_output": node.last_output,
                    "error": node.error,
                }
                for node in self.scene.nodes.values()
            ],
            "edges": [
                {"id": edge.id, "source_id": edge.source_id, "target_id": edge.target_id}
                for edge in self.scene.edges
            ],
        }

    def _autosave(self) -> None:
        if self._loading_active:
            return
        rev = workflow_store.save_workflow(self._workflow_data(), self._active_path)
        self._last_rev = rev
        self._watch_active_path()

    def _on_active_file_changed(self, _path: str) -> None:
        self._watch_active_path()
        self._active_reload_timer.start()

    def _reload_from_disk(self) -> None:
        if not self._active_path.exists():
            self._watch_active_path()
            return
        data = workflow_store.load_workflow(self._active_path)
        rev = int(data.get("rev", 0))
        if rev <= self._last_rev:
            self._watch_active_path()
            return
        self._load_workflow_data(data, preserve_ids=True)
        self._last_rev = rev
        self._watch_active_path()

    def _load_workflow_data(self, data: dict, preserve_ids: bool = False) -> None:
        self._loading_active = True
        try:
            self.scene.clear_workflow()
            old_to_new: dict[str, str] = {}
            for item in data.get("nodes", []):
                node_type = item.get("type")
                if node_type not in NODE_SPEC_BY_TYPE:
                    continue
                node = self.scene.add_node(node_type, QPointF(float(item.get("x", 0)), float(item.get("y", 0))))
                original_id = node.id
                desired_id = str(item.get("id") or original_id)
                if preserve_ids and desired_id != original_id:
                    node.id = desired_id
                    scene_item = self.scene.node_items.pop(original_id)
                    self.scene.nodes.pop(original_id)
                    self.scene.nodes[desired_id] = node
                    self.scene.node_items[desired_id] = scene_item
                old_to_new[str(item.get("id", desired_id))] = node.id
                node.params.update(item.get("params", {}))
                node.status = item.get("status", "idle")
                node.last_output = item.get("last_output")
                node.error = item.get("error", "")
                self.scene.node_items[node.id].update()
            for edge in data.get("edges", []):
                source = old_to_new.get(str(edge.get("source_id")))
                target = old_to_new.get(str(edge.get("target_id")))
                if source and target:
                    before = len(self.scene.edges)
                    self.scene.add_edge(source, target)
                    if len(self.scene.edges) > before:
                        self.scene.edges[-1].id = edge.get("id", self.scene.edges[-1].id)
            self._update_metrics()
        finally:
            self._loading_active = False

    def _log(self, message: str) -> None:
        self.log_box.append(message)
        self.run_logger.write(message)

    def _update_metrics(self) -> None:
        nodes = list(self.scene.nodes.values())
        self.metric_total.set_value(len(nodes))
        self.metric_running.set_value(sum(1 for node in nodes if node.status == "running"))
        self.metric_failed.set_value(sum(1 for node in nodes if node.status == "failed"))


def run_app() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_QSS)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
