from __future__ import annotations

from PyQt5.QtCore import QByteArray, QLineF, QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsScene, QGraphicsView

from app.manifest import best_connection, describe_port
from app.models import NODE_SPEC_BY_TYPE, WorkflowEdge, WorkflowNode


class NodeItem(QGraphicsItem):
    WIDTH = 226
    HEIGHT = 118

    def __init__(self, node: WorkflowNode) -> None:
        super().__init__()
        self.node = node
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(2)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.WIDTH, self.HEIGHT)

    def output_pos(self) -> QPointF:
        return self.scenePos() + QPointF(self.WIDTH, 58)

    def input_pos(self) -> QPointF:
        return self.scenePos() + QPointF(0, 58)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing)
        border = {
            "idle": "#3a4450",
            "running": "#f6c453",
            "success": "#36c275",
            "failed": "#ff6b6b",
        }.get(self.node.status, "#3a4450")
        if self.isSelected():
            border = "#3a86ff"

        painter.setPen(QPen(QColor(border), 2))
        painter.setBrush(QColor("#1b2026"))
        painter.drawRoundedRect(self.boundingRect(), 8, 8)

        painter.setPen(QPen(QColor("#303842"), 1))
        painter.setBrush(QColor("#20262e"))
        painter.drawRoundedRect(QRectF(0, 0, self.WIDTH, 50), 8, 8)
        painter.drawLine(0, 50, self.WIDTH, 50)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self.node.spec.color))
        painter.drawRoundedRect(QRectF(12, 10, 30, 30), 6, 6)
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))
        painter.drawText(QRectF(12, 10, 30, 30), Qt.AlignCenter, self.node.spec.icon)

        painter.setPen(QColor("#eef2f6"))
        painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
        painter.drawText(QRectF(52, 9, 116, 18), Qt.AlignLeft | Qt.AlignVCenter, self.node.spec.name)
        painter.setPen(QColor("#9aa6b2"))
        painter.setFont(QFont("Microsoft YaHei UI", 8))
        painter.drawText(QRectF(52, 27, 126, 16), Qt.AlignLeft | Qt.AlignVCenter, self.node.spec.outputs[0])

        status_text = {"idle": "未运行", "running": "运行中", "success": "成功", "failed": "失败"}.get(self.node.status, self.node.status)
        painter.setPen(QColor("#9aa6b2"))
        painter.drawText(QRectF(174, 14, 42, 18), Qt.AlignRight | Qt.AlignVCenter, status_text)

        painter.setPen(QColor("#9aa6b2"))
        y = 62
        for key, value in list(self.node.params.items())[:3]:
            painter.drawText(QRectF(12, y, 82, 16), Qt.AlignLeft | Qt.AlignVCenter, str(key))
            painter.setPen(QColor("#eef2f6"))
            painter.drawText(QRectF(96, y, 116, 16), Qt.AlignRight | Qt.AlignVCenter, str(value))
            painter.setPen(QColor("#9aa6b2"))
            y += 18

        painter.setPen(QPen(QColor("#0f1215"), 2))
        if self.node.spec.inputs:
            painter.setBrush(QColor("#8b98a7"))
            painter.drawEllipse(QPointF(0, 58), 6, 6)
        if self.node.spec.outputs:
            painter.setBrush(QColor("#36c275"))
            painter.drawEllipse(QPointF(self.WIDTH, 58), 6, 6)
            painter.setPen(QPen(QColor("#9ff0bd"), 1))
            painter.drawEllipse(QPointF(self.WIDTH, 58), 9, 9)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            self.node.x = self.pos().x()
            self.node.y = self.pos().y()
            self.scene().update_edges()
        return super().itemChange(change, value)


class EdgeItem(QGraphicsPathItem):
    def __init__(self, edge: WorkflowEdge, source: NodeItem, target: NodeItem) -> None:
        super().__init__()
        self.edge = edge
        self.source = source
        self.target = target
        self.setZValue(1)
        self.setPen(QPen(QColor("#6c7a89"), 2.5))
        self.update_path()

    def update_path(self) -> None:
        self.prepareGeometryChange()
        start = self.source.output_pos()
        end = self.target.input_pos()
        dx = max(70, abs(end.x() - start.x()) * 0.45)
        path = QPainterPath(start)
        path.cubicTo(start + QPointF(dx, 0), end - QPointF(dx, 0), end)
        self.setPath(path)


class CanvasScene(QGraphicsScene):
    node_selected = pyqtSignal(str)
    node_changed = pyqtSignal()
    selection_cleared = pyqtSignal()
    edge_rejected = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setSceneRect(-2500, -1800, 5000, 3600)
        self.nodes: dict[str, WorkflowNode] = {}
        self.node_items: dict[str, NodeItem] = {}
        self.edges: list[WorkflowEdge] = []
        self.edge_items: list[EdgeItem] = []
        self._drag_source_id: str | None = None
        self._drag_edge: QGraphicsPathItem | None = None

    def add_node(self, node_type: str, pos: QPointF) -> WorkflowNode:
        node = WorkflowNode(NODE_SPEC_BY_TYPE[node_type], pos.x(), pos.y())
        item = NodeItem(node)
        item.setPos(pos)
        self.addItem(item)
        self.nodes[node.id] = node
        self.node_items[node.id] = item
        self.clearSelection()
        item.setSelected(True)
        self.node_selected.emit(node.id)
        self.node_changed.emit()
        return node

    def add_edge(self, source_id: str, target_id: str) -> None:
        if source_id == target_id:
            return
        ok, message = self.can_connect(source_id, target_id)
        if not ok:
            self.edge_rejected.emit(message)
            return
        if any(edge.source_id == source_id and edge.target_id == target_id for edge in self.edges):
            return
        edge = WorkflowEdge(source_id, target_id)
        self.edges.append(edge)
        edge_item = EdgeItem(edge, self.node_items[source_id], self.node_items[target_id])
        self.edge_items.append(edge_item)
        self.addItem(edge_item)
        self.node_changed.emit()

    def can_connect(self, source_id: str, target_id: str) -> tuple[bool, str]:
        source = self.nodes.get(source_id)
        target = self.nodes.get(target_id)
        if not source or not target:
            return False, "节点不存在，无法连线"
        if not source.spec.outputs:
            return False, f"{source.spec.name} 没有输出端口"
        if not target.spec.inputs:
            return False, f"{target.spec.name} 没有输入端口"
        if best_connection(source.spec.outputs, target.spec.inputs) is None:
            source_desc = "、".join(describe_port(p) for p in source.spec.outputs)
            target_desc = "、".join(describe_port(p) for p in target.spec.inputs)
            return (
                False,
                f"数据契约不匹配：{source.spec.name} 输出 [{source_desc}]，"
                f"{target.spec.name} 需要 [{target_desc}]",
            )
        return True, ""

    def delete_selected_nodes(self) -> list[str]:
        selected_ids = [
            item.node.id
            for item in self.selectedItems()
            if isinstance(item, NodeItem)
        ]
        if not selected_ids:
            return []

        selected = set(selected_ids)
        for edge_item in list(self.edge_items):
            if edge_item.edge.source_id in selected or edge_item.edge.target_id in selected:
                self.removeItem(edge_item)
                self.edge_items.remove(edge_item)
                self.edges.remove(edge_item.edge)

        for node_id in selected_ids:
            item = self.node_items.pop(node_id, None)
            self.nodes.pop(node_id, None)
            if item:
                self.removeItem(item)

        self.update()
        self.node_changed.emit()
        self.selection_cleared.emit()
        return selected_ids

    def clear_workflow(self) -> None:
        for item in list(self.items()):
            self.removeItem(item)
        self.nodes.clear()
        self.node_items.clear()
        self.edges.clear()
        self.edge_items.clear()
        self.node_changed.emit()
        self.selection_cleared.emit()

    def update_edges(self) -> None:
        for item in self.edge_items:
            item.update_path()
        self.invalidate(self.sceneRect(), QGraphicsScene.AllLayers)

    def selected_node_id(self) -> str | None:
        for item in self.selectedItems():
            if isinstance(item, NodeItem):
                return item.node.id
        return None

    def mousePressEvent(self, event) -> None:
        source_id = self._node_output_at(event.scenePos())
        if source_id:
            self._start_edge_drag(source_id, event.scenePos())
            event.accept()
            return
        super().mousePressEvent(event)
        node_id = self.selected_node_id()
        if node_id:
            self.node_selected.emit(node_id)
        else:
            self.selection_cleared.emit()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_source_id and self._drag_edge:
            self._update_drag_edge(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_source_id:
            target_id = self._node_input_at(event.scenePos())
            if target_id and target_id != self._drag_source_id:
                self.add_edge(self._drag_source_id, target_id)
                self.node_selected.emit(target_id)
            self._finish_edge_drag()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _node_output_at(self, pos: QPointF) -> str | None:
        for node_id, item in self.node_items.items():
            if item.node.spec.outputs and QLineF(pos, item.output_pos()).length() <= 14:
                return node_id
        return None

    def _node_input_at(self, pos: QPointF) -> str | None:
        for node_id, item in self.node_items.items():
            if item.node.spec.inputs and QLineF(pos, item.input_pos()).length() <= 16:
                return node_id
        return None

    def _start_edge_drag(self, source_id: str, pos: QPointF) -> None:
        self._drag_source_id = source_id
        self._drag_edge = QGraphicsPathItem()
        self._drag_edge.setZValue(5)
        self._drag_edge.setPen(QPen(QColor("#36c275"), 2.5, Qt.DashLine))
        self.clearSelection()
        self.node_items[source_id].setSelected(True)
        self.addItem(self._drag_edge)
        self._update_drag_edge(pos)

    def _update_drag_edge(self, pos: QPointF) -> None:
        if not self._drag_source_id or not self._drag_edge:
            return
        start = self.node_items[self._drag_source_id].output_pos()
        dx = max(70, abs(pos.x() - start.x()) * 0.45)
        path = QPainterPath(start)
        path.cubicTo(start + QPointF(dx, 0), pos - QPointF(dx, 0), pos)
        self._drag_edge.setPath(path)
        self.invalidate(self.sceneRect(), QGraphicsScene.AllLayers)

    def _finish_edge_drag(self) -> None:
        if self._drag_edge:
            self.removeItem(self._drag_edge)
        self._drag_edge = None
        self._drag_source_id = None
        self.invalidate(self.sceneRect(), QGraphicsScene.AllLayers)


class CanvasView(QGraphicsView):
    node_dropped = pyqtSignal(str, QPointF)

    def __init__(self, scene: CanvasScene) -> None:
        super().__init__(scene)
        self.setAcceptDrops(True)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setBackgroundBrush(QColor("#0f1215"))
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self._zoom = 1.0

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
        grid = 24
        left = int(rect.left()) - int(rect.left()) % grid
        top = int(rect.top()) - int(rect.top()) % grid
        x = left
        while x < rect.right():
            painter.drawLine(QLineF(x, rect.top(), x, rect.bottom()))
            x += grid
        y = top
        while y < rect.bottom():
            painter.drawLine(QLineF(rect.left(), y, rect.right(), y))
            y += grid

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat("application/x-videoops-node"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        data: QByteArray = event.mimeData().data("application/x-videoops-node")
        node_type = bytes(data).decode("utf-8")
        self.node_dropped.emit(node_type, self.mapToScene(event.pos()))
        event.acceptProposedAction()

    def wheelEvent(self, event) -> None:
        factor = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
        self._zoom = max(0.4, min(1.8, self._zoom * factor))
        self.scale(factor, factor)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.scene().delete_selected_nodes()
            event.accept()
            return
        super().keyPressEvent(event)
