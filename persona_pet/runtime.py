"""Lightweight agent runtime: events, tracing, and background task hygiene."""

import json
import inspect
import os
import queue
import threading
import time
import traceback
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field


def _now_wall():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _safe_payload(payload):
    if payload is None:
        return {}
    if isinstance(payload, dict):
        result = {}
        for key, value in payload.items():
            if any(token in str(key).lower() for token in ("key", "token", "secret", "password")):
                result[key] = "***"
            else:
                result[key] = value
        return result
    return {"value": payload}


@dataclass
class RuntimeEvent:
    type: str
    payload: dict = field(default_factory=dict)
    level: str = "info"
    trace_id: str = ""
    span_id: str = ""
    created_at: str = field(default_factory=_now_wall)


class CancelToken:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self):
        self._event.set()

    def is_cancelled(self):
        return self._event.is_set()

    def raise_if_cancelled(self):
        if self.is_cancelled():
            raise RuntimeError("task cancelled")


@dataclass
class RuntimeTask:
    id: str
    name: str
    kind: str = "thread"
    status: str = "pending"
    resources: tuple = field(default_factory=tuple)
    created_at: str = field(default_factory=_now_wall)
    started_at: str = ""
    finished_at: str = ""
    error: str = ""
    elapsed_ms: float = 0.0
    token: CancelToken = field(default_factory=CancelToken)
    thread: object = None

    def cancel(self):
        self.token.cancel()

    def is_cancelled(self):
        return self.token.is_cancelled()


class RuntimeSpan:
    def __init__(self, runtime, name, kind="internal", payload=None, parent_id=""):
        self.runtime = runtime
        self.name = str(name or "span")
        self.kind = str(kind or "internal")
        self.payload = _safe_payload(payload)
        self.parent_id = parent_id
        self.trace_id = runtime.current_trace_id() or str(uuid.uuid4())
        self.span_id = str(uuid.uuid4())
        self.started_at = time.monotonic()

    def __enter__(self):
        self.runtime._push_span(self)
        self.runtime.emit(
            "span.start",
            {"name": self.name, "kind": self.kind, "parent_id": self.parent_id, **self.payload},
            trace_id=self.trace_id,
            span_id=self.span_id,
        )
        return self

    def __exit__(self, exc_type, exc, _tb):
        elapsed_ms = round((time.monotonic() - self.started_at) * 1000.0, 1)
        payload = {"name": self.name, "kind": self.kind, "elapsed_ms": elapsed_ms}
        if exc is not None:
            payload["error"] = str(exc)
            payload["traceback"] = traceback.format_exc()[-3000:]
            level = "error"
        else:
            level = "info"
        self.runtime.emit("span.end", payload, level=level, trace_id=self.trace_id, span_id=self.span_id)
        self.runtime._pop_span(self)
        return False


class AgentRuntime:
    def __init__(self, log_dir="", logger=None, max_events=400):
        self.log_dir = log_dir
        self.logger = logger or (lambda *parts: None)
        self.max_events = int(max_events)
        self.lock = threading.Lock()
        self.events = []
        self.queue = queue.Queue()
        self.local = threading.local()
        self.log_path = os.path.join(log_dir, "agent_runtime.jsonl") if log_dir else ""
        self.tasks = {}
        self.resource_locks = {}

    def current_span(self):
        stack = getattr(self.local, "span_stack", None) or []
        return stack[-1] if stack else None

    def current_trace_id(self):
        span = self.current_span()
        return span.trace_id if span else ""

    def _push_span(self, span):
        stack = getattr(self.local, "span_stack", None)
        if stack is None:
            stack = []
            self.local.span_stack = stack
        stack.append(span)

    def _pop_span(self, span):
        stack = getattr(self.local, "span_stack", None) or []
        if stack and stack[-1] is span:
            stack.pop()
        elif span in stack:
            stack.remove(span)

    @contextmanager
    def span(self, name, kind="internal", payload=None):
        parent = self.current_span()
        with RuntimeSpan(self, name, kind=kind, payload=payload, parent_id=parent.span_id if parent else ""):
            yield

    def emit(self, event_type, payload=None, level="info", trace_id="", span_id=""):
        active = self.current_span()
        event = RuntimeEvent(
            type=str(event_type or "event"),
            payload=_safe_payload(payload),
            level=str(level or "info"),
            trace_id=trace_id or (active.trace_id if active else ""),
            span_id=span_id or (active.span_id if active else ""),
        )
        row = {
            "created_at": event.created_at,
            "level": event.level,
            "type": event.type,
            "trace_id": event.trace_id,
            "span_id": event.span_id,
            "payload": event.payload,
        }
        with self.lock:
            self.events.append(event)
            self.events = self.events[-self.max_events :]
        self.queue.put(event)
        if self.log_path:
            try:
                os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
                with open(self.log_path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            except Exception:
                pass
        try:
            self.logger(f"RUNTIME_{event.type.upper().replace('.', '_')}", event.payload)
        except Exception:
            pass
        return event

    def consume_events(self):
        with self.lock:
            events = list(self.events)
            self.events = []
        return events

    def _resource_lock(self, resource):
        with self.lock:
            lock = self.resource_locks.get(resource)
            if lock is None:
                lock = threading.Lock()
                self.resource_locks[resource] = lock
            return lock

    def task_snapshot(self):
        with self.lock:
            return {
                task_id: {
                    "id": task.id,
                    "name": task.name,
                    "kind": task.kind,
                    "status": task.status,
                    "resources": list(task.resources),
                    "created_at": task.created_at,
                    "started_at": task.started_at,
                    "finished_at": task.finished_at,
                    "error": task.error,
                    "elapsed_ms": task.elapsed_ms,
                    "cancelled": task.is_cancelled(),
                }
                for task_id, task in self.tasks.items()
            }

    def cancel_task(self, task_id):
        with self.lock:
            task = self.tasks.get(task_id)
        if not task:
            return False
        task.cancel()
        self.emit("task.cancel_requested", {"task_id": task_id, "name": task.name})
        return True

    def cancel_by_name(self, name):
        matched = []
        with self.lock:
            tasks = list(self.tasks.values())
        for task in tasks:
            if task.name == name and task.status in ("pending", "running"):
                task.cancel()
                matched.append(task.id)
        if matched:
            self.emit("task.cancel_requested", {"name": name, "task_ids": matched})
        return matched

    def _call_task_fn(self, fn, token):
        try:
            signature = inspect.signature(fn)
        except (TypeError, ValueError):
            return fn()
        params = list(signature.parameters.values())
        for param in params:
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                return fn(token)
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                return fn(cancel_token=token)
            if param.name in ("token", "cancel_token"):
                if param.kind == inspect.Parameter.KEYWORD_ONLY:
                    return fn(**{param.name: token})
                return fn(token)
        return fn()

    def run_background(self, name, fn, kind="thread", payload=None, daemon=True, resources=(), timeout=None):
        task = RuntimeTask(
            id=str(uuid.uuid4()),
            name=str(name or "task"),
            kind=str(kind or "thread"),
            resources=tuple(str(item) for item in (resources or ()) if item),
        )
        with self.lock:
            self.tasks[task.id] = task
        self.emit("task.queued", {"task_id": task.id, "name": task.name, "resources": list(task.resources), **_safe_payload(payload)})

        def wrapper():
            locks = [self._resource_lock(resource) for resource in task.resources]
            start = time.monotonic()
            try:
                for lock in locks:
                    lock.acquire()
                task.token.raise_if_cancelled()
                task.status = "running"
                task.started_at = _now_wall()
                self.emit("task.start", {"task_id": task.id, "name": task.name, "resources": list(task.resources)})
                with self.span(name, kind=kind, payload={"task_id": task.id, **_safe_payload(payload)}):
                    result = self._call_task_fn(fn, task.token)
                if timeout is not None and (time.monotonic() - start) > float(timeout):
                    self.emit("task.timeout", {"task_id": task.id, "name": task.name, "timeout": timeout}, level="warning")
                task.status = "cancelled" if task.is_cancelled() else "done"
                return result
            except Exception as exc:
                task.status = "cancelled" if task.is_cancelled() else "error"
                task.error = str(exc)
                self.emit(
                    "task.error",
                    {"task_id": task.id, "name": name, "error": str(exc), "traceback": traceback.format_exc()[-3000:]},
                    level="error",
                )
                raise
            finally:
                task.elapsed_ms = round((time.monotonic() - start) * 1000.0, 1)
                task.finished_at = _now_wall()
                self.emit(
                    "task.finish",
                    {"task_id": task.id, "name": task.name, "status": task.status, "elapsed_ms": task.elapsed_ms},
                    level="error" if task.status == "error" else "info",
                )
                for lock in reversed(locks):
                    try:
                        lock.release()
                    except Exception:
                        pass

        thread = threading.Thread(target=wrapper, daemon=daemon, name=f"persona-{name[:32]}")
        task.thread = thread
        thread.start()
        return task


_DEFAULT_RUNTIME = AgentRuntime()


def get_default_runtime():
    return _DEFAULT_RUNTIME
