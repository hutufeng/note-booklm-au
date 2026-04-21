"""
课程目录管理器（三级存储策略）：

优先级（读取）：
  1. NotebookLM Note  → 查找标题为 "[课程目录] {book_title}" 的笔记
  2. 本地 JSON 缓存   → curriculum/generated_curriculum.json
  3. 不存在 → 提示用户手动触发生成

生成后同步写入：
  - NotebookLM Note（持久化，换机器也能找到）
  - 本地 JSON 缓存（离线备份）
"""

import json
import re
from pathlib import Path

CACHE_FILE = Path(__file__).parent / "generated_curriculum.json"

# Note 标题前缀，便于在 NotebookLM 中精确识别
NOTE_TITLE_PREFIX = "[课程目录]"


# ─── 校验 ───────────────────────────────────────────────────────────────────

def _validate(curriculum: list) -> bool:
    if not isinstance(curriculum, list) or not curriculum:
        return False
    for ch in curriculum:
        if not all(k in ch for k in ("id", "title", "sections")):
            return False
        for sec in ch["sections"]:
            if not all(k in sec for k in ("id", "title", "topics")):
                return False
            for tp in sec["topics"]:
                if not all(k in tp for k in ("id", "title")):
                    return False
    return True


def _extract_json(text: str) -> list | None:
    text = re.sub(r"```(?:json)?", "", text).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start: end + 1])
    except json.JSONDecodeError:
        return None


def _stats(curriculum: list) -> str:
    ch = len(curriculum)
    sec = sum(len(c["sections"]) for c in curriculum)
    tp = sum(len(s["topics"]) for c in curriculum for s in c["sections"])
    return f"{ch} 章 · {sec} 节 · {tp} 个知识点"


# ─── NotebookLM Note 操作 ─────────────────────────────────────────────────────

def _note_title(book_title: str) -> str:
    return f"{NOTE_TITLE_PREFIX} {book_title}"


async def _find_note_in_notebooklm(client, notebook_id: str, book_title: str) -> dict | None:
    """在 NotebookLM 笔记中查找课程目录 Note，返回 Note 对象或 None"""
    try:
        notes = await client.notes.list(notebook_id)
        target = _note_title(book_title)
        for note in notes:
            if note.title and note.title.strip() == target:
                return note
    except Exception as e:
        print(f"  ⚠ 查找笔记时出错：{e}")
    return None


async def _load_from_note(client, notebook_id: str, note) -> list | None:
    """从 Note 中解析课程目录 JSON"""
    try:
        full_note = await client.notes.get(notebook_id, note.id)
        content = full_note.content if hasattr(full_note, "content") else str(full_note)
        data = _extract_json(content)
        if data and _validate(data):
            return data
    except Exception as e:
        print(f"  ⚠ 读取笔记内容时出错：{e}")
    return None


async def _save_to_note(client, notebook_id: str, book_title: str, curriculum: list):
    """将课程目录保存为 NotebookLM 笔记"""
    title = _note_title(book_title)
    content = json.dumps(curriculum, ensure_ascii=False, indent=2)
    try:
        # 如果已存在则更新，否则新建
        existing = await _find_note_in_notebooklm(client, notebook_id, book_title)
        if existing:
            await client.notes.update(notebook_id, existing.id, content, title)
            print(f"  ✓ 已更新 NotebookLM 笔记：「{title}」")
        else:
            await client.notes.create(notebook_id, title=title, content=content)
            print(f"  ✓ 已创建 NotebookLM 笔记：「{title}」")
    except Exception as e:
        print(f"  ⚠ 保存笔记失败（将保留本地缓存）：{e}")


# ─── 本地缓存操作 ─────────────────────────────────────────────────────────────

def _load_local_cache(book_title: str) -> list | None:
    cache_file = _get_cache_file(book_title)
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        if _validate(data):
            return data
    except Exception:
        pass
    return None


def _save_local_cache(book_title: str, curriculum: list):
    cache_file = _get_cache_file(book_title)
    cache_file.write_text(
        json.dumps(curriculum, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _get_cache_file(book_title: str) -> Path:
    """每本书独立缓存文件，书名中特殊字符替换为下划线"""
    safe = re.sub(r'[\\/:*?"<>|]', "_", book_title)
    return Path(__file__).parent / f"curriculum_{safe}.json"


# ─── 生成新目录（通过 AI）────────────────────────────────────────────────────

async def _generate_from_ai(
    client, notebook_id: str, book_title: str, book_type: str,
    depth: int = 3,
) -> list:
    """调用 NotebookLM chat.ask() 生成目录；最多重试 2 次
    depth: 1=仅章, 2=章+节, 3=章+节+知识点
    """
    from pipeline.prompts import get_prompts
    prompts = get_prompts(book_type)
    base_prompt = prompts["curriculum"].format(book_title=book_title)
    
    # 根据 depth 调整 prompt
    if depth == 1:
        base_prompt = base_prompt + (
            "\n\n特别要求：仅生成『章』级别（一级目录），sections 内的 topics 数组保持为空数组 []"
        )
    elif depth == 2:
        base_prompt = base_prompt + (
            "\n\n特别要求：仅生成『章 + 节』两级（二级目录），每个 section 下的 topics 为空数组 []"
        )
    # depth == 3 为默认，不需要額外修改

    print(f"\n  正在通过 NotebookLM 生成《{book_title}》课程目录（{depth}级，约 1~3 分钟）…")

    for attempt in range(1, 3):
        prompt = base_prompt if attempt == 1 else (
            base_prompt + "\n\n注意：仅输出合法 JSON，首字符必须是 `[`，末字符必须是 `]`。"
        )
        if attempt == 2:
            print("  ⤷ 第一次解析失败，正在重试…")
        try:
            result = await client.chat.ask(notebook_id, prompt)
            raw = result.answer or ""
        except Exception as e:
            raise RuntimeError(f"调用 NotebookLM 失败：{e}")

        curriculum = _extract_json(raw)
        if curriculum and _validate(curriculum):
            print(f"  ✓ 目录生成成功：{_stats(curriculum)}")
            return curriculum
        else:
            print(f"  ⤷ 第 {attempt} 次解析失败（回复预览：{raw[:100]}…）")

    raise ValueError("网页返回的目录格式无法解析，请检查 Source 是否已正确上传并索引完毕。")


# ─── 公共入口 ─────────────────────────────────────────────────────────────────

async def find_and_show_curriculum(
    client, notebook_id: str, book_title: str
) -> list | None:
    """
    查找已有目录（NotebookLM Note > 本地缓存），有则展示并返回，无则返回 None。
    """
    # 1. 查 NotebookLM Note
    print(f"\n  正在 NotebookLM 中查找《{book_title}》的课程目录笔记…")
    note = await _find_note_in_notebooklm(client, notebook_id, book_title)
    if note:
        curriculum = await _load_from_note(client, notebook_id, note)
        if curriculum:
            print(f"  ✓ 从 NotebookLM 笔记加载目录：{_stats(curriculum)}")
            print(f"    笔记标题：「{_note_title(book_title)}」")
            # 顺手更新本地缓存
            _save_local_cache(book_title, curriculum)
            return curriculum
        else:
            print("  ⚠ 找到笔记但内容解析失败，将查询本地缓存…")

    # 2. 查本地缓存
    curriculum = _load_local_cache(book_title)
    if curriculum:
        print(f"  ✓ 从本地缓存加载目录：{_stats(curriculum)}")
        print(f"    缓存文件：{_get_cache_file(book_title)}")
        return curriculum

    print("  （未找到已有目录）")
    return None


async def get_or_generate_curriculum(
    client,
    notebook_id: str,
    book_title: str,
    book_type: str,
    force_regenerate: bool = False,
    depth: int = 3,
) -> list:
    """
    主入口：
    - force_regenerate=False → 先查已有目录，有则返回
    - force_regenerate=True  → 强制重新生成
    - 找不到且用户拒绝生成 → 抛出 RuntimeError
    depth: 1=仅章, 2=章+节, 3=章+节+知识点（默认）
    """
    if not force_regenerate:
        existing = await find_and_show_curriculum(client, notebook_id, book_title)
        if existing:
            return existing

    # 询问用户是否生成
    print(f"\n  未找到《{book_title}》的课程目录。")
    choice = input("  是否现在通过 NotebookLM 自动生成？（Y/N）：").strip().upper()
    if choice != "Y":
        raise RuntimeError("用户取消目录生成，无法继绣。")

    curriculum = await _generate_from_ai(client, notebook_id, book_title, book_type, depth=depth)

    # 双写：NotebookLM Note + 本地缓存
    print("  正在保存目录…")
    await _save_to_note(client, notebook_id, book_title, curriculum)
    _save_local_cache(book_title, curriculum)
    print(f"  ✓ 目录已同步保存到 NotebookLM 笔记和本地缓存")

    return curriculum


# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def get_all_topic_ids(curriculum: list) -> list[str]:
    return [tp["id"] for ch in curriculum for sec in ch["sections"] for tp in sec["topics"]]


def find_topic_title(curriculum: list, topic_id: str) -> str:
    for ch in curriculum:
        for sec in ch["sections"]:
            for tp in sec["topics"]:
                if tp["id"] == topic_id:
                    return tp["title"]
    return topic_id
