"""Local todo/task system for PersonaPet.

The design is intentionally small: tasks are stored in the existing memory
meta store and can be controlled from normal chat text without adding a web
backend or new heavy dependencies.
"""

import datetime
import re
import time

TODO_META_KEY = "todo_state"
TODO_MAX_ITEMS = 50


class PersonaTodoList:
    def __init__(self, memory_store, meta_key=TODO_META_KEY, logger=None):
        self.memory_store = memory_store
        self.meta_key = meta_key
        self.log_runtime = logger or (lambda *parts: None)
        saved = self.memory_store.load_meta_json(self.meta_key, {})
        if not isinstance(saved, dict):
            saved = {}
        raw_items = saved.get("items", [])
        self.items = [self._clean_loaded_item(item) for item in raw_items if isinstance(item, dict)]
        self.items = [item for item in self.items if item]
        self.next_id = int(saved.get("next_id") or 1)
        if self.items:
            self.next_id = max(self.next_id, max(item["id"] for item in self.items) + 1)
        self.last_saved_at = 0.0
        self._dirty = False

    def _clean_loaded_item(self, item):
        content = self._clean_content(item.get("content"))
        if not content:
            return None
        status = str(item.get("status") or "pending")
        if status not in {"pending", "completed"}:
            status = "pending"
        return {
            "id": int(item.get("id") or 0),
            "content": content,
            "status": status,
            "created_at": str(item.get("created_at") or ""),
            "completed_at": str(item.get("completed_at") or ""),
        }

    def _clean_content(self, content):
        content = re.sub(r"\s+", " ", str(content or "")).strip(" ，,。.!！?？:：")
        return content[:120]

    def add(self, content):
        content = self._clean_content(content)
        if not content:
            return False, "待办内容不能为空。", None
        if len(self.items) >= TODO_MAX_ITEMS:
            return False, f"待办最多保留 {TODO_MAX_ITEMS} 条，请先完成或删除一些。", None
        item = {
            "id": self.next_id,
            "content": content,
            "status": "pending",
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "completed_at": "",
        }
        self.next_id += 1
        self.items.append(item)
        self.save()
        return True, f"已加入待办：#{item['id']} {content}", item

    def pending_items(self):
        return [item for item in self.items if item["status"] == "pending"]

    def completed_items(self):
        return [item for item in self.items if item["status"] == "completed"]

    def render(self, include_completed=False):
        items = self.items if include_completed else self.pending_items()
        if not items:
            return "暂无待办。"
        lines = []
        for item in items[:12]:
            mark = "x" if item["status"] == "completed" else " "
            lines.append(f"[{mark}] #{item['id']} {item['content']}")
        if len(items) > 12:
            lines.append(f"... 还有 {len(items) - 12} 条")
        completed = len(self.completed_items())
        total = len(self.items)
        lines.append(f"完成进度：{completed}/{total}")
        return "\n".join(lines)

    def complete(self, item_id=None, content_hint=""):
        item = self._find_item(item_id=item_id, content_hint=content_hint, pending_only=True)
        if not item:
            return False, "没有找到对应的未完成待办。", None
        item["status"] = "completed"
        item["completed_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save()
        return True, f"已完成待办：#{item['id']} {item['content']}", item

    def delete(self, item_id=None, content_hint=""):
        item = self._find_item(item_id=item_id, content_hint=content_hint, pending_only=False)
        if not item:
            return False, "没有找到要删除的待办。", None
        self.items = [current for current in self.items if current["id"] != item["id"]]
        self.save()
        return True, f"已删除待办：#{item['id']} {item['content']}", item

    def clear_completed(self):
        before = len(self.items)
        self.items = [item for item in self.items if item["status"] != "completed"]
        removed = before - len(self.items)
        if removed:
            self.save()
        return removed

    def _find_item(self, item_id=None, content_hint="", pending_only=False):
        candidates = self.pending_items() if pending_only else list(self.items)
        if item_id is not None:
            for item in candidates:
                if item["id"] == int(item_id):
                    return item
        hint = self._clean_content(content_hint)
        if hint:
            compact_hint = re.sub(r"\s+", "", hint)
            for item in candidates:
                compact_item = re.sub(r"\s+", "", item["content"])
                if compact_hint in compact_item or compact_item in compact_hint:
                    return item
        if len(candidates) == 1:
            return candidates[0]
        return None

    def save(self):
        self._dirty = True
        now = time.monotonic()
        if now - self.last_saved_at < 10.0:
            return
        self.flush_dirty()

    def flush_dirty(self):
        if not self._dirty:
            return
        self._dirty = False
        self.last_saved_at = time.monotonic()
        self.memory_store.save_meta_json(
            self.meta_key,
            {
                "items": self.items,
                "next_id": self.next_id,
            },
        )


def parse_todo_command(text):
    raw = (text or "").strip()
    compact = re.sub(r"\s+", "", raw)
    if not compact:
        return None

    list_terms = ("列出待办", "查看待办", "显示待办", "待办列表", "todo列表", "todos")
    if any(term.lower() in compact.lower() for term in list_terms) or compact in {"待办", "todo"}:
        return {"action": "list"}

    clear_terms = ("清理已完成待办", "删除已完成待办", "清空已完成待办")
    if any(term in compact for term in clear_terms):
        return {"action": "clear_completed"}

    add_terms = ("创建待办", "新增待办", "添加待办", "加入待办", "记个待办", "记一条待办", "todo")
    if any(term.lower() in compact.lower() for term in add_terms):
        content = raw
        for term in add_terms:
            content = re.sub(re.escape(term), "", content, flags=re.I)
        content = re.sub(r"^(内容|事项|任务)\s*[:：]?", "", content.strip())
        return {"action": "add", "content": content}

    done_terms = ("完成待办", "标记待办完成", "待办完成", "完成任务", "完成todo")
    if any(term.lower() in compact.lower() for term in done_terms):
        return {"action": "complete", **_extract_todo_target(raw, done_terms)}

    delete_terms = ("删除待办", "移除待办", "取消待办", "删掉待办", "删除todo")
    if any(term.lower() in compact.lower() for term in delete_terms):
        return {"action": "delete", **_extract_todo_target(raw, delete_terms)}

    return None


def _extract_todo_target(text, terms):
    item_id = None
    match = re.search(r"#?\s*(\d+)", text)
    if match:
        item_id = int(match.group(1))
    hint = text
    for term in terms:
        hint = re.sub(re.escape(term), "", hint, flags=re.I)
    hint = re.sub(r"#?\s*\d+", "", hint).strip(" ，,。.!！?？:：")
    return {"item_id": item_id, "content_hint": hint}


class TodoMixin:
    def setup_todo_module(self):
        self.todo_list = PersonaTodoList(self.memory, logger=self.runtime_logger)

    def handle_todo_input(self, text):
        command = parse_todo_command(text)
        if not command:
            return False
        if not hasattr(self, "todo_list"):
            self.setup_todo_module()

        action = command["action"]
        if action == "add":
            ok, message, _item = self.todo_list.add(command.get("content", ""))
        elif action == "list":
            ok, message = True, self.todo_list.render(include_completed=True)
        elif action == "complete":
            ok, message, _item = self.todo_list.complete(
                item_id=command.get("item_id"),
                content_hint=command.get("content_hint", ""),
            )
        elif action == "delete":
            ok, message, _item = self.todo_list.delete(
                item_id=command.get("item_id"),
                content_hint=command.get("content_hint", ""),
            )
        elif action == "clear_completed":
            removed = self.todo_list.clear_completed()
            ok, message = True, f"已清理 {removed} 条已完成待办。"
        else:
            return False

        self.chat_input.clear()
        if hasattr(self, "memory_associate_output"):
            self.memory_associate_output(message, source="todo")
        self.show_subtitle(message, voice_text="", duration=5.0)
        self.show_chat_status("待办已更新" if ok else "待办操作失败", seconds=3.0)
        print("TODO_COMMAND =", {"action": action, "ok": ok, "message": message})
        return True

    def save_todo_module(self):
        if hasattr(self, "todo_list"):
            self.todo_list.save()

    def flush_todo_module(self):
        if hasattr(self, "todo_list"):
            self.todo_list.flush_dirty()
