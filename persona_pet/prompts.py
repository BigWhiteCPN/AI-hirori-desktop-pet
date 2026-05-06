"""Prompt contracts shared by LLM calls."""

PROSODY_PROMPT_CONTRACT = (
    "必须只输出 JSON，不要输出 Markdown。JSON 格式为："
    "{\"zh\":\"中文回复\","
    "\"emotion\":\"joy/sadness/anger/fear/surprise/neutral\","
    "\"segments\":[{\"zh\":\"分句中文\","
    "\"emotion\":\"joy/sadness/anger/fear/surprise/neutral\"}],"
    "\"prosody\":{\"pace\":\"slow/normal/fast\","
    "\"tone\":\"soft/bright/serious/teasing/urgent\","
    "\"emphasis\":[\"需要重读的短词\"],"
    "\"pause_after\":[\"需要稍微停顿的短词\"]}}。"
    "zh 要简短自然，通常一到三句话，直接作为中文配音台词。"
    "segments 按语义和情绪拆成一到四段，每段要短，不要为了拆分而拆分。"
    "emotion 必须从 joy、sadness、anger、fear、surprise、neutral 中选择一个。"
    "prosody 用来描述说话节奏和重音。"
    "严禁在 zh 或 segments 中写括号动作、舞台说明、表情说明、心理描写。"
    "不要输出类似（挥手）、（笑）、（名残惜しそうに）的内容。"
)

