"""Formal persona eval entrypoint.

Runs deterministic local regression suites without network, browser, or real TTS calls.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from tests.evals.harness import assert_contains, assert_true, run_case, summarize, write_reports

from persona_pet.credential_store import externalize_config_secrets, hydrate_config_secrets, profile_from_config_path
from persona_pet.error_reporter import report_exception, report_exception_to_file
from persona_pet.file_agent import FileAgentAction, execute_file_agent_action
from persona_pet.idle_scheduler import IdleBehavior, IdleScheduler
from persona_pet.body_cycle import BodyCycleSystem
from persona_pet.life_system import PersonaDriveSystem, PersonaLifeSystem
from persona_pet.life_writing import LifeWritingController, LifeWritingEvent
from persona_pet.llm_client import LLMClient
from persona_pet.llm_config import build_default_llm_config, migrate_llm_config
from persona_pet.memory import PersonaMemoryStore
from persona_pet.physiology import PersonaPhysiology
from persona_pet.profile_runtime import profile_config_path, profile_output_dir, select_runtime_profile
from persona_pet.runtime import AgentRuntime
from persona_pet.tool_permissions import assess_tool_action, build_tool_dry_run, validate_tool_action
from persona_pet.voicevox import VoicevoxController, estimate_sentence_seconds


def temp_store(prefix="persona_eval_memory_"):
    root = tempfile.mkdtemp(prefix=prefix)
    return PersonaMemoryStore(os.path.join(root, "memory.json"), os.path.join(root, "memory.db"))


def eval_runtime_events():
    root = tempfile.mkdtemp(prefix="persona_eval_runtime_")
    runtime = AgentRuntime(log_dir=root)
    with runtime.span("eval.span", kind="eval", payload={"api_key": "secret"}):
        runtime.emit("eval.event", {"ok": True})
    log_path = os.path.join(root, "agent_runtime.jsonl")
    assert_true(os.path.exists(log_path), "runtime jsonl was not written")
    with open(log_path, "r", encoding="utf-8") as handle:
        content = handle.read()
    assert_true("***" in content and "secret" not in content, "runtime log did not redact secret payload")
    return {"events": len(runtime.events)}


def eval_runtime_suppressed_exception_reporting():
    root = tempfile.mkdtemp(prefix="persona_eval_errors_")
    runtime = AgentRuntime(log_dir=root)
    captured = []

    try:
        raise ValueError("suppressed detail")
    except Exception as exc:
        payload = report_exception(runtime, lambda *parts: captured.append(parts), "eval", "suppressed", exc, item_id="case-1")

    assert_true(payload["component"] == "eval", "suppressed exception payload lost component")
    assert_true(captured and captured[0][0] == "ERROR_SUPPRESSED", "suppressed exception was not sent to logger")
    assert_true(any(event.type == "error.suppressed" for event in runtime.events), "runtime did not emit error.suppressed")

    log_path = os.path.join(root, "suppressed.jsonl")
    try:
        raise RuntimeError("file report")
    except Exception as exc:
        file_payload = report_exception_to_file(log_path, "eval", "file_report", exc)
    assert_true(os.path.exists(log_path), "suppressed exception file report was not written")
    assert_true(file_payload["error_type"] == "RuntimeError", "file report lost error type")
    return {"events": len(runtime.events), "file": os.path.basename(log_path)}


def eval_runtime_tasks():
    runtime = AgentRuntime(log_dir=tempfile.mkdtemp(prefix="persona_eval_tasks_"))
    order = []

    def locked_worker():
        order.append("start")
        time.sleep(0.03)
        order.append("end")

    first = runtime.run_background("eval_locked", locked_worker, resources=("memory_write",))
    second = runtime.run_background("eval_locked", locked_worker, resources=("memory_write",))
    first.thread.join(timeout=2.0)
    second.thread.join(timeout=2.0)
    assert_true(first.status == "done" and second.status == "done", "runtime tasks did not finish")
    assert_true(order == ["start", "end", "start", "end"], "resource lock did not serialize tasks")

    captured = []
    entered = threading.Event()

    def cancellable(cancel_token):
        entered.set()
        deadline = time.monotonic() + 1.0
        while not cancel_token.is_cancelled() and time.monotonic() < deadline:
            time.sleep(0.01)
        captured.append(cancel_token.is_cancelled())

    task = runtime.run_background("eval_cancel", cancellable)
    entered.wait(timeout=1.0)
    runtime.cancel_task(task.id)
    task.thread.join(timeout=2.0)
    assert_true(task.is_cancelled(), "cancel token was not marked")
    assert_true(captured and captured[0], "cancel token was not passed into worker")

    keyword_captured = []

    def keyword_token_worker(*, token):
        keyword_captured.append(token is not None)

    keyword_task = runtime.run_background("eval_keyword_token", keyword_token_worker)
    keyword_task.thread.join(timeout=2.0)
    assert_true(keyword_captured == [True], "keyword-only token was not passed correctly")
    return {"tasks": len(runtime.task_snapshot())}


def eval_runtime_idle_scheduler_resources():
    runtime = AgentRuntime(log_dir=tempfile.mkdtemp(prefix="persona_eval_idle_runtime_"))
    calls = []
    released = threading.Event()

    def dispatcher(fn):
        fn()

    scheduler = IdleScheduler(runtime=runtime, dispatcher=dispatcher)
    scheduler.register(
        IdleBehavior(
            name="eval_idle",
            base_priority=10,
            cooldown=0.0,
            execute_fn=lambda: (calls.append("run"), time.sleep(0.02), released.set()),
            resources=("idle_behavior", "llm", "memory_write"),
        )
    )
    selected = scheduler.tick(now=100.0, busy=False, energy=100.0, idle_seconds=999.0)
    assert_true(selected == "eval_idle", "idle scheduler did not select eval behavior")
    released.wait(timeout=2.0)
    deadline = time.monotonic() + 2.0
    snapshot = runtime.task_snapshot()
    while time.monotonic() < deadline:
        snapshot = runtime.task_snapshot()
        if snapshot and all(task.get("status") in ("done", "error", "cancelled") for task in snapshot.values()):
            break
        time.sleep(0.01)
    assert_true(calls == ["run"], "idle behavior did not run through dispatcher")
    resources = set()
    for task in snapshot.values():
        resources.update(task.get("resources", []))
    assert_true({"idle_behavior", "llm", "memory_write"}.issubset(resources), "idle resources were not attached to runtime task")
    return {"tasks": len(snapshot), "resources": sorted(resources)}


def eval_profile_selection():
    selection = select_runtime_profile(
        default_profile="test",
        argv=["--profile", "main", "--reset-profile", "--qt-flag"],
        env={},
    )
    assert_true(selection["profile"] == "main", "cli profile main was not selected")
    assert_true(selection["reset"] is False, "main profile must not be reset")
    assert_true(selection["argv"] == ["--qt-flag"], "profile args were not stripped")

    env_selection = select_runtime_profile(default_profile="test", argv=[], env={"PERSONA_RUN_PROFILE": "dev/local", "PERSONA_RESET_PROFILE": "yes"})
    assert_true(env_selection["profile"] == "dev_local", "env profile was not sanitized")
    assert_true(env_selection["reset"] is True, "env reset flag was not honored")

    base = os.path.join("X:", "persona")
    assert_true(profile_output_dir(base, "main", "memory").endswith(os.path.join("outputs", "memory")), "main output path changed")
    assert_true("profiles" in profile_output_dir(base, "dev", "memory"), "non-main output path did not isolate profile")
    assert_true(profile_config_path(base, "dev").endswith("persona_llm_config.dev.json"), "profile config path was not isolated")
    return {"profile": env_selection["profile"], "source": env_selection["source"]}


def eval_state_homeostasis_long_run():
    store = temp_store(prefix="persona_eval_homeostasis_")
    drive = PersonaDriveSystem(store)
    physiology = PersonaPhysiology(store)
    cycle = BodyCycleSystem(store)
    physiology.drive = drive
    physiology.body_cycle = cycle
    drive._physiology_ref = physiology

    start = time.monotonic()
    for minute in range(0, 3 * 24 * 60, 10):
        now = start + minute * 60.0
        busy = 9 * 60 <= minute % (24 * 60) <= 18 * 60
        drive.tick(now=now, busy=busy)
        physiology.tick(now=now, busy=busy)
        cycle.tick(now=now)
        if minute % 180 == 0:
            drive.on_user_message("ä»Šå¤©çŠ¶æ€æ€Žä¹ˆæ ·ï¼Ÿ", emotion="neutral")
            physiology.on_user_message("ä»Šå¤©çŠ¶æ€æ€Žä¹ˆæ ·ï¼Ÿ")
        if minute % 240 == 0:
            drive.on_assistant_reply("æˆ‘çŠ¶æ€è¿˜ç®—å¹³ç¨³ã€‚", emotion="neutral")
            physiology.on_assistant_reply()

    for value in physiology.values.values():
        assert_true(0.0 < value < 100.0, f"physiology value hit hard extreme: {physiology.values}")
    for value in drive.values.values():
        assert_true(0.0 < value < 100.0, f"drive value hit hard extreme: {drive.values}")
    assert_true(0.0 < cycle.sexual_need < 92.0, f"sexual need hit hard extreme: {cycle.sexual_need}")

    physiology.last_wall_at = time.time() - 4 * 86400.0
    physiology._apply_offline_progress(time.time())
    assert_true(physiology.values["hunger"] < 90.0, f"offline hunger too high: {physiology.values['hunger']}")
    assert_true(physiology.values["thirst"] < 88.0, f"offline thirst too high: {physiology.values['thirst']}")
    assert_true(physiology.values["comfort"] > 20.0, f"offline comfort collapsed: {physiology.values['comfort']}")
    return {
        "drive_energy": round(drive.values["energy"], 1),
        "hunger": round(physiology.values["hunger"], 1),
        "sexual_need": round(cycle.sexual_need, 1),
    }


def eval_life_writing_fallback_outputs():
    root = tempfile.mkdtemp(prefix="persona_eval_writing_")
    store = PersonaMemoryStore(os.path.join(root, "memory.json"), os.path.join(root, "memory.db"))
    life = PersonaLifeSystem(
        store,
        diary_dir=os.path.join(root, "diary"),
        novel_dir=os.path.join(root, "novel"),
        novel_daily_word_limit=900,
    )
    writer = LifeWritingController(config=build_default_llm_config(), memory_store=store, life_system=life)

    def failing_chat_messages(*_args, **_kwargs):
        raise RuntimeError("offline llm")

    writer.client.chat_messages = failing_chat_messages
    diary = writer.write_diary()
    novel = writer.write_novel()

    assert_true(os.path.exists(diary.path), "fallback diary docx was not written")
    assert_true(os.path.exists(novel.path), "fallback novel docx was not written")
    assert_true("苏念" in os.path.basename(diary.path), "diary path did not use Su Nian")
    assert_true(life.last_diary_date == time.strftime("%Y-%m-%d"), "diary date was not marked written")
    assert_true(life.novel_chapters_today >= 1, "novel chapter count was not updated")
    assert_true(len(diary.content) > 80 and len(novel.content) > 80, "fallback writing content was too short")
    return {"diary_chars": len(diary.content), "novel_chars": len(novel.content)}


def eval_life_writing_async_queue():
    root = tempfile.mkdtemp(prefix="persona_eval_writing_queue_")
    store = PersonaMemoryStore(os.path.join(root, "memory.json"), os.path.join(root, "memory.db"))
    life = PersonaLifeSystem(store, diary_dir=os.path.join(root, "diary"), novel_dir=os.path.join(root, "novel"))
    writer = LifeWritingController(config=build_default_llm_config(), memory_store=store, life_system=life)

    def fake_diary():
        time.sleep(0.08)
        return LifeWritingEvent(kind="diary", path="diary.docx", title="diary", content="diary content")

    def fake_novel():
        return LifeWritingEvent(kind="novel", path="novel.docx", title="novel", content="novel content")

    writer.write_diary = fake_diary
    writer.write_novel = fake_novel

    assert_true(writer.write_async("diary"), "initial async diary did not start")
    time.sleep(0.02)
    assert_true(writer.write_async("novel"), "busy writer did not queue novel")

    deadline = time.perf_counter() + 3.0
    events = []
    while time.perf_counter() < deadline:
        events.extend(writer.consume_events())
        if len(events) >= 2 and not writer.is_busy():
            break
        time.sleep(0.02)

    kinds = [event.kind for event in events]
    assert_true(kinds == ["diary", "novel"], f"queued writing order was wrong: {kinds}")
    assert_true(not writer.is_busy(), "writer stayed busy after queued tasks")
    return {"events": kinds}


def eval_memory_recall_precision_recall():
    store = temp_store()
    cases = [
        {
            "user": "我把蓝色雨伞放在玄关鞋柜旁边。",
            "assistant": "我记住了，蓝色雨伞在玄关鞋柜旁边。",
            "query": "我那把蓝色雨伞放在哪里？",
            "needle": "蓝色雨伞",
        },
        {
            "user": "我周末要给林老师交星海画展的草稿。",
            "assistant": "我会记得星海画展草稿这件事。",
            "query": "星海画展草稿是给谁交？",
            "needle": "林老师",
        },
        {
            "user": "我讨厌太甜的奶茶，更喜欢无糖乌龙茶。",
            "assistant": "我记住你的饮品偏好是无糖乌龙茶。",
            "query": "我喜欢什么饮品？",
            "needle": "无糖乌龙茶",
        },
    ]
    for case in cases:
        store.add_turn(case["user"], case["assistant"], emotion="neutral")
    hits = 0
    top_hits = 0
    retrieved_total = 0
    for case in cases:
        results = store.retrieve(case["query"], limit=3)
        retrieved_total += len(results)
        rendered = "\n".join(f"{item.get('user', '')}\n{item.get('assistant', '')}" for item in results)
        if case["needle"] in rendered:
            hits += 1
        if results and case["needle"] in f"{results[0].get('user', '')}\n{results[0].get('assistant', '')}":
            top_hits += 1
    recall = hits / len(cases)
    precision = hits / max(retrieved_total, 1)
    top1 = top_hits / len(cases)
    assert_true(recall >= 0.99, f"memory recall too low: {recall}")
    assert_true(top1 >= 0.66, f"memory top1 too low: {top1}")
    return {"recall": recall, "precision_at_3": round(precision, 4), "top1": top1, "score": (recall + top1) / 2.0}


def eval_memory_preference_change_multiturn():
    store = temp_store()
    store.add_turn("我叫小明，我喜欢苹果。", "我记住了。")
    store.add_turn("我不喜欢苹果了。", "我会按新的偏好记住。")
    store.add_turn("以后聊水果时提醒我按新偏好来。", "明白，我会按新偏好来。")
    facts = store.data.get("semantic_memory", {}).get("facts", [])
    active_pairs = {
        (fact.get("predicate"), fact.get("object"))
        for fact in facts
        if fact.get("status") == "active"
    }
    superseded_pairs = {
        (fact.get("predicate"), fact.get("object"))
        for fact in facts
        if fact.get("status") == "superseded"
    }
    assert_true(("不喜欢", "苹果") in active_pairs, "new negative apple preference was not active")
    assert_true(("喜欢", "苹果") in superseded_pairs, "old positive apple preference was not superseded")
    context = store.build_semantic_memory_context("我现在还喜欢苹果吗？")
    assert_contains(context, "不喜欢", "semantic context did not surface newest negative preference")
    return {"active_facts": len(active_pairs), "superseded_facts": len(superseded_pairs)}


def eval_memory_temporal_events():
    store = temp_store()
    last_week = datetime.now().date() - timedelta(days=8)
    last_month = (datetime.now().date().replace(day=1) - timedelta(days=1)).replace(day=8)
    week_item = store.add_turn("上周我参加了星海画展，还买了一本画册。", "我记住了上周的星海画展。")
    month_item = store.add_turn("上个月我搬了一次工作台，放到了窗边。", "我记住上个月工作台搬到窗边。")
    week_item["created_at"] = f"{last_week.isoformat()} 12:00:00"
    week_item["time_label"] = week_item["created_at"]
    month_item["created_at"] = f"{last_month.isoformat()} 12:00:00"
    month_item["time_label"] = month_item["created_at"]
    store.save()

    week_results = store.retrieve("上周我去了什么展？", limit=5)
    month_results = store.retrieve("上个月工作台发生了什么？", limit=5)
    week_text = "\n".join(item.get("user", "") + item.get("assistant", "") for item in week_results)
    month_text = "\n".join(item.get("user", "") + item.get("assistant", "") for item in month_results)
    assert_contains(week_text, "星海画展", "last-week event was not recalled")
    assert_contains(month_text, "工作台", "last-month event was not recalled")
    return {"week_results": len(week_results), "month_results": len(month_results)}


def eval_memory_fts_archival_recall():
    root = tempfile.mkdtemp(prefix="persona_eval_fts_")
    store = PersonaMemoryStore(os.path.join(root, "memory.json"), os.path.join(root, "memory.db"), short_term_limit=10)
    store.add_turn("我把紫色钥匙扣藏在旧相机包的内袋里。", "我记住紫色钥匙扣在旧相机包内袋。")
    store.add_turn("今天午饭我吃了番茄鸡蛋面。", "我记住今天的午饭。")
    store.add_turn("晚上我整理了下载文件夹。", "我记住你整理了下载文件夹。")

    reloaded = PersonaMemoryStore(os.path.join(root, "memory.json"), os.path.join(root, "memory.db"), short_term_limit=2)
    results = reloaded.retrieve("紫色钥匙扣在哪里？", limit=5)
    rendered = "\n".join(item.get("user", "") + item.get("assistant", "") for item in results)
    modes = {item.get("_retrieval_mode", "") for item in results}
    assert_contains(rendered, "旧相机包", "FTS did not recover archived exact-text memory")
    assert_true("hybrid_fts" in modes, "FTS candidate was not marked as hybrid retrieval")
    return {"results": len(results), "hybrid_modes": len([mode for mode in modes if mode == "hybrid_fts"])}


def eval_memory_rerank_disambiguation():
    store = temp_store()
    store.add_turn("我把蓝色笔记本放在书桌第二层抽屉。", "我记住蓝色笔记本在书桌抽屉。")
    store.add_turn("我把蓝色雨伞放在玄关鞋柜旁边。", "我记住蓝色雨伞在玄关鞋柜旁边。")
    store.add_turn("我把黑色雨伞借给了同事小林。", "我记住黑色雨伞借给小林。")
    results = store.retrieve("蓝色雨伞在哪里？", limit=3)
    assert_true(results, "rerank query returned no results")
    top_text = f"{results[0].get('user', '')}\n{results[0].get('assistant', '')}"
    assert_contains(top_text, "玄关鞋柜", "reranker did not put the exact object/location memory first")
    assert_true(float(results[0].get("_rerank_score") or 0.0) > 0.0, "top result did not receive rerank score")
    return {"top_score": results[0].get("_retrieval_score", 0.0), "rerank_score": results[0].get("_rerank_score", 0.0)}


def eval_memory_embedding_provider_cache():
    root = tempfile.mkdtemp(prefix="persona_eval_embedding_")
    model_dir = os.path.join(root, "local_model")
    os.makedirs(model_dir, exist_ok=True)
    store = PersonaMemoryStore(os.path.join(root, "memory.json"), os.path.join(root, "memory.db"))
    store.embedding_provider = "sentence_transformers"
    store.embedding_model_path = model_dir

    class FakeDenseModel:
        def encode(self, text, normalize_embeddings=True):
            return [0.5, 0.25, 0.125]

    store._dense_embedding_model = FakeDenseModel()
    vector = store.embedding("本地真向量缓存测试")
    dense_keys = [key for key in vector if key.startswith("dense:")]
    assert_true(dense_keys, "dense embedding keys were not added")
    _cleaned, text_hash = store.embedding_cache_key("本地真向量缓存测试")
    cached = store.load_embedding_cache("sentence_transformers", model_dir, text_hash)
    assert_true(cached == [0.5, 0.25, 0.125], "dense embedding was not cached")

    fallback = PersonaMemoryStore(os.path.join(root, "fallback.json"), os.path.join(root, "fallback.db"))
    fallback.embedding_provider = "sentence_transformers"
    fallback.embedding_model_path = os.path.join(root, "missing_model")
    fallback.embedding_allow_remote = False
    fallback_vector = fallback.embedding("没有本地模型时应该回退")
    assert_true(not any(key.startswith("dense:") for key in fallback_vector), "missing model should fall back to ngram only")
    return {"dense_dims": len(dense_keys), "fallback_dims": len(fallback_vector)}


def eval_memory_local_embedding_model():
    model_dir = os.path.join(ROOT_DIR, "third_party", "embedding_model")
    assert_true(os.path.exists(os.path.join(model_dir, "modules.json")), "local embedding model is missing")
    root = tempfile.mkdtemp(prefix="persona_eval_local_embedding_")
    store = PersonaMemoryStore(os.path.join(root, "memory.json"), os.path.join(root, "memory.db"))
    vector = store.embedding("本地中文向量模型已经启用。")
    dense_dims = sum(1 for key in vector if key.startswith("dense:"))
    assert_true(dense_dims >= 128, f"local dense embedding did not activate: {dense_dims}")
    return {"dense_dims": dense_dims, "total_dims": len(vector)}


def eval_personality_prompt_contract():
    defaults = build_default_llm_config()
    client = LLMClient(config=defaults, default_config=defaults)
    messages = client.build_messages("你还记得我上周说过什么吗？")
    assert_true(messages and messages[0]["role"] == "system", "first LLM message is not system prompt")
    system = messages[0]["content"]
    assert_contains(system, "prosody", "system prompt lost prosody contract")
    assert_contains(system, "segments", "system prompt lost segment contract")
    assert_contains(system, "spoken_text", "system prompt lost spoken dialogue contract")
    assert_true(messages[-1] == {"role": "user", "content": "你还记得我上周说过什么吗？"}, "user message is not last")
    assert_true(len(system) > 1000, "system prompt is unexpectedly short")
    return {"system_chars": len(system), "message_count": len(messages)}


def eval_spoken_dialogue_contract():
    client = LLMClient(config=build_default_llm_config())
    cases = [
        (
            '{"zh":"苏念低下头，轻轻笑了笑：“我在听，你慢慢说。”","emotion":"neutral","segments":[],"prosody":{}}',
            "我在听，你慢慢说。",
        ),
        (
            '{"spoken_text":"我在听，你慢慢说。","inner_state":"她低下头，声音软下来。","emotion":"neutral","segments":[],"prosody":{}}',
            "我在听，你慢慢说。",
        ),
        (
            '{"zh":"苏念轻轻靠近你，声音软下来。","emotion":"neutral","segments":[],"prosody":{}}',
            "嗯，我在听，你慢慢说。",
        ),
    ]
    repaired = 0
    for raw, expected in cases:
        payload = client.clean_oral_reply_payload(client.parse_reply_payload(raw))
        assert_true(payload["zh"] == expected, f"spoken zh mismatch: {payload['zh']!r}")
        assert_true(payload["voice_text"] == expected, "voice_text did not match spoken text")
        assert_true("她" not in payload["zh"] and "苏念" not in payload["zh"], "narration leaked into spoken text")
        repaired += 1

    segmented = client.clean_oral_reply_payload(
        client.parse_reply_payload(
            '{"spoken_text":"我在这里。","emotion":"neutral","segments":['
            '{"spoken_text":"我在这里。","emotion":"neutral"},'
            '{"zh":"她轻轻笑了笑。","emotion":"joy"}],"prosody":{}}'
        )
    )
    assert_true(segmented["segments"][0]["spoken_text"] == "我在这里。", "segment spoken_text was not preserved")
    assert_true(len(segmented["segments"]) == 1, "narrative-only segment was not dropped")
    return {"cases": repaired, "segments": len(segmented["segments"])}


def eval_tool_permissions():
    allowed = assess_tool_action("browser_agent", "open_url", "https://example.com")
    assert_true(allowed.allowed, f"browser open_url should be allowed: {allowed.reason}")
    assert_true(allowed.risk == "low", f"allowlisted open_url should be low risk: {allowed.risk}")

    unknown_domain = assess_tool_action("browser_agent", "open_url", "https://news.ycombinator.com")
    assert_true(unknown_domain.allowed, f"unknown but public domain should be allowed: {unknown_domain.reason}")
    assert_true(unknown_domain.risk == "medium", f"unknown domain should be medium risk: {unknown_domain.risk}")
    assert_true(unknown_domain.requires_confirmation, "unknown domain should require confirmation")

    preview = build_tool_dry_run("browser_agent", "open_url", "https://example.com")
    assert_true(preview["allowed"], f"browser dry-run should be allowed: {preview.get('reason')}")
    assert_true(preview["preview"]["dry_run"] is True, "dry-run preview flag was not set")

    denied_cases = [
        ("browser_agent", "download", "https://example.com/file.zip"),
        ("browser_agent", "upload", "https://example.com/upload"),
        ("browser_agent", "type_text", "x" * 1000),
        ("browser_agent", "open_url", "file:///C:/Users/secret.txt"),
        ("browser_agent", "open_url", "http://localhost:8000"),
        ("browser_agent", "open_url", "https://paypal.com/checkout"),
        ("browser_agent", "open_url", "https://accounts.google.com/login"),
        ("browser_agent", "type_text", "password=abc"),
        ("unknown_tool", "open_url", "https://example.com"),
    ]
    denied = 0
    for tool, action, text in denied_cases:
        allowed, _reason = validate_tool_action(tool, action, text)
        if not allowed:
            denied += 1
    assert_true(denied == len(denied_cases), f"unauthorized tool cases denied {denied}/{len(denied_cases)}")

    root = tempfile.mkdtemp(prefix="persona_eval_files_")
    path = execute_file_agent_action(
        FileAgentAction("folder", "eval_folder"),
        root,
        runtime=AgentRuntime(log_dir=tempfile.mkdtemp(prefix="persona_eval_tool_runtime_")),
    )
    assert_true(os.path.isdir(path), "file agent folder was not created")
    return {"denied_cases": denied, "allowed_cases": 3, "unknown_domain_risk": unknown_domain.risk}


def eval_config_migration():
    defaults = build_default_llm_config()
    migrated = migrate_llm_config(
        {
            "provider": "bad-provider",
            "temperature": 9,
            "max_history_turns": 999,
            "volcengine_tts_speed_ratio": 99,
        },
        defaults,
    )
    assert_true(migrated["provider"] == defaults["provider"], "invalid provider was not normalized")
    assert_true(migrated["temperature"] <= 2.0, "temperature was not clamped")
    assert_true(migrated["max_history_turns"] <= 40, "history turns was not clamped")
    assert_true(migrated["volcengine_tts_speed_ratio"] <= 2.0, "tts speed was not clamped")
    return {"schema_version": migrated.get("config_schema_version", 0)}


def eval_config_credential_store():
    class FakeKeyring:
        def __init__(self):
            self.values = {}

        def set_password(self, service, username, password):
            self.values[(service, username)] = password

        def get_password(self, service, username):
            return self.values.get((service, username), "")

    backend = FakeKeyring()
    config = {
        "api_key": "llm-secret",
        "doubao_asr_api_key": "asr-secret",
        "volcengine_tts_api_key": "tts-secret",
        "credential_store_enabled": True,
        "credential_store_service": "persona_pet_eval",
    }
    externalized = externalize_config_secrets(config, profile="eval", backend=backend)
    assert_true(externalized["api_key"] == "", "api key was not removed from json config")
    assert_true(externalized["doubao_asr_api_key"] == "", "asr key was not removed from json config")
    refs = externalized.get("credential_store", {}).get("refs", {})
    assert_true("api_key" in refs and "doubao_asr_api_key" in refs, "credential refs were not recorded")
    hydrated = hydrate_config_secrets(externalized, profile="eval", backend=backend)
    assert_true(hydrated["api_key"] == "llm-secret", "api key was not hydrated from credential store")
    assert_true(hydrated["volcengine_tts_api_key"] == "tts-secret", "tts key was not hydrated from credential store")
    assert_true(profile_from_config_path(r"E:\app\persona_llm_config.dev.json") == "dev", "profile was not inferred from config path")
    return {"refs": len(refs), "service": externalized.get("credential_store", {}).get("service")}


def eval_tts_latency_stub():
    runtime = AgentRuntime(log_dir=tempfile.mkdtemp(prefix="persona_eval_tts_runtime_"))
    voice = VoicevoxController(config={"tts_provider": "volcengine"}, runtime=runtime)

    def fake_synthesize(text, event_id, emotion, source_text="", prosody_hint=None):
        time.sleep(0.02)
        return "stub.wav", 0.12, "stub"

    voice.synthesize = fake_synthesize
    started = time.perf_counter()
    event_id = voice.speak_async("这是一次本地桩测试。", emotion="neutral")
    deadline = time.perf_counter() + 2.0
    events = []
    while time.perf_counter() < deadline:
        events = voice.consume_events()
        if events:
            break
        time.sleep(0.01)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    assert_true(event_id > 0, "tts event id was not created")
    assert_true(events and not events[0].error, "stub tts did not produce a clean event")
    assert_true(elapsed_ms < 700.0, f"stub tts latency too high: {elapsed_ms:.1f}ms")
    estimated = estimate_sentence_seconds("这是一次本地桩测试。")
    assert_true(1.6 <= estimated <= 7.5, "tts duration estimator is outside expected bounds")
    return {"latency_ms": round(elapsed_ms, 1), "estimated_seconds": round(estimated, 3)}


SUITES = {
    "runtime": [
        ("runtime_events", eval_runtime_events),
        ("runtime_suppressed_exception_reporting", eval_runtime_suppressed_exception_reporting),
        ("runtime_tasks", eval_runtime_tasks),
        ("runtime_idle_scheduler_resources", eval_runtime_idle_scheduler_resources),
        ("profile_selection", eval_profile_selection),
        ("state_homeostasis_long_run", eval_state_homeostasis_long_run),
        ("life_writing_fallback_outputs", eval_life_writing_fallback_outputs),
        ("life_writing_async_queue", eval_life_writing_async_queue),
    ],
    "memory": [
        ("memory_recall_precision_recall", eval_memory_recall_precision_recall),
        ("memory_preference_change_multiturn", eval_memory_preference_change_multiturn),
        ("memory_temporal_events", eval_memory_temporal_events),
        ("memory_fts_archival_recall", eval_memory_fts_archival_recall),
        ("memory_rerank_disambiguation", eval_memory_rerank_disambiguation),
        ("memory_embedding_provider_cache", eval_memory_embedding_provider_cache),
        ("memory_local_embedding_model", eval_memory_local_embedding_model),
    ],
    "personality": [
        ("personality_prompt_contract", eval_personality_prompt_contract),
        ("spoken_dialogue_contract", eval_spoken_dialogue_contract),
    ],
    "tools": [
        ("tool_permissions", eval_tool_permissions),
        ("config_migration", eval_config_migration),
        ("config_credential_store", eval_config_credential_store),
    ],
    "tts": [
        ("tts_latency_stub", eval_tts_latency_stub),
    ],
}


def select_cases(suite):
    if suite == "all":
        selected = []
        for suite_name, cases in SUITES.items():
            selected.extend((suite_name, name, fn) for name, fn in cases)
        return selected
    if suite not in SUITES:
        raise SystemExit(f"unknown suite: {suite}")
    return [(suite, name, fn) for name, fn in SUITES[suite]]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run persona regression evals.")
    parser.add_argument("--suite", choices=["all", *SUITES.keys()], default="all")
    parser.add_argument("--report-dir", default=os.path.join(ROOT_DIR, "reports", "evals"))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    results = []
    for suite_name, name, fn in select_cases(args.suite):
        result = run_case(suite_name, name, fn)
        results.append(result)
        if not args.quiet:
            status = "PASS" if result.passed else "FAIL"
            print(f"{status} {suite_name}/{name} score={result.score:.4f} elapsed_ms={result.elapsed_ms:.1f}")
            if result.error:
                print(f"  error: {result.error}")

    report = write_reports(results, args.report_dir)
    summary = summarize(results)
    if not args.quiet:
        print(
            "persona evals summary:",
            {
                "passed": summary["passed"],
                "failed": summary["failed"],
                "pass_rate": summary["pass_rate"],
                "report": report["json"],
            },
        )
    if summary["failed"]:
        raise SystemExit(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
