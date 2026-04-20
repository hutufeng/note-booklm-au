"""Phase 3：多类型 Artifact 异步轮询生成器（解决等待过长和报错问题，支持自定义提示词）"""

import asyncio
import json
import os
from pathlib import Path

from notebooklm.rpc import (
    VideoFormat,
    VideoStyle,
    QuizQuantity,
    QuizDifficulty,
    ReportFormat,
)
from pipeline.progress_tracker import (
    save_progress,
    is_artifact_done,
    get_artifact_id,
    mark_artifact_generated,
    mark_artifact_downloaded,
)
from pipeline.prompts import get_prompts

OUTPUT_DIR = Path(__file__).parent.parent / "output"

_DIRS = {
    "video":     OUTPUT_DIR / "videos",
    "audio":     OUTPUT_DIR / "audios",
    "quiz":      OUTPUT_DIR / "quizzes",
    "flashcard": OUTPUT_DIR / "flashcards",
    "report":    OUTPUT_DIR / "reports",
    "slide":     OUTPUT_DIR / "slides",
    "infographic":OUTPUT_DIR / "infographics",
    "datatable": OUTPUT_DIR / "datatables",
}

for _d in _DIRS.values():
    _d.mkdir(parents=True, exist_ok=True)


def _find_topic_title(curriculum: list, topic_id: str) -> str:
    for ch in curriculum:
        for sec in ch["sections"]:
            for tp in sec["topics"]:
                if tp["id"] == topic_id:
                    return tp["title"]
    return topic_id


def _safe_name(topic_id: str, topic_title: str) -> str:
    return topic_id + "_" + topic_title[:20].replace("/", "_").replace(" ", "_")


# ─────────────────────────────────────────────────────────────────────────────
# 提交任务子程序 (仅提交不等待)
# ─────────────────────────────────────────────────────────────────────────────

async def _submit_video(client, notebook_id, topic_title, instructions):
    status = await client.artifacts.generate_video(
        notebook_id, instructions=instructions,
        video_format=VideoFormat.EXPLAINER, video_style=VideoStyle.WHITEBOARD,
        language="zh"
    )
    return status.task_id

async def _submit_audio(client, notebook_id, topic_title, instructions):
    status = await client.artifacts.generate_audio(
        notebook_id, instructions=instructions, language="zh"
    )
    return status.task_id

async def _submit_quiz(client, notebook_id, topic_title, instructions):
    status = await client.artifacts.generate_quiz(
        notebook_id, instructions=instructions,
        quantity=QuizQuantity.STANDARD, difficulty=QuizDifficulty.HARD,
    )
    return status.task_id

async def _submit_flashcard(client, notebook_id, topic_title, instructions):
    status = await client.artifacts.generate_flashcards(
        notebook_id, instructions=instructions,
    )
    return status.task_id

async def _submit_report(client, notebook_id, topic_title, instructions, book_type):
    report_type = ReportFormat.STUDY_GUIDE if book_type == "stem" else ReportFormat.BRIEFING_DOC
    status = await client.artifacts.generate_report(
        notebook_id, report_format=report_type, extra_instructions=instructions,
    )
    return status.task_id

async def _submit_slide(client, notebook_id, topic_title, instructions):
    status = await client.artifacts.generate_slide_deck(
        notebook_id, instructions=instructions,
    )
    return status.task_id

async def _submit_infographic(client, notebook_id, topic_title, instructions):
    status = await client.artifacts.generate_infographic(
        notebook_id, instructions=instructions,
    )
    return status.task_id

async def _submit_datatable(client, notebook_id, topic_title, instructions):
    status = await client.artifacts.generate_data_table(
        notebook_id, instructions=instructions,
    )
    return status.task_id


async def submit_artifact(client, notebook_id, topic_id, kind, progress, prompts,
                          book_title, curriculum, book_type, quiz_quantity):
    """提交任务，返回 (artifact_id, is_instant_result)"""
    topic_title = _find_topic_title(curriculum or [], topic_id)

    # 取 instructions
    instructions = ""
    prompt_tpl = ""
    if kind == "quiz":
        prompt_tpl = prompts["quiz_pro"] if quiz_quantity == "more" else prompts["quiz_free"]
    elif kind in prompts:
        prompt_tpl = prompts[kind]
    
    if prompt_tpl:
        instructions = prompt_tpl.format(book_title=book_title or "本书", topic_title=topic_title)
    
    if kind == "slide" and not instructions:
        instructions = f"为「{topic_title}」生成详细的演示文稿，使用简体中文"
    
    # 音频生成：附加「同步演示文稿」的要求
    if kind == "audio" and instructions:
        slide_aid = get_artifact_id(progress, topic_id, "slide")
        if slide_aid:
            instructions += (
                f"\n\n重要要求：当前知识点已生成了对应的演示文稿（PPT/PDF），"
                f"请让音频内容完全对齐该演示文稿的结构和页面顺序，"
                f"按照演示文稿从第一页到最后一页逐页进行解说，"
                f"确保听众可以一边看着演示文稿一边吜音频完成学习。"
            )
    
    print(f"    ↳ 提交生成 [{kind}]：{topic_title}")

    try:
        # 分发提交
        if kind == "video":
            aid = await _submit_video(client, notebook_id, topic_title, instructions)
        elif kind == "audio":
            aid = await _submit_audio(client, notebook_id, topic_title, instructions)
        elif kind == "quiz":
            aid = await _submit_quiz(client, notebook_id, topic_title, instructions)
        elif kind == "flashcard":
            aid = await _submit_flashcard(client, notebook_id, topic_title, instructions)
        elif kind == "report":
            aid = await _submit_report(client, notebook_id, topic_title, instructions, book_type)
        elif kind == "slide":
            aid = await _submit_slide(client, notebook_id, topic_title, instructions)
        elif kind == "infographic":
            aid = await _submit_infographic(client, notebook_id, topic_title, instructions)
        elif kind == "datatable":
            aid = await _submit_datatable(client, notebook_id, topic_title, instructions)
        else:
            return None, False
            
        mark_artifact_generated(progress, topic_id, kind, aid)
        save_progress(progress)
        print(f"      （任务ID: {aid[:12]}… 提交成功）")
        return aid, False
    except Exception as e:
        print(f"    ✗ 提交出错（{topic_title} - {kind}）：{e}")
        return None, False


# ─────────────────────────────────────────────────────────────────────────────
# 轮询与下载子程序
# ─────────────────────────────────────────────────────────────────────────────

async def check_and_download(client, notebook_id, topic_id, kind, artifact_id,
                             curriculum, progress, force_download: bool = False) -> bool:
    """检查任务状态，完成则下载并返回 True。未完成返回 False（超时失败也算作从队列移除而返回True但后续不会处理）"""
    topic_title = _find_topic_title(curriculum or [], topic_id)

    if not force_download:
        # 针对 SDK 视频状态判定的 BUG，对于 video 直接跳过 poll_status，利用尝试下载是否报错来充当完成检测
        if kind != "video":
            status = await client.artifacts.poll_status(notebook_id, artifact_id)
            if not status.is_complete and not status.is_failed:
                return False  # 继续等待

            if status.is_failed:
                print(f"\n  ✗ 任务已失败 [{kind}]：{topic_title}")
                return True # 从队列移除

    # 尝试下载
    out_path = ""
    safe_name = _safe_name(topic_id, topic_title)
    
    try:
        if kind == "video":
            out_path = _DIRS["video"] / f"{safe_name}.mp4"
            await client.artifacts.download_video(notebook_id, str(out_path), artifact_id=artifact_id)
        elif kind == "audio":
            out_path = _DIRS["audio"] / f"{safe_name}.mp3"
            await client.artifacts.download_audio(notebook_id, str(out_path), artifact_id=artifact_id)
        elif kind == "quiz":
            out_path = _DIRS["quiz"] / f"{safe_name}_quiz.json"
            await client.artifacts.download_quiz(notebook_id, str(out_path), artifact_id=artifact_id, output_format="json")
        elif kind == "flashcard":
            out_path = _DIRS["flashcard"] / f"{safe_name}_fc.json"
            await client.artifacts.download_flashcards(notebook_id, str(out_path), artifact_id=artifact_id, output_format="json")
        elif kind == "report":
            out_path = _DIRS["report"] / f"{safe_name}_report.md"
            await client.artifacts.download_report(notebook_id, str(out_path), artifact_id=artifact_id)
        elif kind == "slide":
            out_path = _DIRS["slide"] / f"{safe_name}.pdf"
            await client.artifacts.download_slide_deck(notebook_id, str(out_path), artifact_id=artifact_id, output_format="pdf")
        elif kind == "infographic":
            out_path = _DIRS["infographic"] / f"{safe_name}.png"
            await client.artifacts.download_infographic(notebook_id, str(out_path), artifact_id=artifact_id)
        elif kind == "datatable":
            out_path = _DIRS["datatable"] / f"{safe_name}.csv"
            await client.artifacts.download_data_table(notebook_id, str(out_path), artifact_id=artifact_id)
            
        mark_artifact_downloaded(progress, topic_id, kind, str(out_path))
        save_progress(progress)
        print(f"\n  ✓ 下载完成 [{kind}]：{out_path.name}")
        return True
    except Exception as e:
        print(f"  ⚠ 下载出错 [{kind}] {topic_title}：{e} (等待重试...)")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 核心循环引擎：并发+定频轮询
# ─────────────────────────────────────────────────────────────────────────────

async def run_generation(
    client,
    notebook_id: str,
    topic_ids: list[str],
    task_types: dict,
    account_plan: dict,
    progress: dict,
    curriculum: list = None,
    book_title: str = "",
    book_type: str = "stem",
):
    """
    全异步提交+轮询机制：维持最多 max_concurrent 个正在生成的任务。
    每隔 poll_interval 秒检测一次全部 pending 任务。
    避免单任务超时中断整个流程。
    """
    concurrent    = account_plan["concurrent"]
    cooldown      = max(30, account_plan.get("cooldown_seconds", 30))
    quiz_quantity = account_plan["quiz_quantity"]
    plan_label    = account_plan["label"]

    from pipeline.task_selector import ALL_ARTIFACT_TYPES
    order_map = {kind: i for i, (kind, _) in enumerate(ALL_ARTIFACT_TYPES)}
    active_kinds = [k for k, v in task_types.items() if v]
    active_kinds.sort(key=lambda k: order_map.get(k, 99))
    
    # 准备并自定义提示词
    default_prompts = get_prompts(book_type)
    custom_path = Path("custom_prompts.json")
    custom_path.write_text(json.dumps(default_prompts, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print("\n── 提示词设置 ───────────────────────────────────")
    ans = input("  是否自定义提示词？（Y=打开 custom_prompts.json 进行编辑 / N=使用默认，默认N）：").strip().upper()
    if ans == "Y":
        print(f"  已生成 custom_prompts.json")
        print(f"  将在系统中为您打开该文件，如果没有自动打开，请手动找到并编辑。")
        os.system(f"start {custom_path.name}")
        input("  >>> 编辑并保存完成后，请按回车键继续...")
        
    try:
        prompts = json.loads(custom_path.read_text("utf-8"))
        print("  ✓ 已加载 custom_prompts.json")
    except Exception as e:
        print(f"  ⚠ 加载 custom_prompts.json 失败：{e}。将使用默认提示词。")
        prompts = default_prompts

    # 展开所有需要执行的任务：[(topic_id, kind)]
    all_jobs = []
    for tid in topic_ids:
        for k in active_kinds:
            if not is_artifact_done(progress, tid, k):
                all_jobs.append((tid, k))
                
    if not all_jobs:
        print("\n  所有选中任务均已完成，无需生成。")
        return 0, 0

    print(f"\n{'═' * 60}")
    print(f"  🚀 开始异步队列生成任务")
    print(f"  账号类型：{plan_label}  并发上限：{concurrent} 个任务")
    print(f"  待处理总数：{len(all_jobs)} 项  ({','.join(active_kinds)})")
    print(f"  监测模式：每隔 {cooldown} 秒轮询一次任务状态...")
    print(f"{'═' * 60}\n")

    # pending_tasks 记录正在 NotebookLM 中生成的任务 ID
    # 格式: { artifact_id: (topic_id, kind) }
    pending_tasks = {}
    
    # 初始化时先加载之前提交但未下载（中断）的任务
    for tid in set([j[0] for j in all_jobs]):
        for k in active_kinds:
            if not is_artifact_done(progress, tid, k):
                aid = get_artifact_id(progress, tid, k)
                if aid:
                    pending_tasks[aid] = (tid, k)
                    # 从待提交列表中移除，因为它已经提交在生成中了
                    if (tid, k) in all_jobs:
                        all_jobs.remove((tid, k))

    # === 同步云端已有任务（未被本地记录的） ===
    if all_jobs:
        try:
            print("  正在扫描 NotebookLM 云端，尝试寻回已生成的进度...")
            arts = await client.artifacts.list(notebook_id)
            recovered = 0
            
            for tid, k in list(all_jobs):
                topic_title = _find_topic_title(curriculum or [], tid)
                if not topic_title:
                    continue
                    
                local_title = str(topic_title).strip().lower()
                # 提取前 4-6 个中文字符作为关键特征词进行容错匹配
                feature_word = local_title[:5] if len(local_title) >= 5 else local_title
                
                for a in arts:
                    # 匹配 kind
                    kind_str = str(getattr(a, "kind", ""))
                    if "." in kind_str: kind_str = kind_str.split('.')[-1].lower()
                    elif isinstance(getattr(a, "kind", ""), str): kind_str = getattr(a, "kind", "").lower()
                    if kind_str == "data_table": kind_str = "datatable"
                    if kind_str == "slide_deck": kind_str = "slide"
                    
                    if kind_str == k:
                        cloud_title = str(getattr(a, "title", "")).strip().lower()
                        # 闪卡或测试题的 title 往往是 "Quiz" 等固定词，匹配成功率低。
                        # 对于 report、audio 等，通常带题目标题
                        if local_title in cloud_title or feature_word in cloud_title:
                            mark_artifact_generated(progress, tid, k, str(a.id))
                            save_progress(progress)
                            all_jobs.remove((tid, k))
                            pending_tasks[str(a.id)] = (tid, k)
                            recovered += 1
                            print(f"    ✓ 找回遗失任务 [{k}] : {topic_title} (ID: {str(a.id)[:8]}...)")
                            break
            
            if recovered > 0:
                print(f"  ✓ 成功从云端找回 {recovered} 个本地进度丢失的任务，将直接进行下载！")
        except Exception as e:
            print(f"  ⚠ 扫描云端任务失败（忽略并按正常流程生成）：{e}")

    done_count = 0
    fail_count = 0

    while all_jobs or pending_tasks:
        # 1. 努力填满并发队列
        submitted_this_round = 0
        while len(pending_tasks) < concurrent and all_jobs:
            if submitted_this_round > 0:
                await asyncio.sleep(2) # 连续提交间距2秒，防止过多密集请求

            topic_id, kind = all_jobs.pop(0)
            
            aid, _ = await submit_artifact(
                client, notebook_id, topic_id, kind, progress, prompts,
                book_title, curriculum, book_type, quiz_quantity
            )
            
            if aid:
                pending_tasks[aid] = (topic_id, kind)
            else:
                fail_count += 1
            submitted_this_round += 1
            
        print(f"\n  [状态] 正在排队: {len(all_jobs)} | 正在生成: {len(pending_tasks)}")
        for aid, (tid, k) in pending_tasks.items():
            print(f"      … ⏳ {k} / {tid} ({aid[:8]}...)")

        if not pending_tasks:
            break

        # 2. 等待冷却时间进行下一轮轮询
        print(f"  [等待 {cooldown} 秒后检测状态...]")
        await asyncio.sleep(cooldown)

        # 3. 轮询已提交任务
        print(f"  [检测状态...]")
        completed_aids = []
        for aid, (tid, k) in pending_tasks.items():
            try:
                is_done = await check_and_download(client, notebook_id, tid, k, aid, curriculum, progress)
                if is_done:
                    completed_aids.append(aid)
                    done_count += 1
            except Exception as e:
                print(f"  ⚠ 轮询状态异常 [{k}]：{e}")
                # 不移除，下轮继续重试
                
        # 移除已完成的
        for aid in completed_aids:
            pending_tasks.pop(aid, None)

    print(f"\n{'═' * 60}")
    print(f"  📊 队列生成全部完成。新增完成 {done_count} 项任务。")
    print(f"{'═' * 60}\n")
    return done_count, fail_count
