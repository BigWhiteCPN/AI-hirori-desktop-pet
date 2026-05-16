"""Constrained browser automation helper for the desktop pet."""

import json
import os
import re
import time
from dataclasses import dataclass

from persona_pet.error_reporter import report_exception
from persona_pet.tool_permissions import audit_tool_event, assess_tool_action

@dataclass
class BrowserAgentAction:
    kind: str
    target: str = ""
    text: str = ""

BROWSER_AGENT_OPEN_KEYWORDS = ("浏览器打开", "打开网页", "打开网站", "访问网页", "访问网站")

BROWSER_AGENT_OBSERVE_KEYWORDS = ("观察浏览器", "看一下浏览器", "看看浏览器", "浏览器截图", "网页截图", "观察网页")

BROWSER_AGENT_CLICK_KEYWORDS = ("点击", "点一下", "浏览器点击")

BROWSER_AGENT_TYPE_KEYWORDS = ("输入", "填写", "填入")

BROWSER_AGENT_BLOCKED_KEYWORDS = (
    "登录",
    "登陆",
    "login",
    "sign in",
    "signin",
    "密码",
    "password",
    "验证码",
    "captcha",
    "支付",
    "付款",
    "payment",
    "pay",
    "checkout",
    "转账",
    "transfer",
    "银行卡",
    "删除",
    "delete",
    "remove",
    "发消息",
    "发送消息",
    "send message",
    "send email",
    "发邮件",
    "发送邮件",
    "运行命令",
    "执行命令",
    "本地文件",
    "读取文件",
    "file://",
)

def browser_agent_log(event, payload, log_path=None, logger=None):
    try:
        if log_path:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write(time.strftime("%Y-%m-%d %H:%M:%S ") + event + " " + json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as exc:
        report_exception(logger=logger, component="browser_agent", operation="write_log", exc=exc, event=event)
    if logger:
        logger(f"BROWSER_AGENT_{event}", payload)

def browser_agent_block_reason(text):
    compact = re.sub(r"\s+", "", text or "").lower()
    for keyword in BROWSER_AGENT_BLOCKED_KEYWORDS:
        if keyword.lower() in compact:
            return f"包含受限内容：{keyword}"
    without_urls = re.sub(r"https?://[^\s，。；;！!？?\"'<>]+", "", text or "", flags=re.I)
    if re.search(r"(^|[\s\"'：])(?:[a-zA-Z]:\\|\\\\|/[^\s/])", without_urls):
        return "疑似本地文件路径，已拒绝"
    return ""

def browser_agent_extract_url(text):
    match = re.search(r"https?://[^\s，。；;！!？?\"'<>]+", text or "", flags=re.I)
    if match:
        return match.group(0)
    match = re.search(r"(?:打开网页|打开网站|访问网页|访问网站|浏览器打开)\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s，。；;！!？?\"'<>]*)?)", text or "")
    if match:
        return "https://" + match.group(1).strip()
    return ""

def browser_agent_extract_after(text, keywords):
    for keyword in keywords:
        index = text.find(keyword)
        if index == -1:
            continue
        value = text[index + len(keyword):].strip(" ：:，,。.!！?？\"'")
        if value:
            return value
    return ""

def parse_browser_agent_action(text):
    text = (text or "").strip()
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return None, ""

    reason = browser_agent_block_reason(text)
    if reason and any(word in compact for word in ("浏览器", "网页", "网站", "点击", "输入", "填写", "打开")):
        return None, reason

    if any(keyword in compact for keyword in BROWSER_AGENT_OBSERVE_KEYWORDS):
        return BrowserAgentAction("observe"), ""

    if any(keyword in compact for keyword in BROWSER_AGENT_OPEN_KEYWORDS):
        url = browser_agent_extract_url(text)
        if not url:
            return None, "没有识别到要打开的网址"
        return BrowserAgentAction("open_url", target=url), ""

    if "浏览器" in compact and any(keyword in compact for keyword in BROWSER_AGENT_CLICK_KEYWORDS):
        target = browser_agent_extract_after(text, BROWSER_AGENT_CLICK_KEYWORDS)
        target = target.replace("浏览器", "").strip(" ：:，,。.!！?？\"'")
        if not target:
            return None, "没有识别到要点击的网页文字"
        return BrowserAgentAction("click_text", target=target[:80]), ""

    if "浏览器" in compact and any(keyword in compact for keyword in BROWSER_AGENT_TYPE_KEYWORDS):
        value = browser_agent_extract_after(text, BROWSER_AGENT_TYPE_KEYWORDS)
        value = value.replace("浏览器", "").strip(" ：:，,。.!！?？\"'")
        if not value:
            return None, "没有识别到要输入的文字"
        if len(value) > 120:
            return None, "单次输入文字太长，已拒绝"
        return BrowserAgentAction("type_text", text=value), ""

    return None, ""

def describe_browser_agent_action(action):
    if action.kind == "open_url":
        return f"打开独立浏览器窗口并访问：{action.target}"
    if action.kind == "observe":
        return "截取独立浏览器窗口并记录页面信息"
    if action.kind == "click_text":
        return f"点击网页中包含“{action.target}”的元素"
    if action.kind == "type_text":
        return f"向当前网页焦点输入：{action.text}"
    return "未知浏览器动作"

class SafeBrowserAgent:
    def __init__(self, profile_dir, screenshot_dir, log_path=None, logger=None, runtime=None):
        self.profile_dir = profile_dir
        self.screenshot_dir = screenshot_dir
        self.log_path = log_path
        self.logger = logger
        self.runtime = runtime
        self.playwright = None
        self.context = None
        self.page = None

    def ensure_available(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError("浏览器 agent 需要安装 playwright：python -m pip install playwright 后再运行 playwright install chromium") from exc
        return sync_playwright

    def ensure_page(self):
        os.makedirs(self.profile_dir, exist_ok=True)
        os.makedirs(self.screenshot_dir, exist_ok=True)
        if self.page and not self.page.is_closed():
            return self.page

        sync_playwright = self.ensure_available()
        if self.playwright is None:
            self.playwright = sync_playwright().start()
        if self.context is None:
            self.context = self.playwright.chromium.launch_persistent_context(
                self.profile_dir,
                headless=False,
                viewport={"width": 1280, "height": 800},
                accept_downloads=False,
                args=[
                    "--disable-extensions",
                    "--disable-file-system",
                    "--no-default-browser-check",
                    "--disable-sync",
                ],
            )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        return self.page

    def screenshot(self, page):
        os.makedirs(self.screenshot_dir, exist_ok=True)
        path = os.path.join(self.screenshot_dir, f"browser_{time.strftime('%Y%m%d_%H%M%S')}.png")
        page.screenshot(path=path, full_page=False)
        return path

    def page_text_snapshot(self, page):
        try:
            text = page.locator("body").inner_text(timeout=2000)
        except Exception:
            text = ""
        return re.sub(r"\s+", " ", text).strip()[:3000]

    def blocked_page_reason(self, page):
        combined = f"{page.url} {page.title()} {self.page_text_snapshot(page)}".lower()
        for keyword in BROWSER_AGENT_BLOCKED_KEYWORDS:
            if keyword.lower() in combined:
                return f"当前页面包含受限内容：{keyword}"
        return ""

    def execute(self, action):
        decision = assess_tool_action("browser_agent", action.kind, text=action.text or action.target, runtime=self.runtime)
        if not decision.allowed:
            audit_tool_event(
                self.runtime,
                "reject",
                "browser_agent",
                {"action": action.kind, "reason": decision.reason, "risk": decision.risk},
                level="warning",
            )
            raise RuntimeError(f"Browser agent action rejected: {decision.reason}")
        audit_tool_event(
            self.runtime,
            "start",
            "browser_agent",
            {"action": action.kind, "target": action.target[:120], "risk": decision.risk, "preview": decision.preview},
        )
        page = self.ensure_page()
        if action.kind == "open_url":
            if not re.match(r"^https?://", action.target, flags=re.I):
                raise RuntimeError("只允许打开 http/https 网页。")
            page.goto(action.target, wait_until="domcontentloaded", timeout=30000)
        elif action.kind == "observe":
            if page.url == "about:blank":
                page.goto("https://www.example.com", wait_until="domcontentloaded", timeout=30000)
        elif action.kind == "click_text":
            reason = self.blocked_page_reason(page)
            if reason:
                raise RuntimeError(reason)
            locator = page.get_by_text(action.target, exact=False).first
            locator.click(timeout=5000)
        elif action.kind == "type_text":
            reason = self.blocked_page_reason(page)
            if reason:
                raise RuntimeError(reason)
            page.keyboard.type(action.text, delay=15)
        else:
            raise RuntimeError("未知浏览器动作。")

        try:
            page.wait_for_load_state("domcontentloaded", timeout=3000)
        except Exception as exc:
            report_exception(self.runtime, self.logger, "browser_agent", "wait_for_load_state", exc, action=action.kind)
        screenshot_path = self.screenshot(page)
        result = {
            "kind": action.kind,
            "url": page.url,
            "title": page.title(),
            "screenshot": screenshot_path,
            "text_snapshot": self.page_text_snapshot(page),
            "profile": self.profile_dir,
        }
        browser_agent_log("EXECUTE", result, log_path=self.log_path, logger=self.logger)
        audit_tool_event(self.runtime, "done", "browser_agent", {"action": action.kind, "url": page.url, "title": page.title()})
        return result

    def close(self):
        try:
            if self.context:
                self.context.close()
        finally:
            self.context = None
            self.page = None
            if self.playwright:
                try:
                    self.playwright.stop()
                except Exception as exc:
                    report_exception(self.runtime, self.logger, "browser_agent", "playwright_stop", exc)
                self.playwright = None
