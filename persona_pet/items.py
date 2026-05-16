"""Item registry and backpack system for PersonaPet."""

import time

BACKPACK_META_KEY = "backpack_state"

CATEGORY_FOOD = "food"
CATEGORY_DRINK = "drink"
CATEGORY_GIFT = "gift"

CATEGORY_LABELS = {
    CATEGORY_FOOD: "食物",
    CATEGORY_DRINK: "饮品",
    CATEGORY_GIFT: "礼物",
}

ITEMS = {
    "bread": {
        "id": "bread",
        "name": "面包",
        "category": CATEGORY_FOOD,
        "price": 8.0,
        "description": "普通的面包，能填饱肚子。",
        "effects": {"hunger": -18.0, "comfort": 2.0},
    },
    "rice_bowl": {
        "id": "rice_bowl",
        "name": "饭团",
        "category": CATEGORY_FOOD,
        "price": 12.0,
        "description": "好吃的饭团，比面包更管饱。",
        "effects": {"hunger": -28.0, "comfort": 4.0, "closeness_need": -2.0},
    },
    "steak": {
        "id": "steak",
        "name": "牛排",
        "category": CATEGORY_FOOD,
        "price": 35.0,
        "description": "高级牛排，吃了心情会变好。",
        "effects": {"hunger": -40.0, "comfort": 10.0, "closeness_need": -5.0},
    },
    "water": {
        "id": "water",
        "name": "矿泉水",
        "category": CATEGORY_DRINK,
        "price": 3.0,
        "description": "普通的水，解渴用。",
        "effects": {"thirst": -20.0},
    },
    "juice": {
        "id": "juice",
        "name": "果汁",
        "category": CATEGORY_DRINK,
        "price": 8.0,
        "description": "甜甜的果汁，心情也会变好。",
        "effects": {"thirst": -28.0, "comfort": 3.0},
    },
    "coffee": {
        "id": "coffee",
        "name": "咖啡",
        "category": CATEGORY_DRINK,
        "price": 15.0,
        "description": "提神的咖啡，能降低疲劳。",
        "effects": {"thirst": -15.0, "fatigue": -12.0, "sleepiness": -8.0, "stress": 2.0},
    },
    "flower": {
        "id": "flower",
        "name": "花束",
        "category": CATEGORY_GIFT,
        "price": 25.0,
        "description": "送给她的花束，她会很开心。",
        "effects": {"comfort": 8.0, "closeness_need": -10.0},
        "relation_bonus": 2.0,
    },
    "book": {
        "id": "book",
        "name": "新书",
        "category": CATEGORY_GIFT,
        "price": 30.0,
        "description": "一本她可能会喜欢的书。",
        "effects": {"comfort": 6.0, "closeness_need": -8.0, "stress": -5.0},
        "relation_bonus": 2.5,
    },
}

MAX_STACK = 10


def get_items_by_category(category):
    return [item for item in ITEMS.values() if item["category"] == category]


def get_all_categories():
    return [CATEGORY_FOOD, CATEGORY_DRINK, CATEGORY_GIFT]


class Backpack:
    def __init__(self, memory_store, item_registry=None, meta_key=BACKPACK_META_KEY, logger=None):
        self.memory_store = memory_store
        self.item_registry = item_registry or ITEMS
        self.meta_key = meta_key
        self.log_runtime = logger or (lambda *parts: None)
        saved = self.memory_store.load_meta_json(self.meta_key, {})
        if not isinstance(saved, dict):
            saved = {}
        raw_items = saved.get("items", {})
        self.items = {k: int(v) for k, v in raw_items.items() if k in self.item_registry and int(v) > 0}
        self.capacity = int(saved.get("capacity", 20))
        self.total_uses = int(saved.get("total_uses", 0))
        self.last_saved_at = 0.0
        self._dirty = False

    def add_item(self, item_id, quantity=1):
        if item_id not in self.item_registry:
            return False
        quantity = int(quantity)
        if quantity <= 0:
            return False
        current = self.items.get(item_id, 0)
        if current == 0 and len(self.items) >= self.capacity:
            return False
        self.items[item_id] = min(current + quantity, MAX_STACK)
        self.save()
        return True

    def remove_item(self, item_id, quantity=1):
        current = self.items.get(item_id, 0)
        if current < quantity:
            return False
        self.items[item_id] = current - quantity
        if self.items[item_id] <= 0:
            self.items.pop(item_id, None)
        self.save()
        return True

    def has_item(self, item_id, quantity=1):
        return self.items.get(item_id, 0) >= quantity

    def get_quantity(self, item_id):
        return self.items.get(item_id, 0)

    def get_all_items(self):
        result = []
        for item_id, qty in self.items.items():
            item_def = self.item_registry.get(item_id)
            if item_def and qty > 0:
                result.append((item_def, qty))
        return result

    def use_item(self, item_id, physiology=None, life_system=None):
        if not self.has_item(item_id):
            return False, "没有这个物品"
        item = self.item_registry.get(item_id)
        if not item:
            return False, "物品不存在"
        self.remove_item(item_id)
        self.total_uses += 1
        effects = item.get("effects", {})
        if physiology:
            print("BACKPACK_USE_ITEM before adjust =", {"item": item_id, "effects": effects, "values": dict(physiology.values)})
            physiology.adjust(**effects)
            print("BACKPACK_USE_ITEM after adjust =", {"item": item_id, "values": dict(physiology.values)})
        else:
            print("BACKPACK_USE_ITEM WARNING: physiology is None!")
        relation_bonus = item.get("relation_bonus", 0)
        if life_system and relation_bonus > 0:
            life_system.relationship_score += relation_bonus
        desc = f"使用了{item['name']}，感觉好多了。"
        self.save()
        return True, desc

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
                "items": self.items,
                "capacity": self.capacity,
                "total_uses": self.total_uses,
            },
        )


class BackpackMixin:
    def setup_backpack_module(self):
        self.backpack = Backpack(self.memory, ITEMS, logger=self.runtime_logger)

    def backpack_add_item(self, item_id, quantity=1):
        if hasattr(self, 'backpack'):
            return self.backpack.add_item(item_id, quantity)
        return False

    def backpack_use_item(self, item_id):
        if not hasattr(self, 'backpack'):
            return False, ""
        physiology = getattr(self, 'physiology', None)
        life = getattr(self, 'life', None)
        success, desc = self.backpack.use_item(item_id, physiology, life)
        if success:
            self.speak_interaction_feedback(desc, emotion="joy")
            self.interaction_memory_add(
                f"用户给小日和使用了{ITEMS[item_id]['name']}",
                desc, emotion="joy", max_daily_count=6, count=1,
            )
        return success, desc

    def save_backpack_module(self):
        if hasattr(self, 'backpack'):
            self.backpack.save()

    def flush_backpack_module(self):
        if hasattr(self, 'backpack'):
            self.backpack.flush_dirty()
