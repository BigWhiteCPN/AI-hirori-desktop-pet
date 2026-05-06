import random
import time

from persona_pet.behavior import (
    DIALOGUE_ROLE_LISTENER,
    DIALOGUE_ROLE_SPEAKER,
    HIYORI_MOTION_TEMPLATES,
    MOTION_DURATION_SECONDS,
    PRIMARY_EMOTION_THRESHOLD,
    RESIDUE_MOTION_BY_EMOTION,
    analyze_text_to_emotion,
    apply_emotion_override,
    dominant_weight_emotion,
    primary_dominant_analysis,
    select_reaction_motion,
)
from persona_pet.voicevox import estimate_sentence_seconds, split_dialogue_sentences, voicevox_line_for

DIALOGUE_SENTENCE_GAP = {
    DIALOGUE_ROLE_LISTENER: 0.75,
    DIALOGUE_ROLE_SPEAKER: 0.45,
}
VOICE_PLAYBACK_GUARD_SECONDS = 0.25


class PetDialogueMixin:
    def apply_current_text(self, speak=False):
        self.dialogue_active = False
        raw_analysis = analyze_text_to_emotion(self.test_text)
        self.current_analysis = primary_dominant_analysis(raw_analysis)
        self.mixer.set_target(self.current_analysis.weights)
        if speak:
            if hasattr(self, "show_chat_status"):
                self.show_chat_status("测试：角色正在说当前文本。", seconds=2.0)
            self.behavior.set_analysis(
                self.model,
                self.current_analysis,
                text=self.test_text,
                role=DIALOGUE_ROLE_SPEAKER,
            )
            self.start_voice_for_text(self.test_text, self.current_analysis, test_key=self.current_test_key)
        else:
            if hasattr(self, "show_chat_status"):
                self.show_chat_status("测试：已把当前文本应用为监听情绪。", seconds=2.0)
            self.behavior.set_analysis(
                self.model,
                self.current_analysis,
                text=self.test_text,
                role=DIALOGUE_ROLE_LISTENER,
            )

        dominant_weight = dominant_weight_emotion(self.current_analysis)
        role = DIALOGUE_ROLE_SPEAKER if speak else DIALOGUE_ROLE_LISTENER
        _, motion_key, motion = select_reaction_motion(self.current_analysis, text=self.test_text, role=role)
        print(
            "APPLY =",
            {
                "dominant_raw": raw_analysis.dominant,
                "dominant_weight": dominant_weight,
                "dominant_used": self.current_analysis.dominant,
                "primary_threshold": PRIMARY_EMOTION_THRESHOLD,
                "intensity": round(self.current_analysis.intensity, 3),
                "weights": {k: round(v, 3) for k, v in self.current_analysis.weights.items()},
                "matched": self.current_analysis.matched_tokens,
                "reaction_motion": motion_key,
                "reaction_label": motion["label"] if motion else "",
            },
        )

    def start_dialogue_test(self, role):
        sentences = split_dialogue_sentences(self.test_text)
        if not sentences:
            return

        self.dialogue_active = True
        self.dialogue_role = role
        self.dialogue_sentences = sentences
        self.dialogue_index = 0
        self.next_dialogue_at = 0.0
        self.last_dialogue_emotion = dominant_weight_emotion(self.current_analysis)
        if hasattr(self, "show_chat_status"):
            label = "说话者" if role == DIALOGUE_ROLE_SPEAKER else "监听者"
            self.show_chat_status(f"逐句测试开始：{label}，共 {len(sentences)} 句。", seconds=2.4)
        print(
            "DIALOGUE_START =",
            {
                "role": role,
                "sentences": len(sentences),
                "text": self.test_text,
            },
        )

    def apply_dialogue_sentence(self, sentence, role):
        raw_analysis = analyze_text_to_emotion(sentence)
        analysis = primary_dominant_analysis(raw_analysis)
        self.current_analysis = analysis
        self.mixer.set_target(analysis.weights)

        dominant = dominant_weight_emotion(analysis)
        transition_motion_key = None
        if dominant == "neutral" and self.last_dialogue_emotion != "neutral":
            transition_motion_key = RESIDUE_MOTION_BY_EMOTION.get(self.last_dialogue_emotion)

        if role == DIALOGUE_ROLE_SPEAKER:
            self.behavior.set_analysis(
                self.model,
                analysis,
                text=sentence,
                role=DIALOGUE_ROLE_SPEAKER,
                force=True,
                motion_key_override=transition_motion_key,
            )
            self.start_voice_for_text(sentence, analysis)
        else:
            self.behavior.set_analysis(
                self.model,
                analysis,
                text=sentence,
                role=DIALOGUE_ROLE_LISTENER,
                force=True,
                motion_key_override=transition_motion_key,
            )

        if transition_motion_key:
            motion_key = transition_motion_key
            motion = HIYORI_MOTION_TEMPLATES[motion_key]
        else:
            _, motion_key, motion = select_reaction_motion(analysis, text=sentence, role=role)
        previous_emotion = self.last_dialogue_emotion
        self.last_dialogue_emotion = dominant
        print(
            "DIALOGUE_STEP =",
            {
                "role": role,
                "index": self.dialogue_index,
                "sentence": sentence,
                "previous_emotion": previous_emotion,
                "dominant_raw": raw_analysis.dominant,
                "dominant_weight": dominant,
                "motion": motion_key,
                "label": motion["label"] if motion else "",
                "weights": {k: round(v, 3) for k, v in analysis.weights.items()},
            },
        )
        return motion_key

    def update_dialogue_sequence(self):
        if not self.dialogue_active:
            return

        now = time.monotonic()
        if self.next_dialogue_at and now < self.next_dialogue_at:
            return
        if self.dialogue_role == DIALOGUE_ROLE_SPEAKER and self.voice.is_busy_or_playing(now):
            return

        if self.dialogue_index >= len(self.dialogue_sentences):
            self.dialogue_active = False
            if hasattr(self, "show_chat_status"):
                self.show_chat_status("逐句测试已结束。", seconds=2.0)
            print(
                "DIALOGUE_END =",
                {
                    "role": self.dialogue_role,
                    "last_emotion": self.last_dialogue_emotion,
                },
            )
            return

        sentence = self.dialogue_sentences[self.dialogue_index]
        if hasattr(self, "show_chat_status"):
            role_label = "说话" if self.dialogue_role == DIALOGUE_ROLE_SPEAKER else "倾听"
            self.show_chat_status(f"逐句测试：{role_label} {self.dialogue_index + 1}/{len(self.dialogue_sentences)}", seconds=1.6)
        motion_key = self.apply_dialogue_sentence(sentence, self.dialogue_role)
        seconds = estimate_sentence_seconds(sentence, role=self.dialogue_role)
        motion_seconds = min(MOTION_DURATION_SECONDS.get(motion_key, 0.0), 4.2)
        seconds = max(seconds, motion_seconds)
        gap = DIALOGUE_SENTENCE_GAP.get(self.dialogue_role, 0.6)
        self.dialogue_index += 1
        self.next_dialogue_at = now + seconds + gap


