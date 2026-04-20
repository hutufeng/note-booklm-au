"""Phase 2：目录展示 + 手动任务范围勾选 + 多类型 Artifact 选择"""

import re
from pipeline.progress_tracker import is_artifact_done, ARTIFACT_KINDS


# ─────────────────────────────────────────────────────────────────────────────
# Artifact 类型定义（展示用）
# ─────────────────────────────────────────────────────────────────────────────

ALL_ARTIFACT_TYPES = [
    ("slide",     "演示文稿 PDF   (Slide Deck)"),
    ("video",     "视频讲解       (Video Overview)"),
    ("audio",     "音频播客       (Audio Overview)"),
    ("quiz",      "互动测试题     (Quiz)"),
    ("flashcard", "闪卡记忆       (Flashcards)"),
    ("report",    "学习报告       (Study Guide / Briefing Doc)"),
    ("infographic", "信息图         (Infographic)"),
    ("datatable", "数据表格       (Data Table)"),
]

# 默认选中
_DEFAULT_SELECTED = {"video", "quiz"}


# ─────────────────────────────────────────────────────────────────────────────
# 展示目录
# ─────────────────────────────────────────────────────────────────────────────

def _status_marks(progress: dict, topic_id: str, kinds: list[str]) -> str:
    """生成状态标记串，如 ✓○○"""
    return "".join("✓" if is_artifact_done(progress, topic_id, k) else "○" for k in kinds)


def print_curriculum(curriculum: list, progress: dict, show_kinds: list[str] | None = None):
    """打印三级目录，已完成项用对应类型图标标注"""
    display_kinds = show_kinds or ["video", "quiz"]
    kind_labels = {
        "video": "视", "audio": "音", "quiz": "题",
        "flashcard": "卡", "report": "报", "slide": "slides",
        "infographic": "信", "datatable": "表",
    }
    legend = "  ".join(f"{kind_labels.get(k,'?')}={k[:3]}" for k in display_kinds)

    total_ch = len(curriculum)
    total_sec = sum(len(ch["sections"]) for ch in curriculum)
    total_tp = sum(len(s["topics"]) for ch in curriculum for s in ch["sections"])

    print("\n" + "═" * 70)
    print(f"  课程目录  ({total_ch}章 · {total_sec}节 · {total_tp}个知识点)")
    print(f"  图例：✓=已完成 ○=未完成  列顺序: {legend}")
    print("═" * 70)

    for ch in curriculum:
        print(f"\n  【{ch['id'].upper()}】{ch['title']}")
        for sec in ch["sections"]:
            print(f"\n    [{sec['id']}] {sec['title']}")
            for tp in sec["topics"]:
                marks = _status_marks(progress, tp["id"], display_kinds)
                print(f"      [{tp['id']}] {marks}  {tp['title']}")

    print("═" * 70)


# ─────────────────────────────────────────────────────────────────────────────
# 解析用户输入 → topic_id 列表
# ─────────────────────────────────────────────────────────────────────────────

def _all_topic_ids(curriculum: list) -> list[str]:
    return [tp["id"] for ch in curriculum for sec in ch["sections"] for tp in sec["topics"]]


def _ids_for_chapter(curriculum: list, ch_id: str) -> list[str]:
    for ch in curriculum:
        if ch["id"].lower() == ch_id.lower():
            return [tp["id"] for sec in ch["sections"] for tp in sec["topics"]]
    return []


def _ids_for_section(curriculum: list, sec_id: str) -> list[str]:
    for ch in curriculum:
        for sec in ch["sections"]:
            if sec["id"].lower() == sec_id.lower():
                return [tp["id"] for tp in sec["topics"]]
    return []


def _ids_for_topic(curriculum: list, tp_id: str) -> list[str]:
    for ch in curriculum:
        for sec in ch["sections"]:
            for tp in sec["topics"]:
                if tp["id"].lower() == tp_id.lower():
                    return [tp["id"]]
    return []


def parse_selection(raw: str, curriculum: list) -> list[str]:
    """解析用户输入，返回 topic_id 列表"""
    raw = raw.strip().lower()
    if raw == "all":
        return _all_topic_ids(curriculum)

    result = []
    for part in [p.strip() for p in raw.split(",") if p.strip()]:
        if re.search(r"_t\d+$", part):
            ids = _ids_for_topic(curriculum, part)
        elif re.search(r"_s\d+$", part):
            ids = _ids_for_section(curriculum, part)
        else:
            ids = _ids_for_chapter(curriculum, part)

        if not ids:
            print(f"  ⚠ 未找到：{part}（已跳过）")
        else:
            result.extend(ids)

    seen, unique = set(), []
    for x in result:
        if x not in seen:
            seen.add(x)
            unique.append(x)
    return unique


# ─────────────────────────────────────────────────────────────────────────────
# 多选 Artifact 类型
# ─────────────────────────────────────────────────────────────────────────────

def select_artifact_types(pre_selected: set[str] | None = None) -> dict[str, bool]:
    """
    终端多选界面：数字切换选中状态，回车确认。
    返回 {kind: bool} 字典。
    """
    selected = set(pre_selected) if pre_selected is not None else set(_DEFAULT_SELECTED)

    print("\n── 选择生成哪些 Artifact 类型 ─────────────────────")
    print("  输入数字切换选中/取消，直接回车确认")
    print()

    while True:
        for idx, (kind, label) in enumerate(ALL_ARTIFACT_TYPES, 1):
            mark = "[x]" if kind in selected else "[ ]"
            print(f"    {idx}. {mark} {label}")

        raw = input("\n  输入编号（可多个，用空格或逗号分隔），回车确认：").strip()

        if not raw:
            if not selected:
                print("  ⚠ 请至少选择一种类型！")
                continue
            break

        toggle = set()
        for token in re.split(r"[,\s]+", raw):
            token = token.strip()
            if not token:
                continue
            try:
                i = int(token) - 1
                if 0 <= i < len(ALL_ARTIFACT_TYPES):
                    toggle.add(ALL_ARTIFACT_TYPES[i][0])
                else:
                    print(f"  ⚠ 编号 {token} 超出范围")
            except ValueError:
                print(f"  ⚠ 无效输入：{token}")

        for kind in toggle:
            if kind in selected:
                selected.discard(kind)
            else:
                selected.add(kind)

        print()

    chosen = {k: True for k in selected}
    kinds_str = "、".join(
        label for kind, label in ALL_ARTIFACT_TYPES if kind in selected
    )
    print(f"\n  ✓ 已选择：{kinds_str}\n")
    return chosen


# ─────────────────────────────────────────────────────────────────────────────
# 账号计划
# ─────────────────────────────────────────────────────────────────────────────

def select_account_plan() -> dict:
    print("\n── 选择 NotebookLM 账号类型 ──────────────────────")
    print("  [1] 免费账号（串行·冷却30秒·每批5个任务）")
    print("  [2] Pro 账号（3路并发·冷却10秒·每批15个任务）")
    print()
    while True:
        c = input("请选择（1/2）：").strip()
        if c == "1":
            return {
                "plan": "free", "concurrent": 1, "cooldown_seconds": 30,
                "batch_size": 5, "quiz_quantity": "standard", "label": "免费账号",
            }
        elif c == "2":
            return {
                "plan": "pro", "concurrent": 3, "cooldown_seconds": 10,
                "batch_size": 15, "quiz_quantity": "more", "label": "Pro 账号",
            }
        print("  请输入 1 或 2")


# ─────────────────────────────────────────────────────────────────────────────
# 完整选择流程
# ─────────────────────────────────────────────────────────────────────────────

def run_task_selection(
    curriculum: list, progress: dict
) -> tuple[list[str], dict, dict]:
    """
    展示目录 → 选范围 → 跳过已完成 → 选 Artifact 类型 → 选账号计划。
    返回 (selected_topic_ids, task_types, account_plan)
    """
    selected_kinds = list(ARTIFACT_KINDS.keys())
    print_curriculum(curriculum, progress, show_kinds=selected_kinds)

    print("\n── 选择生成范围 ──────────────────────────────────")
    print("  all               → 全部知识点")
    print("  ch01              → 整章")
    print("  ch01_s02          → 整节")
    print("  ch01_s02_t01      → 单个知识点")
    print("  ch01,ch06_s03     → 组合（逗号分隔）")
    print()

    while True:
        raw = input("请输入选择范围：\n> ").strip()
        if not raw:
            print("  请输入内容")
            continue
        selected = parse_selection(raw, curriculum)
        if not selected:
            print("  没有匹配到知识点，请重新输入")
            continue
        print(f"\n  共选中 {len(selected)} 个知识点")
        break

    # 选 Artifact 类型
    task_types = select_artifact_types()

    # 如果勾选了 audio 但没勾选 slide，进行友情提示
    if task_types.get("audio") and not task_types.get("slide"):
        # 检查选中的知识点中，是否还有没生成过 slide 的
        needs_slide = any(not is_artifact_done(progress, tid, "slide") for tid in selected)
        if needs_slide:
            print("\n  💡【强烈建议】您勾选了「音频」，但部分知识点还没有生成「演示文稿（Slide）」！")
            print("  如果先生成演示文稿，音频将自动『对齐演示文稿解说』，学习体验更好。")
            add_slide = input("  是否自动为您补充勾选「演示文稿」？（Y=是 / N=否，默认Y）：").strip().upper()
            if add_slide != "N":
                task_types["slide"] = True
                print("  ✓ 已补充勾选「演示文稿」")

    # 跳过在所有 *已选* 类型上都完成的知识点
    # 按照 ALL_ARTIFACT_TYPES 的顺序对 active_kinds 进行排序，确保 slide 在 audio 之前处理
    order_map = {kind: i for i, (kind, _) in enumerate(ALL_ARTIFACT_TYPES)}
    active_kinds = [k for k, v in task_types.items() if v]
    active_kinds.sort(key=lambda k: order_map.get(k, 99))

    def _all_done(tid):
        return all(is_artifact_done(progress, tid, k) for k in active_kinds)

    fully_done = [tid for tid in selected if _all_done(tid)]
    pending    = [tid for tid in selected if not _all_done(tid)]

    print(f"\n  {len(pending)} 个待处理，{len(fully_done)} 个已全部完成")

    if fully_done:
        ans = input("  是否跳过「已全部完成」的知识点？（Y=跳过/N=重新生成，默认Y）：").strip().upper()
        if ans != "N":
            selected = pending
            print(f"  → 实际处理 {len(selected)} 个知识点")

    if not selected:
        print("  所有选中知识点均已完成！")
        return [], {}, {}

    account_plan = select_account_plan()

    # 预估时间
    n = len(selected)
    task_count = len(active_kinds)
    total_tasks = n * task_count
    concurrent = account_plan["concurrent"]
    cooldown = account_plan["cooldown_seconds"]
    batch = account_plan["batch_size"]
    batches = (total_tasks + batch - 1) // batch
    est_min = (total_tasks / concurrent) * 3 + batches * (cooldown / 60)

    kinds_label = "、".join(label for kind, label in ALL_ARTIFACT_TYPES if kind in task_types)
    print(f"\n  📋 任务摘要")
    print(f"  {'─' * 47}")
    print(f"  知识点数量：{n}")
    print(f"  生成类型：{kinds_label}")
    print(f"  账号类型：{account_plan['label']}")
    print(f"  总任务数：{total_tasks}")
    print(f"  预估时间：约 {est_min:.0f} 分钟（受网络和 NotebookLM 响应影响）")
    print(f"  {'─' * 47}")

    if input("\n确认开始执行？（Y/N）：").strip().upper() != "Y":
        print("  已取消")
        return [], {}, {}

    return selected, task_types, account_plan
