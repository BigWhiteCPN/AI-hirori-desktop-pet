"""Subtext analyzer that infers user's true intent beyond literal words."""

import re


SUBTEXT_PATTERNS = {
    "downplay_sadness": {
        "triggers": ("没事", "没什么", "还好", "还行", "不要紧", "没关系", "算了"),
        "context_signals": ("之前", "刚才", "昨天", "最近", "有点"),
        "inferred_emotion": "sadness",
        "confidence": 0.55,
        "insight": "她说没事，但结合上下文可能心里有些不舒服，可以温柔地追问一下。",
    },
    "hidden_anger": {
        "triggers": ("随便", "都行", "你说了算", "随你", "无所谓", "爱咋咋"),
        "context_signals": ("为什么", "怎么又", "又来了", "每次都"),
        "inferred_emotion": "anger",
        "confidence": 0.50,
        "insight": "她说随便，但语气词暗示可能在闹脾气，可以关心一下是不是哪里让她不高兴了。",
    },
    "seeking_comfort": {
        "triggers": ("好累", "好烦", "好难", "不想", "不想动", "好困", "压力大"),
        "context_signals": ("工作", "学习", "加班", "考试", "项目", "deadline"),
        "inferred_emotion": "sadness",
        "confidence": 0.60,
        "insight": "她可能在寻求安慰而不是解决方案，先共情再问她需要什么。",
    },
    "testing_boundaries": {
        "triggers": ("你是不是", "你到底", "你心里", "你真的", "你确定"),
        "context_signals": ("喜欢", "爱", "在乎", "重要", "第一位"),
        "inferred_emotion": "fear",
        "confidence": 0.45,
        "insight": "她在试探你的心意，可能需要确认感而不是敷衍。",
    },
    "indirect_request": {
        "triggers": ("好想要", "好喜欢", "要是能", "要是有", "听说", "别人家"),
        "context_signals": ("礼物", "惊喜", "陪", "一起", "买"),
        "inferred_emotion": "neutral",
        "confidence": 0.40,
        "insight": "她可能在暗示想要什么，可以认真回应她的愿望。",
    },
    "withdrawal": {
        "triggers": ("你忙吧", "你去吧", "不用管我", "我自己", "你先"),
        "context_signals": ("嗯", "哦", "好", "行"),
        "inferred_emotion": "sadness",
        "confidence": 0.50,
        "insight": "她可能在退缩，怕打扰你。可以告诉她你愿意陪她。",
    },
    "playful_teasing": {
        "triggers": ("哼", "才不要", "讨厌", "不理你", "坏蛋", "笨蛋"),
        "context_signals": ("嘿嘿", "哈哈", "啦", "嘛", "呀"),
        "inferred_emotion": "joy",
        "confidence": 0.65,
        "insight": "她在撒娇，可以用轻松的方式回应。",
    },
}


def analyze_subtext(user_text, recent_history=None, relationship_score=0.0):
    compact = re.sub(r"\s+", "", user_text or "")
    if not compact:
        return None
    recent_text = ""
    if recent_history:
        for item in recent_history[-3:]:
            recent_text += f"{item.get('user', '')} {item.get('assistant', '')}"
    recent_compact = re.sub(r"\s+", "", recent_text)

    matches = []
    for name, pattern in SUBTEXT_PATTERNS.items():
        trigger_score = 0.0
        for trigger in pattern["triggers"]:
            if trigger in compact:
                trigger_score += 1.0
        if trigger_score == 0.0:
            continue
        context_score = 0.0
        for signal in pattern["context_signals"]:
            if signal in compact or signal in recent_compact:
                context_score += 0.5
        if context_score == 0.0 and name not in ("playful_teasing", "withdrawal"):
            continue
        confidence = pattern["confidence"]
        confidence += trigger_score * 0.08
        confidence += context_score * 0.06
        if relationship_score > 88:
            if name in ("testing_boundaries", "seeking_comfort"):
                confidence += 0.08
        if relationship_score > 130:
            if name == "playful_teasing":
                confidence += 0.10
        confidence = min(0.95, confidence)
        matches.append((name, confidence, pattern))

    if not matches:
        return None
    matches.sort(key=lambda x: -x[1])
    best_name, best_confidence, best_pattern = matches[0]
    if best_confidence < 0.35:
        return None

    return {
        "pattern": best_name,
        "confidence": round(best_confidence, 2),
        "inferred_emotion": best_pattern["inferred_emotion"],
        "insight": best_pattern["insight"],
        "literal_text": user_text,
    }


def build_subtext_prompt_context(subtext_result):
    if not subtext_result:
        return ""
    return (
        f"[言外之意分析] {subtext_result['insight']}\n"
        f"推断情绪：{subtext_result['inferred_emotion']}，置信度：{subtext_result['confidence']}\n"
        "请结合这个分析来回应，但不要直接说'我知道你在试探我'这种话，而是自然地回应她的真实需求。"
    )
