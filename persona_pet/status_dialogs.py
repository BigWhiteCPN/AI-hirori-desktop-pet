"""Memory graph and drive status PyQt dialogs."""

import math

from persona_pet.error_reporter import report_exception

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QPainter, QRadialGradient
from PyQt5.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextEdit, QVBoxLayout, QWidget

class MemoryGraphCanvas(QWidget):
    NODE_COLORS = {
        "脑区": QColor(236, 213, 255),
        "角色": QColor(255, 196, 224),
        "类别": QColor(205, 230, 255),
        "情绪": QColor(255, 222, 168),
        "症状": QColor(255, 184, 184),
        "记忆": QColor(218, 238, 204),
        "思考": QColor(222, 206, 255),
        "心情": QColor(186, 234, 226),
    }

    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self.dialog = dialog
        self.positions = {}
        self.velocities = {}
        self.radii = {}
        self.layout_key = ()
        self.drag_node_id = ""
        self.drag_offset = (0.0, 0.0)
        self.setMinimumSize(540, 430)
        self.setMouseTracking(True)
        self.hover_node_id = ""
        self.setStyleSheet(
            "background: rgba(255,255,255,230); border: 1px solid rgba(235,144,188,210); border-radius: 10px;"
        )
        self.layout_timer = QTimer(self)
        self.layout_timer.timeout.connect(self.animate_layout)
        self.layout_timer.start(50)

    def node_color(self, node):
        return self.NODE_COLORS.get(node.get("type", ""), QColor(235, 218, 255))

    def node_text_color(self, node):
        node_type = node.get("type", "")
        if node_type == "脑区":
            return QColor(83, 58, 124)
        if node_type == "症状":
            return QColor(104, 50, 58)
        if node_type == "情绪":
            return QColor(108, 66, 36)
        if node_type == "类别":
            return QColor(48, 76, 112)
        if node_type == "记忆":
            return QColor(55, 89, 56)
        if node_type == "思考":
            return QColor(74, 56, 122)
        if node_type == "心情":
            return QColor(39, 91, 86)
        return QColor(91, 45, 72)

    def compact_label(self, label, max_chars=8):
        label = str(label or "").strip()
        if len(label) <= max_chars:
            return label
        return label[: max_chars - 1] + "…"

    def layout_nodes(self, reset=False):
        nodes = self.dialog.important_nodes()
        node_ids = [node.get("id", "") for node in nodes if node.get("id", "")]
        node_key = tuple(node_ids)
        if reset or node_key != self.layout_key:
            self.positions = {node_id: self.positions[node_id] for node_id in node_ids if node_id in self.positions}
            self.velocities = {node_id: self.velocities.get(node_id, (0.0, 0.0)) for node_id in node_ids}
            self.layout_key = node_key
        self.radii = {}
        if not nodes:
            return []

        center_x = self.width() * 0.50
        center_y = self.height() * 0.50
        rings = [
            min(self.width(), self.height()) * 0.24,
            min(self.width(), self.height()) * 0.39,
        ]
        for index, node in enumerate(nodes):
            node_id = node.get("id", "")
            count = int(node.get("count", 0))
            radius = 22 + min(16, count * 2)
            self.radii[node_id] = radius
            if node_id in self.positions and not reset:
                continue
            if index == 0:
                self.positions[node_id] = (center_x, center_y)
                continue
            ring_index = 0 if index <= 14 else 1
            ring_radius = rings[ring_index]
            ring_items = min(14, max(1, len(nodes) - 1)) if ring_index == 0 else max(1, len(nodes) - 15)
            local_index = index - 1 if ring_index == 0 else index - 15
            angle = local_index / max(1, ring_items) * math.tau - math.pi / 2
            self.positions[node_id] = (
                center_x + math.cos(angle) * ring_radius,
                center_y + math.sin(angle) * ring_radius,
            )
        return nodes

    def clamp_position(self, node_id, x, y):
        radius = self.radii.get(node_id, 24)
        margin = radius + 10
        return (
            max(margin, min(self.width() - margin, x)),
            max(margin, min(self.height() - margin, y)),
        )

    def animate_layout(self):
        nodes = self.layout_nodes()
        if len(nodes) < 2 or not self.isVisible():
            return
        node_ids = [node.get("id", "") for node in nodes if node.get("id", "")]
        node_set = set(node_ids)
        forces = {node_id: [0.0, 0.0] for node_id in node_ids}
        center_x = self.width() * 0.50
        center_y = self.height() * 0.50

        for index, left in enumerate(node_ids):
            x1, y1 = self.positions.get(left, (center_x, center_y))
            for right in node_ids[index + 1 :]:
                x2, y2 = self.positions.get(right, (center_x, center_y))
                dx = x1 - x2
                dy = y1 - y2
                dist_sq = max(64.0, dx * dx + dy * dy)
                dist = math.sqrt(dist_sq)
                strength = min(2.8, 1800.0 / dist_sq)
                fx = dx / dist * strength
                fy = dy / dist * strength
                forces[left][0] += fx
                forces[left][1] += fy
                forces[right][0] -= fx
                forces[right][1] -= fy

        for edge in self.dialog.visible_edges():
            source = edge.get("source")
            target = edge.get("target")
            if source not in node_set or target not in node_set:
                continue
            x1, y1 = self.positions[source]
            x2, y2 = self.positions[target]
            dx = x2 - x1
            dy = y2 - y1
            dist = max(1.0, math.sqrt(dx * dx + dy * dy))
            desired = 112.0 + min(58.0, (self.radii.get(source, 24) + self.radii.get(target, 24)) * 0.7)
            strength = (dist - desired) * 0.006 * min(3.0, max(1.0, float(edge.get("weight", 1))))
            fx = dx / dist * strength
            fy = dy / dist * strength
            forces[source][0] += fx
            forces[source][1] += fy
            forces[target][0] -= fx
            forces[target][1] -= fy

        moved = False
        for node_id in node_ids:
            if node_id == self.drag_node_id:
                self.velocities[node_id] = (0.0, 0.0)
                continue
            x, y = self.positions.get(node_id, (center_x, center_y))
            forces[node_id][0] += (center_x - x) * 0.002
            forces[node_id][1] += (center_y - y) * 0.002
            vx, vy = self.velocities.get(node_id, (0.0, 0.0))
            vx = (vx + forces[node_id][0]) * 0.82
            vy = (vy + forces[node_id][1]) * 0.82
            vx = max(-3.0, min(3.0, vx))
            vy = max(-3.0, min(3.0, vy))
            if abs(vx) > 0.02 or abs(vy) > 0.02:
                moved = True
            self.positions[node_id] = self.clamp_position(node_id, x + vx, y + vy)
            self.velocities[node_id] = (vx, vy)
        if moved:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(255, 255, 255, 0))

        nodes = self.layout_nodes()
        if not nodes:
            painter.setPen(QColor(138, 97, 120))
            painter.setFont(QFont("Microsoft YaHei UI", 12))
            painter.drawText(self.rect(), Qt.AlignCenter, "还没有记忆。\n对话几轮后这里会长出关系网。")
            painter.end()
            return

        node_ids = {node.get("id", "") for node in nodes}
        for edge in self.dialog.visible_edges():
            source = edge.get("source")
            target = edge.get("target")
            if source not in node_ids or target not in node_ids:
                continue
            x1, y1 = self.positions[source]
            x2, y2 = self.positions[target]
            weight = min(4, max(1, int(edge.get("weight", 1))))
            painter.setPen(QColor(205, 142, 180, 85 + weight * 22))
            pen = painter.pen()
            pen.setWidth(weight)
            painter.setPen(pen)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

            if weight >= 2:
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                painter.setPen(QColor(150, 92, 128, 150))
                painter.setFont(QFont("Microsoft YaHei UI", 7))
                painter.drawText(int(mx - 18), int(my - 4), edge.get("relation", "关联")[:4])

        for node in nodes:
            node_id = node.get("id", "")
            x, y = self.positions[node_id]
            radius = self.radii[node_id]
            selected = node_id == self.dialog.current_node_id
            hovered = node_id == self.hover_node_id

            base_color = self.node_color(node)
            shadow_radius = radius + (6 if selected or hovered else 4)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(102, 46, 76, 28 if selected or hovered else 18))
            painter.drawEllipse(
                int(x - shadow_radius + 2),
                int(y - shadow_radius + 5),
                shadow_radius * 2,
                shadow_radius * 2,
            )

            if selected or hovered:
                painter.setBrush(QColor(255, 132, 188, 46 if selected else 30))
                painter.drawEllipse(
                    int(x - radius - 7),
                    int(y - radius - 7),
                    (radius + 7) * 2,
                    (radius + 7) * 2,
                )

            gradient = QRadialGradient(x - radius * 0.35, y - radius * 0.45, radius * 1.35)
            gradient.setColorAt(0.0, base_color.lighter(136))
            gradient.setColorAt(0.58, base_color)
            gradient.setColorAt(1.0, base_color.darker(108))
            painter.setBrush(gradient)
            pen_color = QColor(230, 94, 150) if selected or hovered else QColor(214, 136, 176)
            painter.setPen(pen_color)
            pen = painter.pen()
            pen.setWidth(3 if selected else 2)
            painter.setPen(pen)
            painter.drawEllipse(int(x - radius), int(y - radius), radius * 2, radius * 2)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 76))
            highlight_size = max(8, int(radius * 0.36))
            painter.drawEllipse(
                int(x - radius * 0.42),
                int(y - radius * 0.48),
                highlight_size,
                highlight_size,
            )

            painter.setPen(self.node_text_color(node))
            painter.setFont(QFont("Microsoft YaHei UI", 8, QFont.DemiBold))
            label = self.compact_label(node.get("label", ""), 8)
            painter.drawText(
                int(x - radius - 14),
                int(y - 10),
                int((radius + 14) * 2),
                19,
                Qt.AlignCenter,
                label,
            )

            type_label = self.compact_label(node.get("type", ""), 4)
            count_label = f"{type_label} · {node.get('count', 0)}"
            painter.setFont(QFont("Microsoft YaHei UI", 7))
            painter.setPen(QColor(112, 74, 96, 190))
            painter.drawText(
                int(x - radius - 14),
                int(y + 8),
                int((radius + 14) * 2),
                16,
                Qt.AlignCenter,
                count_label,
            )
        painter.end()

    def node_at(self, pos):
        self.layout_nodes()
        for node_id, (x, y) in self.positions.items():
            radius = self.radii.get(node_id, 24)
            if (pos.x() - x) ** 2 + (pos.y() - y) ** 2 <= radius ** 2:
                return node_id
        return ""

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        node_id = self.node_at(event.pos())
        if node_id:
            x, y = self.positions.get(node_id, (event.pos().x(), event.pos().y()))
            self.drag_node_id = node_id
            self.drag_offset = (event.pos().x() - x, event.pos().y() - y)
            self.dialog.focus_node(node_id)
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_node_id:
            dx, dy = self.drag_offset
            x, y = self.clamp_position(self.drag_node_id, event.pos().x() - dx, event.pos().y() - dy)
            self.positions[self.drag_node_id] = (x, y)
            self.velocities[self.drag_node_id] = (0.0, 0.0)
            self.hover_node_id = self.drag_node_id
            self.setCursor(Qt.ClosedHandCursor)
            self.update()
            event.accept()
            return
        node_id = self.node_at(event.pos())
        if node_id != self.hover_node_id:
            self.hover_node_id = node_id
            self.setCursor(Qt.OpenHandCursor if node_id else Qt.ArrowCursor)
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drag_node_id and event.button() == Qt.LeftButton:
            self.drag_node_id = ""
            self.drag_offset = (0.0, 0.0)
            self.setCursor(Qt.OpenHandCursor if self.hover_node_id else Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dialog.exit_module()
            self.layout_nodes(reset=True)
            self.update()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def leaveEvent(self, event):
        if self.drag_node_id:
            super().leaveEvent(event)
            return
        if self.hover_node_id:
            self.hover_node_id = ""
            self.setCursor(Qt.ArrowCursor)
            self.update()
        super().leaveEvent(event)

class MemoryGraphDialog(QDialog):
    def __init__(self, memory_store, parent=None):
        super().__init__(parent)
        self.memory_store = memory_store
        self.graph, self.short_terms, self.long_term = self.memory_store.graph_snapshot()
        self.brain = self.memory_store.brain_module_snapshot() if hasattr(self.memory_store, "brain_module_snapshot") else {"modules": [], "edges": [], "node_to_module": {}}
        self.current_module_key = ""
        self.current_node_id = ""
        self.setWindowTitle("脑内记忆地图")
        self.resize(900, 620)
        self.setMinimumSize(760, 520)
        self.setStyleSheet(
            """
            QDialog {
                background: #fff6fb;
                color: #543247;
                font: 10pt "Microsoft YaHei UI";
            }
            QLabel#memoryTitle {
                color: #8f2d5a;
                font: 16pt "Microsoft YaHei UI";
                font-weight: 700;
            }
            QLabel#memoryHint {
                color: #8a6178;
            }
            QTextEdit {
                background: rgba(255, 255, 255, 238);
                border: 1px solid rgba(235, 144, 188, 210);
                border-radius: 10px;
                padding: 10px;
                color: #543247;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        title = QLabel("脑内记忆地图")
        title.setObjectName("memoryTitle")
        root.addWidget(title)
        hint = QLabel("先点击脑区模块进入内部；模块内会显示该脑区处理的记忆和联想连线。双击图面返回脑区总览。")
        hint.setObjectName("memoryHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        body = QHBoxLayout()
        root.addLayout(body, 1)
        self.canvas = MemoryGraphCanvas(self)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMinimumWidth(270)
        body.addWidget(self.canvas, 2)
        body.addWidget(self.detail, 1)

        self.show_overview()

    def visible_edges(self):
        if not self.current_module_key:
            return self.brain.get("edges", [])
        node_ids = {node.get("id", "") for node in self.important_nodes()}
        return [
            edge
            for edge in self.graph.get("edges", [])
            if edge.get("source") in node_ids and edge.get("target") in node_ids
        ]

    def important_nodes(self):
        if not self.current_module_key:
            return self.brain.get("modules", [])
        nodes = self.graph.get("nodes", {})
        edges = self.graph.get("edges", [])
        connected = {}
        for edge in edges:
            connected[edge.get("source")] = connected.get(edge.get("source"), 0) + int(edge.get("weight", 1))
            connected[edge.get("target")] = connected.get(edge.get("target"), 0) + int(edge.get("weight", 1))

        def score(node):
            return (
                connected.get(node.get("id"), 0) * 2
                + int(node.get("count", 0))
            )

        node_to_module = self.brain.get("node_to_module", {})
        values = [
            node
            for node_id, node in nodes.items()
            if node_to_module.get(node_id) == self.current_module_key
        ]
        roles = sorted([node for node in values if node.get("type") == "角色"], key=score, reverse=True)[:3]
        real_memory = sorted(
            [node for node in values if node.get("type") in ("记忆", "症状", "情绪")],
            key=score,
            reverse=True,
        )[:16]
        categories = sorted([node for node in values if node.get("type") == "类别"], key=score, reverse=True)[:6]
        thoughts = sorted([node for node in values if node.get("type") == "思考"], key=score, reverse=True)[:6]
        moods = sorted([node for node in values if node.get("type") == "心情"], key=score, reverse=True)[:3]

        selected = []
        seen = set()
        for group in (roles, real_memory, categories, thoughts, moods):
            for node in group:
                node_id = node.get("id", "")
                if node_id and node_id not in seen:
                    selected.append(node)
                    seen.add(node_id)
        if len(selected) < 34:
            for node in sorted(values, key=score, reverse=True):
                node_id = node.get("id", "")
                if node_id and node_id not in seen:
                    selected.append(node)
                    seen.add(node_id)
                if len(selected) >= 34:
                    break
        return selected[:34]

    def show_overview(self):
        summary = self.long_term.get("summary", "还没有形成长期记忆。")
        recent = self.short_terms[-5:]
        reflections = [item for item in self.short_terms if item.get("reflection")]
        association = self.memory_store.load_meta_json("last_association", {}) if hasattr(self.memory_store, "load_meta_json") else {}
        lines = [f"长期摘要\n{summary}", "", "脑区模块"]
        modules = self.brain.get("modules", [])
        if not modules:
            lines.append("暂无脑区模块。对话几轮后，记忆会自动分配到不同脑区。")
        for module in modules:
            lines.append(f"- {module.get('label')}：{module.get('count', 0)} 个信号")
            if module.get("category"):
                lines.append(f"  {module.get('category')}")
        lines.append("")
        lines.append("最近联想链")
        if isinstance(association, dict) and association.get("steps"):
            source = association.get("source", "")
            role = association.get("role", "")
            lines.append(f"{association.get('time', '')}  {source}/{role}：{association.get('query', '')[:80]}")
            for step in association.get("steps", [])[:6]:
                lines.append(f"- {step}")
        else:
            lines.append("暂无检索联想。她开始回应或主动表达后这里会出现思考路径。")
        lines.extend(["", "思考痕迹"])
        if not reflections:
            lines.append("暂无反思记忆。她空闲时会从旧记忆里抽取线索，形成新的想法。")
        for item in reversed(reflections[-5:]):
            focus = item.get("focus_memory_text") or item.get("user", "")
            lines.append(f"- {item.get('created_at', '')}  {item.get('mood', '')}")
            if focus:
                lines.append(f"  触发记忆：{focus[:80]}")
            lines.append(f"  新想法：{item.get('assistant', '')[:110]}")
        lines.extend(["", "最近片段"])
        if not recent:
            lines.append("暂无。")
        for item in reversed(recent):
            cats = " / ".join(item.get("categories", []))
            if item.get("reflection"):
                lines.append(f"- [{cats}] 内心反思：{item.get('assistant', '')[:90]}")
            else:
                lines.append(f"- [{cats}] 用户：{item.get('user', '')[:80]}")
                lines.append(f"  桌宠：{item.get('assistant', '')[:80]}")
        self.detail.setPlainText("\n".join(lines))

    def show_module_overview(self, module_key):
        self.current_module_key = module_key
        self.current_node_id = ""
        modules = {module.get("key"): module for module in self.brain.get("modules", [])}
        module = modules.get(module_key, {})
        nodes = self.important_nodes()
        edge_count = len(self.visible_edges())
        lines = [
            module.get("label", module_key),
            module.get("category", ""),
            "",
            f"模块信号：{module.get('count', 0)}",
            f"内部节点：{len(nodes)}",
            f"内部连线：{edge_count}",
            "",
            "这个脑区会处理：",
            module.get("details", [""])[0] if module.get("details") else "",
            "",
            "点击左侧节点可以看具体记忆；双击图面返回脑区总览。",
        ]
        self.detail.setPlainText("\n".join(line for line in lines if line is not None))
        if hasattr(self, "canvas"):
            self.canvas.layout_nodes(reset=True)
            self.canvas.update()

    def exit_module(self):
        if not self.current_module_key and not self.current_node_id:
            return
        self.current_module_key = ""
        self.current_node_id = ""
        self.show_overview()
        if hasattr(self, "canvas"):
            self.canvas.layout_nodes(reset=True)
            self.canvas.update()

    def focus_node(self, node_id):
        if str(node_id or "").startswith("脑区:"):
            self.show_module_overview(str(node_id).split(":", 1)[1])
            return
        self.current_node_id = node_id
        nodes = self.graph.get("nodes", {})
        node = nodes.get(node_id, {})
        related = []
        for edge in self.graph.get("edges", []):
            other_id = ""
            direction = ""
            if edge.get("source") == node_id:
                other_id = edge.get("target")
                direction = "->"
            elif edge.get("target") == node_id:
                other_id = edge.get("source")
                direction = "<-"
            if other_id and other_id in nodes:
                related.append((edge, nodes[other_id], direction))
        related.sort(key=lambda pair: int(pair[0].get("weight", 1)), reverse=True)
        lines = [
            f"{node.get('label', node_id)}",
            f"类型：{node.get('type', '')}",
            f"类别：{node.get('category', '') or '未归类'}",
            f"出现次数：{node.get('count', 0)}",
            f"最近出现：{node.get('last_seen', '')}",
            "",
            "细节",
        ]
        details = node.get("details") or []
        lines.extend([f"- {detail}" for detail in details] or ["暂无细节。"])
        lines.extend(["", "联想关系"])
        for edge, other, direction in related[:16]:
            lines.append(
                f"- {direction} {edge.get('relation', '关联')}：{other.get('label', other.get('id'))}  x{edge.get('weight', 1)}"
            )
            if edge.get("detail"):
                lines.append(f"  {edge.get('detail')[:90]}")
        self.detail.setPlainText("\n".join(lines))
        if hasattr(self, "canvas"):
            self.canvas.update()

class DriveStatusDialog(QDialog):
    PHASE_COLORS = {
        "menstrual": "#f58aa8",
        "follicular": "#8ed4a4",
        "ovulation": "#f2c45c",
        "luteal": "#b99af1",
    }
    PHASE_TEXT_COLORS = {
        "menstrual": "#6b2636",
        "follicular": "#285c37",
        "ovulation": "#6a4a12",
        "luteal": "#4d3978",
    }
    PHYSIO_METRICS = (
        ("hunger", "饥饿", QColor(238, 111, 120)),
        ("thirst", "口渴", QColor(94, 166, 230)),
        ("fatigue", "疲劳", QColor(158, 139, 216)),
        ("sleepiness", "困意", QColor(143, 170, 205)),
        ("comfort", "舒适", QColor(124, 205, 132)),
        ("stress", "压力", QColor(255, 181, 92)),
        ("closeness_need", "亲近", QColor(255, 145, 184)),
    )

    def __init__(self, drive, life=None, parent=None, drive_metrics=None, novel_daily_word_limit=1200, novel_daily_chapter_limit=1, physiology=None, body_cycle=None):
        super().__init__(parent)
        self.drive = drive
        self.life = life
        self.physiology = physiology
        self.body_cycle = body_cycle
        self.drive_metrics = tuple(drive_metrics or ())
        self.novel_daily_word_limit = int(novel_daily_word_limit)
        self.novel_daily_chapter_limit = int(novel_daily_chapter_limit)
        self.bars = {}
        self.value_labels = {}
        self.physio_bars = {}
        self.physio_value_labels = {}
        self.cycle_cells = []
        self.setWindowTitle("角色状态")
        self.resize(760, 640)
        self.setMinimumSize(680, 560)
        self.setStyleSheet(
            """
            QDialog {
                background: #fff1f8;
                color: #543247;
                font: 10pt "Microsoft YaHei UI";
            }
            QLabel#statusTitle {
                color: #8f2d5a;
                font: 16pt "Microsoft YaHei UI";
                font-weight: 700;
            }
            QLabel#statusSubtitle {
                color: #8a6178;
                font: 9pt "Microsoft YaHei UI";
            }
            QLabel#sectionTitle {
                color: #8f2d5a;
                font: 9pt "Microsoft YaHei UI";
                font-weight: 700;
                padding-top: 4px;
            }
            QWidget#statusPanel {
                background: rgba(255, 255, 255, 226);
                border: 1px solid #e89abe;
                border-radius: 8px;
            }
            QLabel#softPanel, QTextEdit#softPanel {
                background: rgba(255, 255, 255, 226);
                border: 1px solid #e89abe;
                border-radius: 8px;
                padding: 9px;
                color: #684158;
                font: 9pt "Microsoft YaHei UI";
            }
            QProgressBar {
                background: rgba(255, 255, 255, 215);
                border: 1px solid #e89abe;
                border-radius: 5px;
            }
            QProgressBar::chunk {
                border-radius: 4px;
            }
            QPushButton {
                background: #fff8fd;
                border: 1px solid #e89abe;
                border-radius: 6px;
                padding: 4px 12px;
                color: #543247;
                font: 9pt "Microsoft YaHei UI";
            }
            QPushButton:hover {
                background: #ffe2f0;
                border-color: #d95b95;
            }
            QPushButton:pressed {
                background: #ffd0e5;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(9)

        title = QLabel("苏念 STATUS")
        title.setObjectName("statusTitle")
        root.addWidget(title)

        subtitle = QLabel("内驱 / 记忆 / 身体 / 生理周期")
        subtitle.setObjectName("statusSubtitle")
        root.addWidget(subtitle)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        root.addLayout(top_row, 1)

        drive_panel, drive_layout = self._make_panel("内驱状态")
        for key, label, hint, color in self.drive_metrics:
            self._add_meter_row(drive_layout, key, label, color, self.bars, self.value_labels)
        top_row.addWidget(drive_panel, 1)

        body_panel, body_layout = self._make_panel("身体需求")
        for key, label, color in self.PHYSIO_METRICS:
            self._add_meter_row(body_layout, key, label, color, self.physio_bars, self.physio_value_labels)
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        for btn_text, action in [("喂饭", "feed"), ("喝水", "drink"), ("休息", "rest"), ("摸头", "pat")]:
            btn = QPushButton(btn_text)
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda checked=False, a=action: self._do_action(a))
            action_row.addWidget(btn, 1)
        body_layout.addLayout(action_row)
        top_row.addWidget(body_panel, 1)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)
        root.addLayout(bottom_row, 1)

        cycle_panel, cycle_layout = self._make_panel("生理周期 / 亲密需求")
        self.cycle_label = QLabel("")
        self.cycle_label.setStyleSheet("color: #684158; font: 9pt 'Microsoft YaHei UI';")
        self.cycle_label.setWordWrap(True)
        cycle_layout.addWidget(self.cycle_label)
        self.intimacy_bar = QProgressBar()
        self.intimacy_bar.setRange(0, 100)
        self.intimacy_bar.setTextVisible(False)
        self.intimacy_bar.setFixedHeight(10)
        self.intimacy_bar.setStyleSheet("QProgressBar::chunk { background: #e86fa6; }")
        intimacy_row = QHBoxLayout()
        intimacy_row.setSpacing(8)
        self.intimacy_label = QLabel("亲密需求")
        self.intimacy_label.setFixedWidth(76)
        self.intimacy_label.setStyleSheet("font: bold 9pt 'Microsoft YaHei UI'; color: #5d3750;")
        self.intimacy_value_label = QLabel("0")
        self.intimacy_value_label.setMinimumWidth(118)
        self.intimacy_value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.intimacy_value_label.setStyleSheet("font: bold 9pt 'Microsoft YaHei UI'; color: #8f2d5a;")
        intimacy_row.addWidget(self.intimacy_label)
        intimacy_row.addWidget(self.intimacy_bar, 1)
        intimacy_row.addWidget(self.intimacy_value_label)
        cycle_layout.addLayout(intimacy_row)
        self.growth_label = QLabel("")
        self.growth_label.setStyleSheet("color: #8a6178; font: 8pt 'Microsoft YaHei UI';")
        cycle_layout.addWidget(self.growth_label)
        cycle_layout.addLayout(self._build_cycle_grid())
        cycle_layout.addLayout(self._build_cycle_legend())
        cycle_layout.addLayout(self._build_cycle_test_controls())
        bottom_row.addWidget(cycle_panel, 1)

        mood_panel, mood_layout = self._make_panel("内心状态")
        self.mood_label = QLabel("")
        self.mood_label.setStyleSheet("color: #684158; font: 9pt 'Microsoft YaHei UI';")
        self.mood_label.setWordWrap(True)
        self.mood_label.setMinimumHeight(136)
        mood_layout.addWidget(self.mood_label)
        bottom_row.addWidget(mood_panel, 1)

        self.intent_log = QTextEdit()
        self.intent_log.setObjectName("softPanel")
        self.intent_log.setReadOnly(True)
        self.intent_log.setFixedHeight(64)
        root.addWidget(self.intent_log)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(500)
        self.refresh()

    def _make_panel(self, title):
        panel = QWidget()
        panel.setObjectName("statusPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        layout.addWidget(title_label)
        return panel, layout

    def _add_meter_row(self, layout, key, label, color, bar_store, value_store):
        row = QHBoxLayout()
        row.setSpacing(8)
        name = QLabel(label)
        name.setFixedWidth(72)
        name.setStyleSheet("font: bold 9pt 'Microsoft YaHei UI'; color: #5d3750;")
        value_label = QLabel("0")
        value_label.setFixedWidth(34)
        value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        value_label.setStyleSheet("font: bold 9pt 'Microsoft YaHei UI'; color: #8f2d5a;")
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setTextVisible(False)
        bar.setFixedHeight(10)
        bar.setMinimumWidth(120)
        bar.setStyleSheet("QProgressBar::chunk { background: " + color.name() + "; }")
        row.addWidget(name)
        row.addWidget(bar, 1)
        row.addWidget(value_label)
        layout.addLayout(row)
        bar_store[key] = bar
        value_store[key] = value_label

    def _build_cycle_grid(self):
        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)
        self.cycle_cells = []
        for day in range(1, 32):
            cell = QLabel(str(day))
            cell.setAlignment(Qt.AlignCenter)
            cell.setFixedSize(30, 24)
            cell.setToolTip(f"第 {day} 天")
            self.cycle_cells.append(cell)
            grid.addWidget(cell, (day - 1) // 10, (day - 1) % 10)
        return grid

    def _build_cycle_legend(self):
        legend = QHBoxLayout()
        legend.setSpacing(8)
        for phase, text in (
            ("menstrual", "经期"),
            ("follicular", "卵泡期"),
            ("ovulation", "排卵期"),
            ("luteal", "黄体期"),
        ):
            swatch = QLabel("")
            swatch.setFixedSize(12, 12)
            swatch.setStyleSheet(
                f"background: {self.PHASE_COLORS.get(phase, '#f4d9e8')}; "
                "border: 1px solid rgba(122, 46, 85, 120); border-radius: 3px;"
            )
            label = QLabel(text)
            label.setStyleSheet("color: #684158; font: 8pt 'Microsoft YaHei UI';")
            legend.addWidget(swatch)
            legend.addWidget(label)
        legend.addStretch(1)
        return legend

    def _build_cycle_test_controls(self):
        row = QHBoxLayout()
        row.setSpacing(6)
        for text, phase in (
            ("测经期", "menstrual"),
            ("测卵泡", "follicular"),
            ("测排卵", "ovulation"),
            ("测黄体", "luteal"),
        ):
            btn = QPushButton(text)
            btn.setFixedHeight(24)
            btn.setToolTip("测试用：临时把今天切到这个生理阶段，方便检查对话。")
            btn.clicked.connect(lambda checked=False, p=phase: self._set_cycle_phase_for_testing(p))
            row.addWidget(btn, 1)
        return row

    def _style_cycle_cell(self, cell, phase, current=False):
        bg = self.PHASE_COLORS.get(phase, "#f4d9e8")
        fg = self.PHASE_TEXT_COLORS.get(phase, "#543247")
        border = "#7a2e55" if current else "#ffffff"
        width = 2 if current else 1
        weight = "700" if current else "500"
        cell.setStyleSheet(
            f"background: {bg}; color: {fg}; border: {width}px solid {border}; "
            f"border-radius: 5px; font: {weight} 8pt 'Microsoft YaHei UI';"
        )

    def refresh(self):
        try:
            self._do_refresh()
        except Exception as exc:
            parent = self.parent()
            report_exception(getattr(parent, "runtime", None), getattr(parent, "runtime_logger", None), "status_dialog", "refresh", exc)

    def _do_refresh(self):
        snapshot = self.drive.snapshot()
        values = snapshot.get("values", {})
        for key, label, _hint, _color in self.drive_metrics:
            value = int(round(values.get(key, 0)))
            self.bars[key].setValue(value)
            self.value_labels[key].setText(str(value))

        body_line = ""
        if self.physiology is not None:
            physio_snap = self.physiology.snapshot()
            physio_values = physio_snap.get("values", {})
            for key, _label, _color in self.PHYSIO_METRICS:
                val = int(round(physio_values.get(key, 50.0)))
                if key in self.physio_bars:
                    self.physio_bars[key].setValue(val)
                if key in self.physio_value_labels:
                    self.physio_value_labels[key].setText(str(val))
            body = physio_snap.get("body", {})
            if body:
                body_line = (
                    f"身体：身高 {body.get('height_cm', 162):.0f}cm / "
                    f"体重 {body.get('weight_kg', 48):.2f}kg / "
                    f"年龄 {body.get('age_years', 22)}岁 / "
                    f"生日 {body.get('birthday', '06-01')}\n"
                    f"饱食度 {body.get('satiety', 0):.0f} / 水分 {body.get('hydration', 0):.0f} / "
                    f"今日进餐 {body.get('meals_today', 0)}/3 / 喝水 {body.get('water_today', 0)}次\n"
                    f"寿命进度 {body.get('life_progress_years', 22):.2f}/{body.get('life_expectancy_years', 80):.0f} 年"
                )

        if self.body_cycle is not None:
            try:
                cycle_text = self.body_cycle.build_status_text()
                self.cycle_label.setText(cycle_text)
                sexual = self.body_cycle.get_sexual_status()
                level = int(round(sexual.get("level", 0.0)))
                self.intimacy_bar.setValue(level)
                status_text = f"{sexual.get('label', '')} {level}"
                self.intimacy_value_label.setText(status_text)
                self.intimacy_value_label.setToolTip(status_text)
                self.growth_label.setText(f"当前亲密需求增长速度：x{sexual.get('growth_multiplier', 1.0):.1f}；深色边框是今天。")
                calendar_items = self.body_cycle.build_cycle_calendar()
                for index, item in enumerate(calendar_items):
                    if index >= len(self.cycle_cells):
                        break
                    cell = self.cycle_cells[index]
                    cell.setVisible(True)
                    current = bool(item.get("is_current"))
                    text = f">{item.get('day')}" if current else str(item.get("day"))
                    cell.setText(text)
                    cell.setToolTip(
                        f"第 {item.get('day')} 天：{item.get('label')}，亲密需求增长 x{item.get('growth_multiplier', 1.0):.1f}"
                    )
                    self._style_cycle_cell(cell, item.get("phase", ""), current=current)
                for cell in self.cycle_cells[len(calendar_items):]:
                    cell.setVisible(False)
            except Exception as exc:
                parent = self.parent()
                report_exception(getattr(parent, "runtime", None), getattr(parent, "runtime_logger", None), "status_dialog", "refresh_cycle", exc)
                self.cycle_label.setText("")
        else:
            self.cycle_label.setText("")
            self.intimacy_bar.setValue(0)
            self.intimacy_value_label.setText("未同步")

        dominant = snapshot.get("dominant", "")
        labels = {key: label for key, label, *_rest in self.drive_metrics}
        dominant_label = labels.get(dominant, dominant)
        streak = snapshot.get("proactive_streak", 0)
        last_action = snapshot.get("last_action_type") or "暂无"
        mood = snapshot.get("mood", "quiet")
        goal = snapshot.get("active_goal", "安静待在旁边")
        inner = self.inner_monologue(mood, goal)
        relation_line = "关系阶段：未同步"
        writing_line = ""
        profile_line = "用户侧写：未同步"
        if self.life is not None:
            if hasattr(self.life, "relationship_profile"):
                profile = self.life.relationship_profile(getattr(self.life, "user_gender", ""))
                relation_line = (
                    f"关系：{profile.get('label', '')} / {profile.get('branch_label', '')}"
                    f"（{self.life.relationship_score:.0f}）"
                )
            else:
                stage, _attitude = self.life.relationship_stage()
                relation_line = f"关系阶段：{stage}（{self.life.relationship_score:.0f}/100）"
            user_profile = getattr(self.life, "user_profile", None)
            if user_profile is not None:
                try:
                    profile = user_profile.snapshot()
                    profile_line = (
                        f"用户侧写：{profile.get('mbti', '未知')} "
                        f"({profile.get('confidence', 0):.0f}%)；"
                        f"{'；'.join(profile.get('adaptation_rules', [])[:2])}"
                    )
                except Exception as exc:
                    parent = self.parent()
                    report_exception(getattr(parent, "runtime", None), getattr(parent, "runtime_logger", None), "status_dialog", "user_profile_snapshot", exc)
                    profile_line = "用户侧写：读取失败"
            if self.life.novel.get("title"):
                writing_line = f"\n小说：《{self.life.novel.get('title')}》 {self.life.novel.get('chapter', 0)}/{self.life.novel.get('target_chapters', 8)}"
                writing_line += f"\n今日写作：{self.life.novel_words_today}/{self.novel_daily_word_limit} 字，{self.life.novel_chapters_today}/{self.novel_daily_chapter_limit} 章"
            away = self.life.away_label()
            if away:
                writing_line += f"\n日历：{away}"
        self.mood_label.setText(
            f"{relation_line}\n"
            f"身份：情感陪伴朋友{writing_line}\n"
            f"{body_line}\n"
            f"{profile_line}\n"
            f"心境：{mood}\n"
            f"当前目标：{goal}\n"
            f"内心独白：{inner}\n"
            f"最强驱动：{dominant_label}\n"
            f"连续主动次数：{streak}\n"
            f"上一次自主行动：{last_action}"
        )
        history = snapshot.get("intent_history") or []
        if history:
            lines = [
                f"{item.get('time', '')[-8:]}  {item.get('type', '')}：{item.get('reason', '')}"
                for item in reversed(history[-5:])
            ]
        else:
            lines = ["暂无行动记录。"]
        self.intent_log.setPlainText("\n".join(lines))

    def inner_monologue(self, mood, goal):
        templates = {
            "curious": "我想多知道一点，但要问得轻一点。",
            "attached": "想靠近他一点，不过不能太黏。",
            "worried": "他如果有点累，我应该先温柔一点。",
            "relaxed": "现在的气氛很安稳，可以慢慢陪着。",
            "tired": "先安静一会儿，别打扰他。",
            "playful": "感觉可以用轻松一点的方式开口。",
            "quiet": "还没到开口的时候，先观察。",
        }
        return templates.get(mood, goal)

    def _do_action(self, action):
        parent = self.parent()
        if parent is None:
            return
        try:
            if action == "feed" and hasattr(parent, "interact_with_pet"):
                parent.interact_with_pet("feed")
            elif action == "drink" and hasattr(parent, "offer_drink_to_pet"):
                parent.offer_drink_to_pet()
            elif action == "rest" and hasattr(parent, "physiology"):
                parent.physiology.on_rest()
            elif action == "pat" and hasattr(parent, "interact_with_pet"):
                parent.interact_with_pet("pat")
        except Exception as exc:
            report_exception(getattr(parent, "runtime", None), getattr(parent, "runtime_logger", None), "status_dialog", "quick_action", exc, action=action)

    def _set_cycle_phase_for_testing(self, phase):
        if self.body_cycle is None:
            return
        try:
            self.body_cycle.set_phase_for_testing(phase)
            if self.physiology is not None:
                self.physiology.body_cycle = self.body_cycle
            self.refresh()
        except Exception as exc:
            parent = self.parent()
            report_exception(getattr(parent, "runtime", None), getattr(parent, "runtime_logger", None), "status_dialog", "set_cycle_phase", exc, phase=phase)


class RelationshipDialog(QDialog):
    def __init__(self, life, config=None, parent=None):
        super().__init__(parent)
        self.life = life
        self.config = dict(config or {})
        self.setWindowTitle("关系面板")
        self.resize(560, 520)
        self.setMinimumSize(500, 460)
        self.setStyleSheet(
            """
            QDialog {
                background: #fff6fb;
                color: #543247;
                font: 10pt "Microsoft YaHei UI";
            }
            QLabel#titleLabel {
                color: #8f2d5a;
                font: 16pt "Microsoft YaHei UI";
                font-weight: 700;
            }
            QLabel#sectionTitle {
                color: #8f2d5a;
                font: 10pt "Microsoft YaHei UI";
                font-weight: 700;
                padding-top: 4px;
            }
            QLabel#panel, QTextEdit#panel {
                background: rgba(255, 255, 255, 228);
                border: 1px solid rgba(235, 144, 188, 210);
                border-radius: 8px;
                padding: 9px;
                color: #684158;
            }
            QProgressBar {
                background: rgba(255, 255, 255, 215);
                border: 1px solid #e89abe;
                border-radius: 5px;
            }
            QProgressBar::chunk {
                background: #e86fa6;
                border-radius: 4px;
            }
            """
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        title = QLabel("关系面板")
        title.setObjectName("titleLabel")
        root.addWidget(title)

        self.summary = QLabel("")
        self.summary.setObjectName("panel")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

        self.score_bar = QProgressBar()
        self.score_bar.setRange(0, 220)
        self.score_bar.setTextVisible(False)
        self.score_bar.setFixedHeight(12)
        root.addWidget(self.score_bar)

        branch_title = QLabel("当前分支")
        branch_title.setObjectName("sectionTitle")
        root.addWidget(branch_title)
        self.branch = QLabel("")
        self.branch.setObjectName("panel")
        self.branch.setWordWrap(True)
        root.addWidget(self.branch)

        stages_title = QLabel("可能阶段")
        stages_title.setObjectName("sectionTitle")
        root.addWidget(stages_title)
        self.stage_text = QTextEdit()
        self.stage_text.setObjectName("panel")
        self.stage_text.setReadOnly(True)
        root.addWidget(self.stage_text, 1)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(800)
        self.refresh()

    def refresh(self):
        gender = self.config.get("user_gender", "")
        if hasattr(self.life, "relationship_profile"):
            profile = self.life.relationship_profile(gender)
        else:
            stage, attitude = self.life.relationship_stage()
            profile = {
                "label": stage,
                "attitude": attitude,
                "score": getattr(self.life, "relationship_score", 0.0),
                "gender": gender or "未透露",
                "branch": "neutral",
                "branch_label": stage,
                "remembered": "",
                "stages": [],
            }
        score = float(profile.get("score", 0.0))
        self.score_bar.setValue(max(0, min(220, int(round(score)))))
        remembered = profile.get("remembered", "")
        remembered_line = f"\n已确认关系：{remembered}" if remembered else ""
        self.summary.setText(
            f"当前关系：{profile.get('label', '')}\n"
            f"亲近度：{score:.1f}\n"
            f"用户性别：{profile.get('gender', '未透露')}{remembered_line}"
        )
        branch_notes = {
            "female_friendship": "女性用户分支：关系优先按朋友、好朋友、闺蜜、亲密闺蜜发展，不会因为分数上升自动变成恋人。",
            "male_romance_possible": "男性用户分支：关系会从朋友到密友，再到暧昧或恋人，但仍需要对话和记忆里的确认。",
            "neutral": "未透露分支：关系按朋友、密友、重要的人、灵魂伙伴发展，不强行进入恋爱线。",
        }
        self.branch.setText(
            f"{profile.get('branch_label', '')}\n"
            f"{branch_notes.get(profile.get('branch', 'neutral'), '')}\n"
            f"态度基调：{profile.get('attitude', '')}"
        )
        lines = []
        for item in profile.get("stages", []):
            mark = ">" if score >= float(item.get("score", 0.0)) else " "
            lines.append(f"{mark} {item.get('score', 0):>3}  {item.get('label', '')}：{item.get('attitude', '')}")
        self.stage_text.setPlainText("\n".join(lines))
