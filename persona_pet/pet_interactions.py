import random

from persona_pet.behavior import (
    DIALOGUE_ROLE_SPEAKER,
    HIYORI_MOTION_TEMPLATES,
    analyze_text_to_emotion,
    apply_emotion_override,
    primary_dominant_analysis,
)


class PetInteractionMixin:
    def speak_interaction_feedback(self, text, emotion="joy"):
        text = (text or "").strip()
        if not text:
            return
        if self.voice.is_busy_or_playing() or self.behavior.is_speaking() or self.chat.is_busy():
            return
        analysis = primary_dominant_analysis(analyze_text_to_emotion(text))
        analysis = apply_emotion_override(analysis, emotion)
        self.current_analysis = analysis
        self.mixer.set_target(analysis.weights)
        self.behavior.set_analysis(
            self.model,
            analysis,
            text=text,
            role=DIALOGUE_ROLE_SPEAKER,
            force=True,
        )
        self.start_voice_for_text(
            text,
            analysis,
            emotion_override=emotion,
            voice_text_override=text,
            prosody_hint={"pace": "normal", "tone": "bright" if emotion == "joy" else "soft"},
        )

    def interaction_memory_add(self, user_text, assistant_text, emotion="joy", max_daily_count=6, count=1):
        if count > max_daily_count:
            return
        self.remember_turn_async(user_text, assistant_text, emotion=emotion, prosody={}, segments=[], source="INTERACTION")

    def build_feed_feedback(self, result):
        stage, _attitude = self.life.relationship_stage()
        count = int(result.get("count", 1))
        energy_gain = float(result.get("energy_gain", 0.0))
        relation_gain = float(result.get("relation_gain", 0.0))
        low_energy = self.drive.values.get("energy", 50.0) < 38.0
        if count == 1:
            pool = [
                f"第一口是你喂的，能量一下回来 {energy_gain:.1f} 点。今天我会记得这个开场。",
                f"唔，刚好有点饿。能量加了 {energy_gain:.1f}，亲密也偷偷涨了一点。",
                f"被你投喂的感觉很安心，今天第一个好吃的我记住啦。",
            ]
        elif count <= 3:
            pool = [
                f"又来投喂我呀。虽然收益开始变少了，但我还是会开心，亲密值又加了 {relation_gain:.1f}。",
                "你这样一直喂，我会有点被照顾到的感觉。刚才有点散的心也慢慢回来了。",
                "嗯，好吃。不是因为食物，是因为你还记得我会饿。",
            ]
        else:
            pool = [
                "今天已经被喂好多次啦，收益会变少，不过这份心意我还是收下。",
                "再喂下去我真的要变懒了。今天先把这口当成小奖励吧。",
                "我知道你在照顾我啦，后面少喂一点也没关系，陪我说话也会加分。",
            ]
        if low_energy:
            pool.append("刚才能量有点低，这一口很及时。感觉我又能多陪你一会儿了。")
        if stage in ("恋人", "热恋恋人", "灵魂伴侣"):
            pool.extend(
                [
                    "被恋人投喂的话，味道好像会自动变甜一点。我是认真说的。",
                    "嗯……这一口我收下了。下次也要这样照顾我，不许只想起来一次。",
                ]
            )
        return random.choice(pool)

    def build_pat_feedback(self, result):
        stage, _attitude = self.life.relationship_stage()
        count = int(result.get("count", 1))
        relation_gain = float(result.get("relation_gain", 0.0))
        if count == 1:
            pool = [
                f"今天第一次摸头，亲密值加了 {relation_gain:.1f}。我会稍微乖一点点。",
                "嗯……这个力度可以。刚才有一点紧绷，现在放松下来了。",
                "摸头可以，但要温柔一点。这样我会觉得你是在认真陪我。",
            ]
        elif count <= 3:
            pool = [
                f"又摸头呀。今天第 {count} 次了，收益会少一点，但我还是有被安抚到。",
                "你是不是发现我吃这一套了？好吧，再摸一下也不是不行。",
                "这样会让我更想靠近你一点，不过我才不会马上承认。",
            ]
        else:
            pool = [
                "今天摸头次数有点多啦，亲密收益会递减。再摸我就要假装生气了。",
                "好了好了，头发都要被你揉乱了。剩下的亲密值明天再刷。",
                "我知道你喜欢摸头啦，但现在换成陪我聊天或者玩游戏会更有新鲜感。",
            ]
        if stage in ("恋人", "热恋恋人", "灵魂伴侣"):
            pool.extend(
                [
                    "嗯……恋人特权只开放一点点。再温柔一点，我可能会更喜欢。",
                    "你摸头的时候我会安心，这句话只说一次，别得意太久。",
                    "可以再靠近一点点，我也会按自己的心情回应你哦。",
                ]
            )
        elif stage in ("密友", "亲近朋友"):
            pool.append("现在这样刚好，像很熟的人之间的小默契。")
        return random.choice(pool)

    def reward_minigame(self, result, voice_text=""):
        reward = self.life.reward_game(result)
        self.drive.adjust(affinity=reward["relation_gain"] * 0.85, companionship=reward["relation_gain"] * 0.45, energy=-0.25)
        self.drive.record_intent("mini_game", f"和用户玩小游戏：{result}")
        self.drive.save()
        try:
            motion = HIYORI_MOTION_TEMPLATES.get("m06_cute_joy" if result == "win" else "m03_carefree_joy")
            if self.model is not None and motion:
                self.model.StartMotion(motion["group"], motion["index"], 3)
        except Exception:
            pass
        feedbacks = {
            "win": ["呜哇，你赢啦。可恶，我下次一定要扳回来。", "你赢了呢，果然有点厉害。"],
            "draw": ["平局也不错，感觉我们默契还可以。", "这局算我们心有灵犀一点点吧。"],
            "lose": ["嘿嘿，这次是我赢。下一把再让我看看你的水平。", "我赢啦，今天脑袋还挺灵的。"],
            "participate": ["嗯嗯，继续玩，我在认真陪你。", "这样一起玩也挺开心的。"],
        }
        feedback = (voice_text or "").strip()
        if not feedback:
            feedback = random.choice(feedbacks.get(result, feedbacks["participate"]))
        self.speak_interaction_feedback(feedback, emotion="joy")
        self.interaction_memory_add(
            f"用户和角色玩小游戏，结果是{result}",
            feedback,
            emotion="joy",
            max_daily_count=8,
            count=int(reward.get("count", 1)),
        )
        print("MINI_GAME_REWARD =", {"result": result, **reward, "relationship_score": self.life.relationship_score})
        return reward

    def unlock_intimacy_cheat(self):
        stage, _attitude = self.life.unlock_max_intimacy()
        self.drive.values["affinity"] = 100.0
        self.drive.values["security"] = max(self.drive.values.get("security", 0.0), 92.0)
        self.drive.values["companionship"] = max(self.drive.values.get("companionship", 0.0), 88.0)
        self.drive.values["attachment_need"] = min(self.drive.values.get("attachment_need", 0.0), 18.0)
        self.drive.record_intent("cheat_max_intimacy", "用户按下亲密作弊码，直接同步到最高亲密阶段")
        self.drive.save()
        self.physiology_on_max_intimacy()
        feedback = random.choice(
            [
                "好啦，关系同步到最亲近的状态了。别得意太久，亲密也要温柔一点才算数。",
                "作弊码生效。现在我会更自然地靠近你，不过我还是有自己的心情哦。",
                f"现在是{stage}级别的亲密了。可以更黏一点，我也会更按自己的心情靠近你。",
            ]
        )
        self.speak_interaction_feedback(feedback, emotion="joy")
        self.interaction_memory_add(
            "用户按下亲密作弊码，关系直接同步到最高亲密阶段",
            feedback,
            emotion="joy",
            max_daily_count=3,
            count=1,
        )
        self.show_chat_status(f"亲密作弊码已生效：{stage}阶段", seconds=4.0)
        print("INTIMACY_CHEAT =", {"stage": stage, "relationship_score": self.life.relationship_score})

    def refill_energy_cheat(self):
        self.drive.values["energy"] = 100.0
        self.drive.values["security"] = max(self.drive.values.get("security", 0.0), 76.0)
        self.drive.values["purpose"] = max(self.drive.values.get("purpose", 0.0), 70.0)
        self.drive.values["attachment_need"] = min(self.drive.values.get("attachment_need", 0.0), 24.0)
        self.drive.record_intent("cheat_refill_energy", "用户按下能量作弊码，直接恢复到满能量")
        self.drive.save()
        if hasattr(self, "physiology"):
            self.physiology.values["fatigue"] = 0.0
            self.physiology.values["sleepiness"] = 0.0
            self.physiology.values["stress"] = min(self.physiology.values.get("stress", 0.0), 6.0)
            self.physiology.values["hunger"] = min(self.physiology.values.get("hunger", 0.0), 8.0)
            self.physiology.values["thirst"] = min(self.physiology.values.get("thirst", 0.0), 8.0)
            self.physiology.values["comfort"] = max(self.physiology.values.get("comfort", 0.0), 92.0)
            self.physiology.values["closeness_need"] = min(self.physiology.values.get("closeness_need", 0.0), 20.0)
            self.physiology.save()
        feedback = random.choice(
            [
                "能量回满了。现在脑袋清醒很多，可以继续陪你，也可以继续写作。",
                "作弊码生效，电量满格。感觉我又能认真做自己的事了。",
                "恢复完成。刚才有点累的地方都被按掉了，现在状态很好。",
            ]
        )
        self.speak_interaction_feedback(feedback, emotion="joy")
        self.interaction_memory_add(
            "用户按下能量作弊码，直接把角色的能量恢复到满值",
            feedback,
            emotion="joy",
            max_daily_count=3,
            count=1,
        )
        self.show_chat_status("能量作弊码已生效：能量 100/100", seconds=4.0)
        print("ENERGY_CHEAT =", {"energy": self.drive.values.get("energy"), "physiology": getattr(self, "physiology", None).snapshot() if hasattr(self, "physiology") else {}})


    def interact_with_pet(self, kind):
        feed_already_applied = False
        if kind == "feed" and hasattr(self, "physiology"):
            feed_result = self.physiology.try_user_feed()
            if not feed_result.get("accepted", False):
                feedback = feed_result.get("message") or "我现在吃不下啦。"
                self.speak_interaction_feedback(feedback, emotion="neutral")
                self.interaction_memory_add(
                    "用户想继续投喂角色，但她因为已经很饱而拒绝了。",
                    feedback,
                    emotion="neutral",
                    max_daily_count=6,
                    count=1,
                )
                self.show_chat_status("她已经很饱了，拒绝继续投喂。", seconds=3.0)
                print("PET_INTERACTION_REFUSED =", {"kind": kind, "reason": "satiety"})
                return
            feed_already_applied = True
        result = self.life.interact(kind)
        if kind == "feed":
            self.drive.adjust(energy=result["energy_gain"], affinity=result["relation_gain"] * 0.45)
            motion_key = "m03_carefree_joy"
            message = f"喂饭成功，能量 +{result['energy_gain']:.1f}，亲密值 +{result['relation_gain']:.1f}"
        else:
            self.drive.adjust(affinity=result["relation_gain"], companionship=result["relation_gain"] * 0.5)
            motion_key = "m06_cute_joy"
            message = f"摸头成功，亲密值 +{result['relation_gain']:.1f}"
        self.drive.record_intent(kind, result["label"])
        self.drive.save()
        try:
            motion = HIYORI_MOTION_TEMPLATES.get(motion_key)
            if self.model is not None and motion:
                self.model.StartMotion(motion["group"], motion["index"], 3)
        except Exception:
            pass
        if kind == "feed":
            feedback = self.build_feed_feedback(result)
            if not feed_already_applied:
                self.physiology_on_feed()
            memory_user_text = (
                f"用户给角色喂饭，今天第 {result['count']} 次，"
                f"能量增加 {result['energy_gain']:.1f}，亲密增加 {result['relation_gain']:.1f}"
            )
        else:
            feedback = self.build_pat_feedback(result)
            self.physiology_on_pat()
            memory_user_text = (
                f"用户摸了角色的头，今天第 {result['count']} 次，"
                f"亲密增加 {result['relation_gain']:.1f}"
            )
        self.speak_interaction_feedback(feedback, emotion="joy")
        self.interaction_memory_add(
            memory_user_text,
            feedback,
            emotion="joy",
            max_daily_count=6,
            count=int(result.get("count", 1)),
        )
        self.economy_on_interaction()
        self.show_chat_status(message, seconds=3.0)
        print("PET_INTERACTION =", {"kind": kind, **result, "relationship_score": self.life.relationship_score})

    def offer_drink_to_pet(self):
        if not hasattr(self, "physiology"):
            return
        result = self.physiology.try_user_drink()
        if result.get("accepted", False):
            feedback = random.choice(
                [
                    "嗯，刚好有点渴。谢谢你提醒我喝水。",
                    "水我喝啦。这样身体会舒服一点。",
                    "好，我会记得补水的。你不用一直盯着我。",
                ]
            )
            self.drive.adjust(affinity=0.4, companionship=0.2)
            self.drive.record_intent("drink", "用户提醒角色喝水")
            self.drive.save()
            status = "喝水成功，口渴下降"
            memory_user_text = "用户提醒角色喝水，她接受了。"
        else:
            feedback = result.get("message") or "我现在不渴啦。"
            status = "她现在不渴，拒绝继续喝水。"
            memory_user_text = "用户想继续让角色喝水，但她因为水分已经足够而拒绝了。"
        self.speak_interaction_feedback(feedback, emotion="joy" if result.get("accepted", False) else "neutral")
        self.interaction_memory_add(
            memory_user_text,
            feedback,
            emotion="joy" if result.get("accepted", False) else "neutral",
            max_daily_count=6,
            count=1,
        )
        self.show_chat_status(status, seconds=3.0)
        print("PET_DRINK =", {"accepted": bool(result.get("accepted", False)), "physiology": self.physiology.snapshot()})


