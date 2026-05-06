import os

from PyQt5.QtWidgets import QMessageBox

from persona_pet.browser_agent import browser_agent_log, describe_browser_agent_action, parse_browser_agent_action
from persona_pet.file_agent import (
    describe_file_agent_action,
    execute_file_agent_action,
    file_agent_is_cancel,
    file_agent_is_confirm,
    parse_file_agent_action,
)


class AgentCommandMixin:
    def handle_file_agent_input(self, text):
        if self.pending_file_action:
            if file_agent_is_cancel(text):
                action = self.pending_file_action
                self.pending_file_action = None
                message = f"已取消：{describe_file_agent_action(action)}"
                self.show_subtitle(message, voice_text="", duration=3.2)
                self.show_chat_status("文件操作已取消", seconds=2.4)
                print("FILE_AGENT_CANCEL =", {"action": describe_file_agent_action(action)})
                return True
            if file_agent_is_confirm(text):
                action = self.pending_file_action
                self.pending_file_action = None
                try:
                    path = execute_file_agent_action(
                        action,
                        self.agent_files_dir,
                        logger=self.runtime_logger,
                        max_chars=self.agent_file_name_max_chars,
                    )
                    message = f"已创建：{os.path.basename(path)}\n位置：{os.path.dirname(path)}"
                    self.show_subtitle(message, voice_text="", duration=5.5)
                    self.show_chat_status("文件已创建", seconds=3.2)
                    print("FILE_AGENT_DONE =", {"action": describe_file_agent_action(action), "path": path})
                except Exception as exc:
                    message = f"创建失败：{exc}"
                    self.show_subtitle(message, voice_text="", duration=4.0)
                    self.show_chat_status("文件创建失败", seconds=3.0)
                    print("FILE_AGENT_ERROR =", {"action": describe_file_agent_action(action), "error": str(exc)})
                return True

        action = parse_file_agent_action(text)
        if not action:
            return False

        self.pending_file_action = action
        message = (
            f"准备{describe_file_agent_action(action)}\n"
            f"安全目录：{self.agent_files_dir}\n"
            "回复“确认”执行，或回复“取消”。"
        )
        self.chat_input.clear()
        self.show_subtitle(message, voice_text="", duration=6.5)
        self.show_chat_status("等待确认文件操作", seconds=8.0)
        print("FILE_AGENT_PLAN =", {"action": describe_file_agent_action(action), "dir": self.agent_files_dir})
        return True

    def confirm_browser_agent_action(self, action):
        message = (
            f"{describe_browser_agent_action(action)}\n\n"
            "安全限制：独立浏览器 profile；不登录、不支付、不删除、不发消息、不运行命令、不读取本地文件。\n"
            "本次确认只允许执行这一个动作，执行后授权立刻失效。"
        )
        result = QMessageBox.question(
            self,
            "确认浏览器 agent 动作",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return result == QMessageBox.Yes

    def handle_browser_agent_input(self, text):
        action, reject_reason = parse_browser_agent_action(text)
        if reject_reason:
            message = f"浏览器 agent 已拒绝：{reject_reason}"
            self.chat_input.clear()
            self.show_subtitle(message, voice_text="", duration=4.0)
            self.show_chat_status("浏览器动作被拒绝", seconds=3.0)
            browser_agent_log("REJECT", {"text": text, "reason": reject_reason}, log_path=self.browser_agent_log_path, logger=self.runtime_logger)
            print("BROWSER_AGENT_REJECT =", {"text": text, "reason": reject_reason})
            return True
        if not action:
            return False

        self.chat_input.clear()
        browser_agent_log("PLAN", {"action": describe_browser_agent_action(action), "text": text}, log_path=self.browser_agent_log_path, logger=self.runtime_logger)
        print("BROWSER_AGENT_PLAN =", {"action": describe_browser_agent_action(action)})
        if not self.confirm_browser_agent_action(action):
            self.show_subtitle("已取消浏览器动作。", voice_text="", duration=2.8)
            self.show_chat_status("浏览器动作已取消", seconds=2.2)
            browser_agent_log("CANCEL", {"action": describe_browser_agent_action(action)}, log_path=self.browser_agent_log_path, logger=self.runtime_logger)
            return True

        try:
            result = self.browser_agent.execute(action)
            message = f"浏览器动作完成：{result.get('title') or result.get('url')}\n截图：{result.get('screenshot')}"
            self.show_subtitle(message, voice_text="", duration=6.0)
            self.show_chat_status("浏览器动作完成", seconds=3.0)
            print("BROWSER_AGENT_DONE =", result)
        except Exception as exc:
            message = f"浏览器动作失败：{exc}"
            self.show_subtitle(message, voice_text="", duration=5.0)
            self.show_chat_status("浏览器动作失败", seconds=3.0)
            browser_agent_log("ERROR", {"action": describe_browser_agent_action(action), "error": str(exc)}, log_path=self.browser_agent_log_path, logger=self.runtime_logger)
            print("BROWSER_AGENT_ERROR =", {"action": describe_browser_agent_action(action), "error": str(exc)})
        return True


