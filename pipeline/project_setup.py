"""Phase 0：项目选择 + Source 上传 + 书籍信息配置（与任务生成解耦）"""

import json
from pathlib import Path
from typing import Optional

CONFIG_FILE = Path(__file__).parent.parent / "config.json"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_config(config: dict):
    CONFIG_FILE.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 书籍基本信息配置
# ─────────────────────────────────────────────────────────────────────────────

def configure_book_info(existing_config: dict) -> dict:
    """询问书名和书籍类型，返回更新后的配置字段"""
    from pipeline.prompts import select_book_type, BOOK_TYPES

    print("\n── 书籍基本信息 ──────────────────────────────────")

    # 书名
    old_title = existing_config.get("book_title", "")
    prompt_title = f"请输入书籍名称（当前：{old_title}，直接回车保留）：\n> " if old_title else "请输入书籍名称：\n> "
    title_input = input(prompt_title).strip()
    book_title = title_input if title_input else old_title
    if not book_title:
        book_title = "未命名书籍"

    # 书籍类型
    old_type = existing_config.get("book_type", "")
    old_type_label = BOOK_TYPES.get(old_type, {}).get("label", "")
    if old_type:
        keep = input(f"\n当前书籍类型：{old_type_label}，是否更改？（Y/N，默认 N）：").strip().upper()
        if keep != "Y":
            return {"book_title": book_title, "book_type": old_type}

    book_type = select_book_type()
    return {"book_title": book_title, "book_type": book_type}


# ─────────────────────────────────────────────────────────────────────────────
# 主配置流程
# ─────────────────────────────────────────────────────────────────────────────

async def run_project_setup(client, existing_config: dict | None = None) -> dict:
    """
    引导用户：
    1. 选择/新建 NotebookLM 项目
    2. 管理 Sources（显示已有、可选上传新文件）
    3. 配置书籍信息（书名 + 理工/文科类型）
    返回完整 config dict。
    """
    if existing_config is None:
        existing_config = {}

    print("\n" + "═" * 62)
    print("  📚  NotebookLM 项目配置")
    print("═" * 62)

    # ── 1. Notebook 选择 / 新建 ────────────────────────────────
    print("\n正在获取现有项目列表…")
    try:
        notebooks = await client.notebooks.list()
    except Exception as e:
        print(f"  [错误] 无法获取项目列表：{e}")
        raise

    notebook_id: Optional[str] = None
    notebook_title: str = ""

    if notebooks:
        print(f"\n发现 {len(notebooks)} 个现有项目：\n")
        for i, nb in enumerate(notebooks, 1):
            tag = " ← 当前" if nb.id == existing_config.get("notebook_id") else ""
            print(f"  [{i:2d}] {nb.title}  (ID: {nb.id[:12]}…){tag}")
        print(f"  [ N] 新建项目\n")

        while True:
            choice = input("请选择项目编号，或输入 N 新建：").strip().upper()
            if choice == "N":
                break
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(notebooks):
                    nb = notebooks[idx]
                    notebook_id, notebook_title = nb.id, nb.title
                    print(f"\n  ✓ 已选择：{notebook_title}")
                    break
                print("  超出范围，请重试")
            except ValueError:
                print("  请输入数字或 N")
    else:
        print("  （暂无已有项目，将新建）")

    if not notebook_id:
        old_title = existing_config.get("notebook_title", "")
        default = old_title or "读书学习项目"
        raw = input(f"\n请输入新项目名称（默认：{default}）：\n> ").strip()
        notebook_title = raw if raw else default
        print(f"\n  正在创建项目「{notebook_title}」…")
        nb = await client.notebooks.create(notebook_title)
        notebook_id = nb.id
        print(f"  ✓ 创建成功，ID: {notebook_id[:16]}…")

    # ── 2. Sources 管理 ────────────────────────────────────────
    print(f"\n正在获取「{notebook_title}」的资源列表…")
    sources = await client.sources.list(notebook_id)

    if sources:
        print(f"\n已有 {len(sources)} 个资源：")
        for s in sources:
            src_type = str(s.kind) if hasattr(s, "kind") else "?"
            print(f"  ✓ [{src_type}] {s.title or '无标题'}")
    else:
        print("\n  （该项目暂无资源）")

    print()
    while True:
        upload_raw = (
            input("上传新文件？（输入路径，或直接回车跳过）：\n> ")
            .strip().strip('"').strip("'")
        )
        if not upload_raw:
            break
        file_path = Path(upload_raw)
        if not file_path.exists():
            print(f"  [错误] 文件不存在：{upload_raw}")
            continue

        # 幂等：按文件名匹配
        if any(file_path.stem in (s.title or "") for s in sources):
            print(f"  ⚠ 「{file_path.name}」已存在，跳过")
        else:
            print(f"  正在上传「{file_path.name}」…")
            try:
                new_src = await client.sources.add_file(notebook_id, file_path)
                sources.append(new_src)
                print(f"  ✓ 上传成功：{new_src.title or file_path.name}")
            except Exception as e:
                print(f"  [错误] 上传失败：{e}")

        if input("\n继续上传？（Y/N）：").strip().upper() != "Y":
            break

    # ── 3. 书籍信息 ────────────────────────────────────────────
    book_info = configure_book_info(existing_config)

    # ── 4. 保存配置 ─────────────────────────────────────────────
    config = {
        **existing_config,
        "notebook_id": notebook_id,
        "notebook_title": notebook_title,
        "source_ids": [s.id for s in sources],
        **book_info,
    }
    save_config(config)

    print(f"\n  ✓ 配置已保存")
    print(f"    书名：{config['book_title']}")
    print(f"    类型：{config['book_type']}")
    print(f"    资源：{len(config['source_ids'])} 个文件")
    print("═" * 62)
    return config
