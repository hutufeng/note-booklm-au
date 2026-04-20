"""任务管理器：列出所有任务状态，支持两种删除操作"""

import asyncio
from pathlib import Path
from pipeline.progress_tracker import (
    load_progress,
    save_progress,
    ARTIFACT_KINDS,
    get_artifact_id,
    get_artifact_path,
    clear_topic_progress,
    delete_local_files,
    get_all_artifact_ids,
    is_artifact_done,
)
from pipeline.task_selector import parse_selection, ALL_ARTIFACT_TYPES

# 类型中文简称（表格标题）
_KIND_CN = {
    "video":     "视频",
    "audio":     "音频",
    "quiz":      "题目",
    "flashcard": "闪卡",
    "report":    "报告",
    "slide":     "PPT",
    "mindmap":   "导图",
}


# ─────────────────────────────────────────────────────────────────────────────
# 展示任务列表
# ─────────────────────────────────────────────────────────────────────────────

def _find_topic_info(curriculum: list, topic_id: str) -> tuple[str, str]:
    """返回 (chapter_title, topic_title)"""
    for ch in curriculum:
        for sec in ch["sections"]:
            for tp in sec["topics"]:
                if tp["id"] == topic_id:
                    return ch["title"], tp["title"]
    return ("未知章节", topic_id)


def show_task_list(curriculum: list | None, progress: dict,
                   filter_mode: str = "all") -> list[str]:
    """
    展示所有任务状态表格。
    filter_mode: 'all' | 'done' | 'pending'
    返回展示的 topic_id 列表
    """
    kinds = list(ARTIFACT_KINDS.keys())
    topics_dict = progress.get("topics", {})

    if not topics_dict and (not curriculum):
        print("\n  （当前没有任何任务记录）\n")
        return []

    # 收集所有知识点（仅限 progress 里有记录的任务）
    all_ids: list[str] = list(topics_dict.keys())

    # 状态过滤
    def _has_any_done(tid):
        return any(is_artifact_done(progress, tid, k) for k in kinds)

    def _all_done(tid):
        return all(is_artifact_done(progress, tid, k) for k in kinds)

    if filter_mode == "done":
        display_ids = [tid for tid in all_ids if _has_any_done(tid)]
    elif filter_mode == "pending":
        display_ids = [tid for tid in all_ids if not _all_done(tid)]
    else:
        display_ids = all_ids

    if not display_ids:
        print(f"\n  （没有符合条件的任务）\n")
        return []

    # 表头
    kind_width = 4
    header_kinds = "  ".join(f"{_KIND_CN.get(k, k):^{kind_width}}" for k in kinds)
    print(f"\n{'═' * 74}")
    print(f"  {'知识点 ID':<22} {header_kinds}  标题")
    print(f"{'─' * 74}")

    for tid in display_ids:
        marks = "  ".join(
            f"{'✓':^{kind_width}}" if is_artifact_done(progress, tid, k)
            else f"{'○':^{kind_width}}"
            for k in kinds
        )
        _, title = _find_topic_info(curriculum or [], tid)
        print(f"  {tid:<22} {marks}  {title[:24]}")

    print(f"{'═' * 74}")
    print(f"  图例：✓=已完成  ○=未完成/无记录")
    print(f"  共展示 {len(display_ids)} 个知识点\n")
    return display_ids


# ─────────────────────────────────────────────────────────────────────────────
# 删除操作
# ─────────────────────────────────────────────────────────────────────────────

async def _delete_cloud_artifacts(client, notebook_id: str, progress: dict,
                                  topic_ids: list[str], kinds: list[str] | None = None):
    """删除 NotebookLM 云端 Artifact，释放配额"""
    total_deleted = 0
    total_failed  = 0
    for tid in topic_ids:
        aid_map = get_all_artifact_ids(progress, tid, kinds)
        for kind, aid in aid_map.items():
            try:
                ok = await client.artifacts.delete(notebook_id, aid)
                if ok:
                    print(f"    ✓ 删除云端 {kind} artifact: {aid[:12]}…")
                    total_deleted += 1
                else:
                    print(f"    ⚠ 删除失败（返回 False）：{kind} {aid[:12]}…")
                    total_failed += 1
            except Exception as e:
                print(f"    ✗ 删除出错（{kind}）：{e}")
                total_failed += 1
    return total_deleted, total_failed


def _delete_local_artifacts(progress: dict, topic_ids: list[str],
                            kinds: list[str] | None = None, curriculum: list | None = None) -> int:
    """删除本地已下载文件，返回删除数量"""
    deleted_count = 0
    from pipeline.artifact_generator import _DIRS, _safe_name, _find_topic_title
    
    for tid in topic_ids:
        removed = delete_local_files(progress, tid, kinds)
        deleted_count += len(removed)
        for f in removed:
            print(f"    ✓ 已删除本地文件：{Path(f).name}")
            
        # 即使 progress 没记录，也去对应的目录猜文件名并强制删除残留文件
        topic_title = _find_topic_title(curriculum or [], tid)
        safe = _safe_name(tid, topic_title)
        target_kinds = kinds or list(ARTIFACT_KINDS.keys())
        for k in target_kinds:
            ak_info = ARTIFACT_KINDS.get(k, {})
            ext = ak_info.get("ext", "")
            guessed = _DIRS.get(k, Path()) / f"{safe}{ext}"
            
            if guessed.exists() and str(guessed) not in removed:
                guessed.unlink()
                print(f"    ✓ 已强制删除残留文件：{guessed.name}")
                deleted_count += 1
                
            guessed_tmp = Path(str(guessed) + ".tmp")
            if guessed_tmp.exists():
                guessed_tmp.unlink()
                print(f"    ✓ 已强制删除残留中间文件：{guessed_tmp.name}")
                
    return deleted_count


# ─────────────────────────────────────────────────────────────────────────────
# 选择要操作的知识点 / 类型
# ─────────────────────────────────────────────────────────────────────────────

def _prompt_topic_selection(curriculum: list | None, label: str) -> list[str]:
    """让用户输入范围选择，返回 topic_id 列表"""
    while True:
        print(f"\n  {label}")
        print("  格式：all / ch01 / ch01_s02 / ch01_s02_t01  （逗号分隔多选）")
        raw = input("> ").strip()
        if not raw:
            print("  已取消")
            return []
        if curriculum:
            ids = parse_selection(raw, curriculum)
        else:
            # 无 curriculum 时直接解析 ID
            ids = [x.strip() for x in raw.replace(",", " ").split() if x.strip()]
        if not ids and raw != "all":
            print("  ⚠ 没有匹配到任何知识点，请重新输入")
            continue
        return ids


def _prompt_kind_selection() -> list[str] | None:
    """让用户选择要操作的 Artifact 类型，返回 kinds 列表或 None（全部）"""
    print("\n  选择操作哪些 Artifact 类型？")
    print("  0. 全部类型")
    for idx, (kind, label) in enumerate(ALL_ARTIFACT_TYPES, 1):
        print(f"  {idx}. {label}")
    raw = input("  输入编号（逗号或空格分隔），直接回车=全部：").strip()
    if not raw:
        return None  # 全部
    result = []
    for token in raw.replace(",", " ").split():
        try:
            i = int(token.strip())
            if i == 0:
                return None
            if 1 <= i <= len(ALL_ARTIFACT_TYPES):
                result.append(ALL_ARTIFACT_TYPES[i - 1][0])
        except ValueError:
            pass
    return result or None


# ─────────────────────────────────────────────────────────────────────────────
# 主菜单
# ─────────────────────────────────────────────────────────────────────────────

async def run_task_manager(client, notebook_id: str, curriculum: list | None):
    """任务管理主界面（async，因为云端删除需要 await）"""
    progress = load_progress()

    while True:
        print("""
── 任务管理 ───────────────────────────────────
  [1] 查看全部任务（含完成/未完成）
  [2] 只看已完成任务
  [3] 只看未完成/待生成任务
  ────────────────────────────────────
  [4] 删除云端 Artifact（释放 NotebookLM 配额，保留本地文件）
  [5] 删除本地文件（保留云端，清理磁盘空间）
  [6] 清除进度记录（仅清除 progress.json，不删文件/云端）
  ────────────────────────────────────
  [7] 手动下载/二次下载（从 NotebookLM 云端重新拉取）
  [B] 返回主菜单
────────────────────────────────────""")

        choice = input("  请选择：").strip().upper()

        if choice == "B":
            break

        elif choice in ("1", "2", "3"):
            mode = {"1": "all", "2": "done", "3": "pending"}[choice]
            progress = load_progress()
            show_task_list(curriculum, progress, filter_mode=mode)

        elif choice == "4":
            if not client or not notebook_id:
                print("\n  ⚠ 需要已连接 NotebookLM 才能执行云端删除，请先配置项目（选项 1）\n")
                continue
            progress = load_progress()
            show_task_list(curriculum, progress, filter_mode="done")
            ids = _prompt_topic_selection(curriculum, "选择要从 NotebookLM 删除哪些知识点的 Artifact：")
            if not ids:
                continue
            kinds = _prompt_kind_selection()
            kinds_label = "全部类型" if kinds is None else "、".join(kinds)
            confirm = input(f"\n  ⚠ 将删除 {len(ids)} 个知识点的云端 [{kinds_label}] Artifact，"
                            f"本地文件保留，确认？（Y/N）：").strip().upper()
            if confirm != "Y":
                print("  已取消")
                continue

            print(f"\n  开始删除云端 Artifact…")
            del_ok, del_fail = await _delete_cloud_artifacts(client, notebook_id, progress, ids, kinds)

            # 删除后清除 progress 里的 artifact_id（使其可重新生成），但保留 downloaded 标记
            for tid in ids:
                st = progress.get("topics", {}).get(tid, {})
                target_kinds = kinds or list(ARTIFACT_KINDS.keys())
                for k in target_kinds:
                    st.pop(f"{k}_artifact_id", None)
            save_progress(progress)

            print(f"\n  完成：删除 {del_ok} 个，失败 {del_fail} 个")
            print("  progress.json 中的 artifact_id 已清除，可重新生成。\n")

        elif choice == "5":
            progress = load_progress()
            show_task_list(curriculum, progress, filter_mode="done")
            ids = _prompt_topic_selection(curriculum, "选择要删除本地文件的知识点：")
            if not ids:
                continue
            kinds = _prompt_kind_selection()
            kinds_label = "全部类型" if kinds is None else "、".join(kinds)
            confirm = input(f"\n  ⚠ 将删除 {len(ids)} 个知识点的本地 [{kinds_label}] 文件，"
                            f"云端 Artifact 保留，确认？（Y/N）：").strip().upper()
            if confirm != "Y":
                print("  已取消")
                continue

            print(f"\n  开始删除本地文件…")
            count = _delete_local_artifacts(progress, ids, kinds, curriculum=curriculum)

            # 清除 downloaded 标记（但保留 artifact_id）
            for tid in ids:
                st = progress.get("topics", {}).get(tid, {})
                target_kinds = kinds or list(ARTIFACT_KINDS.keys())
                for k in target_kinds:
                    st.pop(f"{k}_downloaded", None)
                    st.pop(f"{k}_path", None)
            save_progress(progress)

            print(f"\n  完成：共删除 {count} 个本地文件。\n")

        elif choice == "6":
            progress = load_progress()
            ids = _prompt_topic_selection(curriculum, "选择要清除进度记录的知识点：")
            if not ids:
                continue
            kinds = _prompt_kind_selection()
            kinds_label = "全部类型" if kinds is None else "、".join(kinds)
            confirm = input(f"\n  ⚠ 将清除 {len(ids)} 个知识点的进度记录 [{kinds_label}]，"
                            f"不删除文件或云端，确认？（Y/N）：").strip().upper()
            if confirm != "Y":
                print("  已取消")
                continue

            for tid in ids:
                clear_topic_progress(progress, tid, kinds)
            print(f"  ✓ 已清除 {len(ids)} 个知识点的进度记录。\n")

        elif choice == "7":
            if not client or not notebook_id:
                print("\n  ⚠ 需要已连接 NotebookLM 才能执行二次下载\n")
                continue
            progress = load_progress()
            show_task_list(curriculum, progress, filter_mode="all")
            ids = _prompt_topic_selection(curriculum, "选择要重新下载的知识点：")
            if not ids:
                continue
            kinds = _prompt_kind_selection()
            kinds_label = "全部类型" if kinds is None else "、".join(kinds)
            
            # 筛选出有 artifact_id 的任务
            from pipeline.progress_tracker import ARTIFACT_KINDS as _KINDS
            from pipeline.artifact_generator import check_and_download
            from curriculum.curriculum_generator import get_all_topic_ids
            
            targets = []
            target_kinds = kinds or list(_KINDS.keys())
            for tid in ids:
                for k in target_kinds:
                    aid = get_artifact_id(progress, tid, k)
                    if aid:
                        targets.append((tid, k, aid))

            if not targets:
                print("\n  ⚠ 选中的知识点中没有可供二次下载的 Artifact（需要已经在 NotebookLM 上成功生成）")
                continue

            # 统计已下载 / 未下载数量
            done_cnt   = sum(1 for tid, k, _ in targets if is_artifact_done(progress, tid, k))
            undone_cnt = len(targets) - done_cnt

            print(f"\n  找到 {len(targets)} 个可下载的 Artifact（✓已下载 {done_cnt} 个，○未下载 {undone_cnt} 个）：")
            for tid, k, aid in targets:
                _, title = _find_topic_info(curriculum or [], tid)
                already = "✓已下载" if is_artifact_done(progress, tid, k) else "○未下载"
                print(f"    [{already}] {k:10} {tid} - {title[:20]}")

            # ── 选择下载模式 ──
            print("\n  请选择下载模式：")
            print("  [1] 仅下载未完成的（跳过已有文件，安全）")
            print("  [2] 全部覆盖下载（重新拉取所有文件，含已下载）")
            print("  [Q] 取消")
            dl_mode = input("  > ").strip().upper()
            if dl_mode == "Q" or dl_mode not in ("1", "2"):
                print("  已取消")
                continue

            overwrite = (dl_mode == "2")
            mode_label = "覆盖下载" if overwrite else "仅补充未下载"

            # 按模式过滤执行列表
            exec_targets = targets if overwrite else [
                (tid, k, aid) for tid, k, aid in targets
                if not is_artifact_done(progress, tid, k)
            ]
            if not exec_targets:
                print("  ✓ 所有选中项均已下载，无需补充（如需覆盖请选择模式2）")
                continue

            print(f"\n  模式：{mode_label} | 将处理 {len(exec_targets)} 个文件...\n")
            ok_count = skip_count = 0

            from pipeline.progress_tracker import ARTIFACT_KINDS as _AK
            from pipeline.artifact_generator import check_and_download, _DIRS, _safe_name, _find_topic_title

            # 预检状态：将 exec_targets 分为 就绪 / 已完成 / 失败
            ready_targets    = []   # 云端已完成，可下载
            pending_targets  = []   # 云端仍在生成中
            failed_targets   = []   # 云端已失败

            print("  预检云端状态...")
            for tid, k, aid in exec_targets:
                try:
                    status = await client.artifacts.poll_status(notebook_id, aid)
                    if status.is_complete:
                        ready_targets.append((tid, k, aid))
                    elif status.is_failed:
                        failed_targets.append((tid, k, aid))
                    else:
                        pending_targets.append((tid, k, aid))
                except Exception as e:
                    _, title = _find_topic_info(curriculum or [], tid)
                    print(f"    ⚠ 轮询状态失败 [{k}] {title}: {e}")
                    pending_targets.append((tid, k, aid))  # 保守处理

            # 打印预检结果
            if pending_targets:
                print(f"\n  ⏳ 以下 {len(pending_targets)} 个任务仍在云端生成中（或者 API 状态未能正确更新），无法立即下载：")
                for tid, k, _ in pending_targets:
                    _, title = _find_topic_info(curriculum or [], tid)
                    print(f"    … [{k}] {title}")
                
                # 新增强制绕过选项（针对 video 等 SDK 可能误判的状态）
                force_dl = input("\n    → 如果您确信它们在 NotebookLM 网页端已生成成功，是否强制跳过状态检查去下载？（Y/N）：").strip().upper()
                if force_dl == "Y":
                    print("    ⚠ 已将这些任务强制加入下载队列！")
                    # 将 pending 加入 ready 队列，并标记为 force_download=True
                    ready_targets.extend([(t[0], t[1], t[2], True) for t in pending_targets])
                    pending_targets = []
                else:
                    print("    → 请回到主菜单选择 [3]『开始生成』，让轮询队列自动等待并下载。")
            
            if failed_targets:
                print(f"\n  ✗ 以下 {len(failed_targets)} 个任务已在云端失败，需重新提交生成：")
                for tid, k, _ in failed_targets:
                    _, title = _find_topic_info(curriculum or [], tid)
                    print(f"    ✕ [{k}] {title}")
                print("    → 请回到主菜单选择 [3]『开始生成』重新提交。")

            # 原有 ready_targets 默认 force_download=False
            ready_targets_with_flags = [(t[0], t[1], t[2], False) for t in ready_targets if len(t) == 3] + [t for t in ready_targets if len(t) == 4]
            
            if not ready_targets_with_flags:
                print("\n  没有可立即下载的任务。\n")
                continue

            print(f"\n  ✓ {len(ready_targets_with_flags)} 个准备就绪，开始下载...\n")
            ok_count = err_count = 0

            for tid, k, aid, is_forced in ready_targets_with_flags:
                st = progress.get("topics", {}).get(tid, {})
                old_path = st.get(f"{k}_path", "")
                ak_info  = _AK.get(k, {})

                if overwrite:
                    # 覆盖模式：先清除标记，再删除旧文件（含 .tmp）
                    st.pop(f"{k}_downloaded", None)
                    st.pop(f"{k}_path", None)

                    def _del_if_exists(p: Path):
                        if p.exists():
                            p.unlink()

                    if old_path:
                        _del_if_exists(Path(old_path))
                        _del_if_exists(Path(old_path + ".tmp"))
                    else:
                        topic_title = _find_topic_title(curriculum or [], tid)
                        safe    = _safe_name(tid, topic_title)
                        ext     = ak_info.get("ext", "")
                        guessed = _DIRS.get(k, Path()) / f"{safe}{ext}"
                        _del_if_exists(guessed)
                        _del_if_exists(Path(str(guessed) + ".tmp"))

                try:
                    done = await check_and_download(client, notebook_id, tid, k, aid, curriculum, progress, force_download=is_forced)
                    if done:
                        ok_count += 1
                    else:
                        err_count += 1
                        _, title = _find_topic_info(curriculum or [], tid)
                        print(f"    ⚠ [{k}] {title} 下载未完成，请重试")
                except Exception as e:
                    err_count += 1
                    _, title = _find_topic_info(curriculum or [], tid)
                    print(f"    ✗ [{k}] {title} 下载失败：{e}")

            save_progress(progress)
            print(f"\n  完成（{mode_label})：成功 {ok_count} 个"
                  + (f"，异常 {err_count} 个" if err_count else "")
                  + (f"，仍在生成 {len(pending_targets)} 个" if pending_targets else "")
                  + (f"，已失败 {len(failed_targets)} 个" if failed_targets else "")
                  + "\n")

        else:
            print("  请输入有效选项")
