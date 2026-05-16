"""Tool permission manifests, risk scoring, dry-run previews, and guardrails."""

from dataclasses import dataclass, field
from urllib.parse import urlparse


RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class ActionSchema:
    required_text: bool = False
    max_text_chars: int = 4000
    require_http_url: bool = False
    allow_empty_text: bool = True


@dataclass
class ToolActionPolicy:
    permission: str
    risk: str = "low"
    requires_confirmation: bool = True
    dry_run: bool = True
    schema: ActionSchema = field(default_factory=ActionSchema)
    allow_domains: tuple = field(default_factory=tuple)
    deny_domains: tuple = field(default_factory=tuple)
    deny_keywords: tuple = field(default_factory=tuple)


@dataclass
class ToolManifest:
    name: str
    permissions: tuple = field(default_factory=tuple)
    dangerous_actions: tuple = field(default_factory=tuple)
    requires_confirmation: bool = True
    audit: bool = True
    max_text_chars: int = 4000
    actions: dict = field(default_factory=dict)


@dataclass
class ToolDecision:
    allowed: bool
    reason: str = ""
    tool: str = ""
    action: str = ""
    permission: str = ""
    risk: str = "low"
    requires_confirmation: bool = True
    dry_run_available: bool = True
    preview: dict = field(default_factory=dict)

    def as_dict(self):
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "tool": self.tool,
            "action": self.action,
            "permission": self.permission,
            "risk": self.risk,
            "requires_confirmation": self.requires_confirmation,
            "dry_run_available": self.dry_run_available,
            "preview": self.preview,
        }


BROWSER_DENY_KEYWORDS = (
    "login",
    "sign in",
    "signin",
    "password",
    "captcha",
    "payment",
    "pay",
    "checkout",
    "transfer",
    "delete",
    "remove",
    "download",
    "upload",
    "send message",
    "send email",
    "bank",
    "wallet",
    "credit card",
    "admin",
)

BROWSER_DENY_DOMAINS = (
    "paypal.com",
    "stripe.com",
    "alipay.com",
    "weixin.qq.com",
    "bank",
    "checkout",
    "login",
    "accounts.google.com",
    "account.microsoft.com",
)

BROWSER_ALLOW_DOMAINS = (
    "example.com",
    "wikipedia.org",
    "github.com",
    "docs.python.org",
    "huggingface.co",
    "openai.com",
    "developer.mozilla.org",
)


TOOL_MANIFESTS = {
    "file_agent": ToolManifest(
        name="file_agent",
        permissions=("create:folder", "create:docx", "create:pptx"),
        dangerous_actions=("overwrite", "delete", "outside_agent_files"),
        requires_confirmation=True,
        max_text_chars=12000,
        actions={
            "folder": ToolActionPolicy(
                permission="create:folder",
                risk="low",
                schema=ActionSchema(required_text=True, max_text_chars=240, allow_empty_text=False),
            ),
            "docx": ToolActionPolicy(
                permission="create:docx",
                risk="medium",
                schema=ActionSchema(required_text=True, max_text_chars=12000, allow_empty_text=False),
            ),
            "pptx": ToolActionPolicy(
                permission="create:pptx",
                risk="medium",
                schema=ActionSchema(required_text=True, max_text_chars=12000, allow_empty_text=False),
            ),
        },
    ),
    "browser_agent": ToolManifest(
        name="browser_agent",
        permissions=("browser:open_url", "browser:observe", "browser:click_text", "browser:type_text"),
        dangerous_actions=("login", "payment", "delete", "send_message", "local_file", "download", "upload"),
        requires_confirmation=True,
        max_text_chars=2048,
        actions={
            "open_url": ToolActionPolicy(
                permission="browser:open_url",
                risk="medium",
                schema=ActionSchema(required_text=True, max_text_chars=2048, require_http_url=True, allow_empty_text=False),
                allow_domains=BROWSER_ALLOW_DOMAINS,
                deny_domains=BROWSER_DENY_DOMAINS,
                deny_keywords=BROWSER_DENY_KEYWORDS,
            ),
            "observe": ToolActionPolicy(
                permission="browser:observe",
                risk="low",
                requires_confirmation=False,
                schema=ActionSchema(required_text=False, max_text_chars=0, allow_empty_text=True),
            ),
            "click_text": ToolActionPolicy(
                permission="browser:click_text",
                risk="medium",
                schema=ActionSchema(required_text=True, max_text_chars=80, allow_empty_text=False),
                deny_keywords=BROWSER_DENY_KEYWORDS,
            ),
            "type_text": ToolActionPolicy(
                permission="browser:type_text",
                risk="high",
                schema=ActionSchema(required_text=True, max_text_chars=120, allow_empty_text=False),
                deny_keywords=BROWSER_DENY_KEYWORDS,
            ),
        },
    ),
}


def get_tool_manifest(name):
    return TOOL_MANIFESTS.get(str(name or ""))


def _domain_matches(hostname, patterns):
    host = str(hostname or "").lower()
    for pattern in patterns or ():
        pattern = str(pattern or "").lower()
        if not pattern:
            continue
        if pattern in host or host.endswith("." + pattern):
            return pattern
    return ""


def _browser_local_or_internal(url):
    lowered = str(url or "").strip().lower()
    if lowered.startswith(("file:", "about:", "chrome:", "edge:", "data:", "javascript:")):
        return True
    parsed = urlparse(lowered)
    host = parsed.hostname or ""
    return host in ("localhost", "127.0.0.1", "::1") or host.startswith("127.")


def _policy_for(manifest, action_kind):
    action_kind = str(action_kind or "")
    policy = manifest.actions.get(action_kind) if manifest else None
    if policy is not None:
        return policy
    if not manifest:
        return None
    if manifest.name == "browser_agent":
        permission = f"browser:{action_kind}"
    elif manifest.name == "file_agent":
        permission = {
            "folder": "create:folder",
            "docx": "create:docx",
            "pptx": "create:pptx",
        }.get(action_kind, action_kind)
    else:
        permission = action_kind
    return ToolActionPolicy(permission=permission, risk="high", schema=ActionSchema(max_text_chars=manifest.max_text_chars))


def _schema_error(schema, text):
    text = str(text or "")
    if schema.required_text and not text.strip():
        return "input_required"
    if not schema.allow_empty_text and not text.strip():
        return "input_empty"
    if schema.max_text_chars and len(text) > schema.max_text_chars:
        return "input_too_long"
    if schema.require_http_url:
        parsed = urlparse(text.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return "invalid_http_url"
    return ""


def _risk_at_least(risk, threshold):
    return RISK_ORDER.get(str(risk or "low"), 1) >= RISK_ORDER.get(str(threshold or "low"), 1)


def assess_tool_action(tool_name, action_kind="", text="", runtime=None):
    tool_name = str(tool_name or "")
    action_kind = str(action_kind or "")
    text = str(text or "")
    manifest = get_tool_manifest(tool_name)
    if manifest is None:
        return ToolDecision(False, "unknown_tool", tool=tool_name, action=action_kind, risk="critical")

    policy = _policy_for(manifest, action_kind)
    if policy is None:
        return ToolDecision(False, "unknown_action", tool=tool_name, action=action_kind, risk="critical")

    preview = {
        "tool": tool_name,
        "action": action_kind,
        "input_chars": len(text),
        "dry_run": True,
        "would_execute": action_kind,
    }
    decision = ToolDecision(
        allowed=True,
        tool=tool_name,
        action=action_kind,
        permission=policy.permission,
        risk=policy.risk,
        requires_confirmation=manifest.requires_confirmation or policy.requires_confirmation or _risk_at_least(policy.risk, "medium"),
        dry_run_available=bool(policy.dry_run),
        preview=preview,
    )

    error = _schema_error(policy.schema, text)
    if error:
        decision.allowed = False
        decision.reason = error
        return decision

    if policy.permission not in manifest.permissions:
        decision.allowed = False
        decision.reason = f"permission_denied:{policy.permission}"
        return decision

    lowered = text.strip().lower()
    for keyword in policy.deny_keywords:
        if keyword and str(keyword).lower() in lowered:
            decision.allowed = False
            decision.reason = f"dangerous_keyword:{keyword}"
            decision.risk = "critical"
            return decision

    if tool_name == "browser_agent":
        parsed = urlparse(text.strip()) if text.strip() else None
        host = parsed.hostname if parsed else ""
        preview["domain"] = host or ""
        if action_kind == "open_url":
            preview["url"] = text.strip()
        if _browser_local_or_internal(text):
            decision.allowed = False
            decision.reason = "browser_local_or_internal_target"
            decision.risk = "critical"
            return decision
        matched_deny = _domain_matches(host, policy.deny_domains)
        if matched_deny:
            decision.allowed = False
            decision.reason = f"domain_denied:{matched_deny}"
            decision.risk = "critical"
            return decision
        matched_allow = _domain_matches(host, policy.allow_domains)
        if matched_allow:
            decision.risk = "low" if action_kind == "open_url" else decision.risk
            preview["domain_policy"] = "allow"
        elif action_kind == "open_url":
            preview["domain_policy"] = "unknown_requires_confirmation"
            decision.risk = "medium"
            decision.requires_confirmation = True

    if runtime is not None and manifest.audit and decision.allowed:
        runtime.emit(
            "tool.authorized",
            {
                "tool": tool_name,
                "action": action_kind,
                "permission": decision.permission,
                "risk": decision.risk,
                "requires_confirmation": decision.requires_confirmation,
            },
        )
    return decision


def validate_tool_action(tool_name, action_kind="", text="", runtime=None):
    decision = assess_tool_action(tool_name, action_kind, text=text, runtime=runtime)
    return decision.allowed, decision.reason


def build_tool_dry_run(tool_name, action_kind="", text="", runtime=None):
    decision = assess_tool_action(tool_name, action_kind, text=text, runtime=runtime)
    payload = decision.as_dict()
    if runtime is not None:
        runtime.emit(
            "tool.dry_run",
            {
                "tool": decision.tool,
                "action": decision.action,
                "allowed": decision.allowed,
                "risk": decision.risk,
                "reason": decision.reason,
                "preview": decision.preview,
            },
            level="warning" if not decision.allowed else "info",
        )
    return payload


def audit_tool_event(runtime, event_type, tool_name, payload=None, level="info"):
    if runtime is None:
        return
    manifest = get_tool_manifest(tool_name)
    if manifest is not None and manifest.audit:
        runtime.emit(f"tool.{event_type}", {"tool": tool_name, **(payload or {})}, level=level)
