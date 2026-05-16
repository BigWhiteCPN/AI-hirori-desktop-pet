"""Economy system for PersonaPet -- wallets, transactions, income sources."""

import time
import datetime

ECONOMY_META_KEY = "economy_state"


class PersonaEconomy:
    NOVEL_CHAPTER_REWARD = 50.0
    NOVEL_WORD_BONUS_RATE = 0.05
    FARM_WORK_REWARD = 15.0
    FARM_WORK_COOLDOWN = 300.0
    DAILY_LOGIN_BONUS = 20.0
    INTERACTION_BONUS = 3.0

    def __init__(self, memory_store, meta_key=ECONOMY_META_KEY, logger=None):
        self.memory_store = memory_store
        self.meta_key = meta_key
        self.log_runtime = logger or (lambda *parts: None)
        saved = self.memory_store.load_meta_json(self.meta_key, {})
        if not isinstance(saved, dict):
            saved = {}
        self.user_wallet = float(saved.get("user_wallet", 100.0))
        self.character_wallet = float(saved.get("character_wallet", 0.0))
        self.total_earned = float(saved.get("total_earned", 0.0))
        self.total_spent = float(saved.get("total_spent", 0.0))
        self.daily_earnings = float(saved.get("daily_earnings", 0.0))
        self.daily_date = str(saved.get("daily_date") or "")
        self.transaction_log = saved.get("transaction_log") if isinstance(saved.get("transaction_log"), list) else []
        self.last_farm_work_at = float(saved.get("last_farm_work_at") or 0.0)
        self.last_daily_login_date = str(saved.get("last_daily_login_date") or "")
        self.last_saved_at = 0.0
        self._dirty = False

    def reset_daily_if_needed(self):
        today = datetime.date.today().isoformat()
        if self.daily_date != today:
            self.daily_date = today
            self.daily_earnings = 0.0
            self._dirty = True

    def _log_transaction(self, ttype, wallet, amount, detail=""):
        entry = {
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": ttype,
            "wallet": wallet,
            "amount": round(amount, 2),
            "detail": detail,
        }
        self.transaction_log.append(entry)
        if len(self.transaction_log) > 50:
            self.transaction_log = self.transaction_log[-50:]

    def earn(self, amount, wallet="character", detail=""):
        amount = float(amount)
        if amount <= 0:
            return
        self.reset_daily_if_needed()
        if wallet == "user":
            self.user_wallet += amount
        else:
            self.character_wallet += amount
        self.total_earned += amount
        self.daily_earnings += amount
        self._log_transaction("earn", wallet, amount, detail)
        self.save()

    def spend(self, amount, wallet="user", detail=""):
        amount = float(amount)
        if amount <= 0:
            return False
        if wallet == "user":
            if self.user_wallet < amount:
                return False
            self.user_wallet -= amount
        else:
            if self.character_wallet < amount:
                return False
            self.character_wallet -= amount
        self.total_spent += amount
        self._log_transaction("spend", wallet, -amount, detail)
        self.save()
        return True

    def transfer(self, amount, from_wallet, to_wallet, detail=""):
        amount = float(amount)
        if amount <= 0 or from_wallet == to_wallet:
            return False
        if from_wallet == "user":
            if self.user_wallet < amount:
                return False
            self.user_wallet -= amount
            self.character_wallet += amount
        else:
            if self.character_wallet < amount:
                return False
            self.character_wallet -= amount
            self.user_wallet += amount
        self._log_transaction("transfer", from_wallet, -amount, detail)
        self.save()
        return True

    def balance(self, wallet="user"):
        if wallet == "user":
            return self.user_wallet
        return self.character_wallet

    def on_novel_chapter_complete(self, word_count=0):
        reward = self.NOVEL_CHAPTER_REWARD + max(0, word_count) * self.NOVEL_WORD_BONUS_RATE
        reward = round(reward, 2)
        self.earn(reward, wallet="character", detail=f"完成小说章节，{word_count}字")
        return reward

    def on_farm_work(self):
        now = time.monotonic()
        if now - self.last_farm_work_at < self.FARM_WORK_COOLDOWN:
            remaining = self.FARM_WORK_COOLDOWN - (now - self.last_farm_work_at)
            return False, f"还需要休息 {remaining / 60:.1f} 分钟"
        self.last_farm_work_at = now
        self.earn(self.FARM_WORK_REWARD, wallet="user", detail="农场打工")
        return True, f"农场打工赚了 {self.FARM_WORK_REWARD:.0f} 金币"

    def on_daily_login(self):
        today = datetime.date.today().isoformat()
        if self.last_daily_login_date == today:
            return False, "今天已经领取过了"
        self.last_daily_login_date = today
        self.earn(self.DAILY_LOGIN_BONUS, wallet="user", detail="每日登录奖励")
        return True, f"每日登录奖励 +{self.DAILY_LOGIN_BONUS:.0f} 金币"

    def on_interaction_bonus(self):
        self.earn(self.INTERACTION_BONUS, wallet="user", detail="互动奖励")
        return self.INTERACTION_BONUS

    def save(self):
        self._dirty = True
        now = time.monotonic()
        if now - self.last_saved_at < 15.0:
            return
        self.flush_dirty()

    def flush_dirty(self):
        if not getattr(self, '_dirty', False):
            return
        self._dirty = False
        self.last_saved_at = time.monotonic()
        self.memory_store.save_meta_json(
            self.meta_key,
            {
                "user_wallet": self.user_wallet,
                "character_wallet": self.character_wallet,
                "total_earned": self.total_earned,
                "total_spent": self.total_spent,
                "daily_earnings": self.daily_earnings,
                "daily_date": self.daily_date,
                "transaction_log": self.transaction_log,
                "last_farm_work_at": self.last_farm_work_at,
                "last_daily_login_date": self.last_daily_login_date,
            },
        )


class EconomyMixin:
    def setup_economy_module(self):
        self.economy = PersonaEconomy(self.memory, logger=self.runtime_logger)

    def economy_earn(self, amount, wallet="character", detail=""):
        if hasattr(self, 'economy'):
            self.economy.earn(amount, wallet=wallet, detail=detail)

    def economy_spend(self, amount, wallet="user", detail=""):
        if hasattr(self, 'economy'):
            return self.economy.spend(amount, wallet=wallet, detail=detail)
        return False

    def economy_on_novel_complete(self, word_count=0):
        if hasattr(self, 'economy'):
            reward = self.economy.on_novel_chapter_complete(word_count)
            if reward > 0:
                self.show_chat_status(f"写作收入 +{reward:.0f} 金币", seconds=3.0)

    def economy_on_interaction(self):
        if hasattr(self, 'economy'):
            self.economy.on_interaction_bonus()

    def save_economy_module(self):
        if hasattr(self, 'economy'):
            self.economy.save()

    def flush_economy_module(self):
        if hasattr(self, 'economy'):
            self.economy.flush_dirty()
