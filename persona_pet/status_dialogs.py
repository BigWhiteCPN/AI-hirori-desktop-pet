"""Memory graph and drive status PyQt dialogs."""

import math

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QPainter, QRadialGradient
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QTextEdit, QVBoxLayout, QWidget

class MemoryGraphCanvas(QWidget):
    NODE_COLORS = {
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

        for edge in self.dialog.graph.get("edges", []):
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
        for edge in self.dialog.graph.get("edges", []):
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
        hint = QLabel("点击关系网里的节点查看细节；紫色思考节点表示她把旧记忆重新解释后形成的新心理内容。")
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

    def important_nodes(self):
        nodes = self.graph.get("nodes", {})
        edges = self.graph.get("edges", [])
        connected = {}
        for edge in edges:
            connected[edge.get("source")] = connected.get(edge.get("source"), 0) + int(edge.get("weight", 1))
            connected[edge.get("target")] = connected.get(edge.get("target"), 0) + int(edge.get("weight", 1))
        type_bonus = {"思考": 8, "心情": 5, "类别": 2}
        ranked = sorted(
            nodes.values(),
            key=lambda node: (
                type_bonus.get(node.get("type", ""), 0),
                connected.get(node.get("id"), 0),
                int(node.get("count", 0)),
            ),
            reverse=True,
        )
        return ranked[:34]

    def show_overview(self):
        summary = self.long_term.get("summary", "还没有形成长期记忆。")
        recent = self.short_terms[-5:]
        reflections = [item for item in self.short_terms if item.get("reflection")]
        lines = [f"长期摘要\n{summary}", "", "思考痕迹"]
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

    def focus_node(self, node_id):
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
    def __init__(self, drive, life=None, parent=None, drive_metrics=None, novel_daily_word_limit=1200, novel_daily_chapter_limit=1):
        super().__init__(parent)
        self.drive = drive
        self.life = life
        self.drive_metrics = tuple(drive_metrics or ())
        self.novel_daily_word_limit = int(novel_daily_word_limit)
        self.novel_daily_chapter_limit = int(novel_daily_chapter_limit)
        self.bars = {}
        self.value_labels = {}
        self.setWindowTitle("角色状态")
        self.resize(430, 560)
        self.setMinimumSize(390, 500)
        self.setStyleSheet(
            """
            QDialog {
                background: #fff1f8;
                color: #543247;
                font: 10pt "Microsoft YaHei UI";
            }
            QLabel#driveTitle {
                color: #8f2d5a;
                font: 16pt "Microsoft YaHei UI";
                font-weight: 700;
            }
            QLabel#driveSubTitle {
                color: #8a6178;
            }
            QLabel[class="metricName"] {
                color: #5d3750;
                font-weight: 700;
            }
            QLabel[class="metricHint"] {
                color: #9a7188;
                font-size: 8pt;
            }
            QLabel[class="metricValue"] {
                color: #8f2d5a;
                font-weight: 700;
            }
            QLabel#driveMood {
                background: rgba(255, 255, 255, 228);
                border: 1px solid rgba(222, 112, 168, 210);
                border-radius: 8px;
                padding: 12px;
                color: #684158;
            }
            QTextEdit#intentLog {
                background: rgba(255, 255, 255, 226);
                border: 1px solid rgba(235, 144, 188, 190);
                border-radius: 8px;
                padding: 8px;
                color: #684158;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        title = QLabel("小日和 STATUS")
        title.setObjectName("driveTitle")
        root.addWidget(title)

        subtitle = QLabel("当前同步：内驱 / 记忆 / 主动意图 / 写作生活")
        subtitle.setObjectName("driveSubTitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        for key, label, hint, color in self.drive_metrics:
            block = QVBoxLayout()
            top = QHBoxLayout()
            name = QLabel(f"{label}  {key}")
            name.setProperty("class", "metricName")
            value_label = QLabel("0")
            value_label.setProperty("class", "metricValue")
            value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            top.addWidget(name, 1)
            top.addWidget(value_label)
            block.addLayout(top)

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setFixedHeight(12)
            bar.setStyleSheet(
                "QProgressBar {"
                "background: rgba(255,255,255,210);"
                "border: 1px solid rgba(232,154,190,190);"
                "border-radius: 6px;"
                "}"
                "QProgressBar::chunk {"
                f"background: {color.name()};"
                "border-radius: 5px;"
                "}"
            )
            block.addWidget(bar)

            hint_label = QLabel(hint)
            hint_label.setProperty("class", "metricHint")
            hint_label.setWordWrap(True)
            block.addWidget(hint_label)
            root.addLayout(block)
            self.bars[key] = bar
            self.value_labels[key] = value_label

        self.mood_label = QLabel("")
        self.mood_label.setObjectName("driveMood")
        self.mood_label.setWordWrap(True)
        root.addWidget(self.mood_label)

        self.intent_log = QTextEdit()
        self.intent_log.setObjectName("intentLog")
        self.intent_log.setReadOnly(True)
        self.intent_log.setFixedHeight(96)
        root.addWidget(self.intent_log)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(500)
        self.refresh()

    def refresh(self):
        snapshot = self.drive.snapshot()
        values = snapshot.get("values", {})
        for key, label, _hint, _color in self.drive_metrics:
            value = int(round(values.get(key, 0)))
            self.bars[key].setValue(value)
            self.value_labels[key].setText(str(value))

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
            stage, _attitude = self.life.relationship_stage()
            relation_line = f"关系阶段：{stage}（{self.life.relationship_score:.0f}/100）"
            user_profile = getattr(self.life, "user_profile", None)
            if user_profile is not None:
                try:
                    profile = user_profile.snapshot()
                    profile_line = (
                        f"用户侧写：{profile.get('mbti', '????')} "
                        f"({profile.get('confidence', 0):.0f}%)；"
                        f"{'；'.join(profile.get('adaptation_rules', [])[:2])}"
                    )
                except Exception:
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
