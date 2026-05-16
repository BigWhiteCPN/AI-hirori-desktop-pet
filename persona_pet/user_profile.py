"""User profiling for adaptive conversation style.

This is a lightweight preference model, not a psychological diagnosis.
"""

import copy
import re
import time

from persona_pet.memory import compact_text, contains_any, memory_now_label


USER_PROFILE_META_KEY = "user_profile"


MBTI_AXES = ("EI", "SN", "TF", "JP")


def clamp(value, low=-100.0, high=100.0):
    return max(low, min(high, float(value)))


class PersonaUserProfile:
    def __init__(self, memory_store, meta_key=USER_PROFILE_META_KEY, logger=None):
        self.memory_store = memory_store
        self.meta_key = meta_key
        self.log_runtime = logger or (lambda *parts: None)
        saved = self.memory_store.load_meta_json(self.meta_key, {})
        if not isinstance(saved, dict):
            saved = {}
        self.axis_scores = {
            axis: clamp(saved.get("axis_scores", {}).get(axis, 0.0))
            for axis in MBTI_AXES
        }
        self.traits = dict(saved.get("traits", {})) if isinstance(saved.get("traits"), dict) else {}
        self.traits = {
            "detail_preference": float(self.traits.get("detail_preference", 0.0)),
            "emotional_openness": float(self.traits.get("emotional_openness", 0.0)),
            "playfulness": float(self.traits.get("playfulness", 0.0)),
            "directiveness": float(self.traits.get("directiveness", 0.0)),
            "proactive_tolerance": float(self.traits.get("proactive_tolerance", 0.0)),
            "intimacy_comfort": float(self.traits.get("intimacy_comfort", 0.0)),
        }
        self.message_count = int(saved.get("message_count") or 0)
        self.last_updated = str(saved.get("last_updated") or "")
        self.recent_evidence = saved.get("recent_evidence") if isinstance(saved.get("recent_evidence"), list) else []
        self.last_saved_at = 0.0

    def observe_user_message(self, text, emotion="neutral"):
        text = str(text or "").strip()
        if not text:
            return
        compact = compact_text(text)
        length = len(compact)
        deltas = {axis: 0.0 for axis in MBTI_AXES}
        trait_delta = {key: 0.0 for key in self.traits}
        evidence = []

        if contains_any(compact, ("一个人", "安静", "不想社交", "社恐", "独处", "自己待")):
            deltas["EI"] -= 2.4
            evidence.append("偏好安静/独处")
        if contains_any(compact, ("朋友", "大家", "聊天", "一起", "聚会", "分享给别人")):
            deltas["EI"] += 1.5
            evidence.append("提到社交/分享")

        if contains_any(compact, ("可能性", "意义", "本质", "如果", "假设", "想象", "灵魂", "未来")):
            deltas["SN"] += 2.0
            evidence.append("偏抽象和可能性")
        if contains_any(compact, ("具体", "步骤", "怎么做", "代码", "文件", "数值", "直接改", "报错")):
            deltas["SN"] -= 1.8
            evidence.append("偏具体和可执行")

        if contains_any(compact, ("逻辑", "原因", "为什么", "效率", "规则", "风险", "准确", "证明")):
            deltas["TF"] += 1.7
            trait_delta["directiveness"] += 1.0
            evidence.append("重视原因/逻辑")
        if contains_any(compact, ("感觉", "心情", "难受", "喜欢", "讨厌", "陪", "安慰", "温柔")) or emotion in ("sadness", "fear", "joy"):
            deltas["TF"] -= 2.0
            trait_delta["emotional_openness"] += 1.4
            evidence.append("重视情绪回应")

        if contains_any(compact, ("计划", "安排", "固定", "必须", "应该", "完成", "流程", "规则")):
            deltas["JP"] += 1.7
            trait_delta["directiveness"] += 0.8
            evidence.append("偏计划和结构")
        if contains_any(compact, ("随便", "试试", "感觉来", "灵活", "不要定式", "自然", "随机", "有趣")):
            deltas["JP"] -= 2.0
            trait_delta["playfulness"] += 1.0
            evidence.append("偏自然灵活")

        if length >= 120:
            trait_delta["detail_preference"] += 1.1
        elif length <= 18:
            trait_delta["detail_preference"] -= 0.6

        if contains_any(compact, ("主动", "自己思考", "自己说", "自由对话", "想法")):
            trait_delta["proactive_tolerance"] += 1.2
        if contains_any(compact, ("别烦", "安静", "不要打扰", "先别")):
            trait_delta["proactive_tolerance"] -= 1.8
        if contains_any(compact, ("亲密", "亲亲", "抱抱", "摸头", "贴近", "恋人")):
            trait_delta["intimacy_comfort"] += 1.2
        if contains_any(compact, ("边界", "别这样", "不舒服", "太快")):
            trait_delta["intimacy_comfort"] -= 1.5
        if re.search(r"[!?！？~～]{2,}|哈哈|嘿嘿|ww|233", text):
            trait_delta["playfulness"] += 0.8

        self.message_count += 1
        decay = 0.985
        for axis, delta in deltas.items():
            self.axis_scores[axis] = clamp(self.axis_scores[axis] * decay + delta)
        for key, delta in trait_delta.items():
            self.traits[key] = clamp(self.traits[key] * 0.99 + delta)
        if evidence:
            self.recent_evidence.append(
                {
                    "time": memory_now_label(),
                    "text": text[:80],
                    "emotion": emotion,
                    "evidence": evidence[:4],
                }
            )
            self.recent_evidence = self.recent_evidence[-12:]
        self.last_updated = memory_now_label()
        self.save()

    def axis_letter(self, axis):
        score = self.axis_scores.get(axis, 0.0)
        if axis == "EI":
            return "E" if score >= 0 else "I"
        if axis == "SN":
            return "N" if score >= 0 else "S"
        if axis == "TF":
            return "T" if score >= 0 else "F"
        if axis == "JP":
            return "J" if score >= 0 else "P"
        return "?"

    def mbti(self):
        return "".join(self.axis_letter(axis) for axis in MBTI_AXES)

    def confidence(self):
        if self.message_count <= 0:
            return 0.0
        axis_strength = sum(min(1.0, abs(self.axis_scores.get(axis, 0.0)) / 12.0) for axis in MBTI_AXES) / 4.0
        sample_strength = min(1.0, self.message_count / 24.0)
        return round((axis_strength * 0.65 + sample_strength * 0.35) * 100.0, 1)

    def preference_label(self, key, low, mid, high):
        value = self.traits.get(key, 0.0)
        if value >= 6:
            return high
        if value <= -6:
            return low
        return mid

    def adaptation_rules(self):
        mbti = self.mbti()
        rules = []
        if mbti[0] == "I":
            rules.append("少连环追问，给用户留安静思考空间")
        else:
            rules.append("可以更主动接话和延展话题")
        if mbti[1] == "N":
            rules.append("允许一点抽象联想，但要落回具体行动")
        else:
            rules.append("多给具体步骤、例子和明确选项")
        if mbti[2] == "F":
            rules.append("先承接情绪，再给建议")
        else:
            rules.append("先说明原因和取舍，再补一点情绪照顾")
        if mbti[3] == "P":
            rules.append("语气更自然灵活")
        else:
            rules.append("回应可以更有结构和计划感")

        if self.traits.get("detail_preference", 0.0) >= 6:
            rules.append("用户能接受较完整解释")
        elif self.traits.get("detail_preference", 0.0) <= -6:
            rules.append("优先短句和直接结论")
        if self.traits.get("playfulness", 0.0) >= 5:
            rules.append("可以保留一点玩笑和撒娇")
        if self.traits.get("proactive_tolerance", 0.0) <= -5:
            rules.append("降低主动打扰频率")
        elif self.traits.get("proactive_tolerance", 0.0) >= 5:
            rules.append("可以偶尔主动分享想法")
        return rules[:7]

    def snapshot(self):
        return {
            "mbti": self.mbti(),
            "confidence": self.confidence(),
            "axis_scores": copy.deepcopy(self.axis_scores),
            "traits": {key: round(value, 1) for key, value in self.traits.items()},
            "message_count": self.message_count,
            "last_updated": self.last_updated,
            "recent_evidence": copy.deepcopy(self.recent_evidence[-6:]),
            "adaptation_rules": self.adaptation_rules(),
            "style": {
                "detail": self.preference_label("detail_preference", "短句直接", "适中", "可以详细"),
                "emotion": self.preference_label("emotional_openness", "少煽情", "自然共情", "先照顾情绪"),
                "playfulness": self.preference_label("playfulness", "更认真", "自然", "更活泼"),
                "proactive": self.preference_label("proactive_tolerance", "少主动", "适中", "可主动"),
            },
        }

    def build_prompt_context(self):
        snap = self.snapshot()
        return (
            "用户心理侧写（启发式估计，像观察和理解一样使用）：\n"
            f"- 估计 MBTI：{snap['mbti']}，置信度 {snap['confidence']:.1f}%，样本 {snap['message_count']} 条。\n"
            f"- 沟通偏好：细节={snap['style']['detail']}，情绪={snap['style']['emotion']}，玩笑={snap['style']['playfulness']}，主动={snap['style']['proactive']}。\n"
            "- 行为调整：" + "；".join(snap["adaptation_rules"])
        )

    def save(self):
        self.last_saved_at = time.monotonic()
        self.memory_store.save_meta_json(
            self.meta_key,
            {
                "axis_scores": self.axis_scores,
                "traits": self.traits,
                "message_count": self.message_count,
                "last_updated": self.last_updated,
                "recent_evidence": self.recent_evidence[-12:],
            },
        )


class UserProfileMixin:
    def setup_user_profile_module(self):
        self.user_profile = PersonaUserProfile(self.memory, logger=getattr(self, "runtime_logger", None))
        if hasattr(self, "life"):
            self.life.user_profile = self.user_profile

    def user_profile_on_message(self, text, emotion="neutral"):
        if hasattr(self, "user_profile"):
            self.user_profile.observe_user_message(text, emotion=emotion)

    def save_user_profile_module(self):
        if hasattr(self, "user_profile"):
            self.user_profile.save()
