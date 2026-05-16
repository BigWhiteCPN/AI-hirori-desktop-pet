"""Structured reporting for deliberately suppressed exceptions."""

import json
import os
import time
import traceback


def exception_payload(component, operation, exc, **extra):
    payload = {
        "component": str(component or "unknown"),
        "operation": str(operation or "unknown"),
        "error_type": type(exc).__name__,
        "error": str(exc),
    }
    payload.update(extra)
    return payload


def report_exception(runtime=None, logger=None, component="", operation="", exc=None, level="warning", **extra):
    if exc is None:
        exc = RuntimeError("unknown suppressed exception")
    payload = exception_payload(component, operation, exc, **extra)
    payload["traceback"] = traceback.format_exc()[-3000:]
    if runtime is not None:
        try:
            runtime.emit("error.suppressed", payload, level=level)
        except Exception:
            pass
    if logger is not None:
        try:
            logger("ERROR_SUPPRESSED", payload)
        except Exception:
            pass
    return payload


def report_exception_to_file(log_path, component, operation, exc, **extra):
    payload = exception_payload(component, operation, exc, **extra)
    payload["created_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:
        pass
    return payload

