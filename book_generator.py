"""主程序入口：书籍 NotebookLM 自动化教学工具"""

import asyncio
import sys
from pathlib import Path

# 确保根目录在 sys.path
sys.path.insert(0, str(Path(__file__).parent))

from notebooklm import NotebookLMClient

from pipeline.project_setup import load_config, run_project_setup
from pipeline.task_selector import run_task_selection, print_curriculum
from pipeline.artifact_generator import run_generation
from pipeline.progress_tracker import load_progress, ARTIFACT_KINDS, is_artifact_done
from pipeline.prompts import BOOK_TYPES
from pipeline.task_manager import run_task_manager
from curriculum.curriculum_generator import (
    find_and_show_curriculum,
    get_or_generate_curriculum,
)
from web_builder.site_generator import generate_site, run_site_wizard


# ─────────────────────────────────────────────────────────────────────────────
# Banner & 状态显示
# ─────────────────────────────────────────────────────────────────────────────

def print_banner():
    print("""
╔══════════════════════════════════════════════════════════════╗
║    📚  书籍知识点视频教程自动生成工具                        ║
║    基于 notebooklm-py  ·  支持理工科 / 文科  ·  简体中文    ║
╚══════════════════════════════════════════════════════════════╝
""")


def print_status(config: dict, curriculum: list | None, progress: dict):
    book_title = config.get("book_title", "（未配置）")
    book_type = config.get("book_type", "")
    type_label = BOOK_TYPES.get(book_type, {}).get("label", "未配置")
    nb_title = config.get("notebook_title", "（未配置）")
    src_count = len(config.get("source_ids", []))

    if curriculum:
        all_ids = [tp["id"] for ch in curriculum for sec in ch["sections"] for tp in sec["topics"]]
        total = len(all_ids)
        cur_status = f"已加载（{len(curriculum)}章 · {total}个知识点）"
        parts = []
        for kind in ARTIFACT_KINDS:
            done = sum(1 for tid in all_ids if is_artifact_done(progress, tid, kind))
            if done > 0:
                parts.append(f"{kind}:{done}/{total}")
        prog_str = "  ".join(parts) if parts else "（无生成记录）"
    else:
        cur_status = "（未加载）"
        prog_str = "—"

    print(f"  ─── 当前状态 {'─' * 40}")
    print(f"  书 名：{book_title}")
    print(f"  类 型：{type_label}")
    print(f"  项 目：{nb_title}  ({src_count} 个资源)")
    print(f"  目 录：{cur_status}")
    print(f"  进 度：{prog_str}")
    print(f"  {'─' * 50}")


def print_main_menu():
    print("""
  ─── 主菜单 ──────────────────────────────────────────
  [1] 配置项目    选择/新建 NotebookLM 项目，管理资源，设置书名
  [2] 管理目录    查看/生成/重新生成课程目录（存于 NotebookLM 笔记）
  [3] 开始生成    选择知识点范围，选择生成类型（视频/音频/题目等）
  [4] 生成网页    自定义选择知识点和内容类型，打包离线 HTML 教程
  [5] 任务管理    查看任务状态，删除云端 Artifact / 本地文件
  [0] 退出
  ─────────────────────────────────────────────────────""")


# ─────────────────────────────────────────────────────────────────────────────
# 目录管理菜单
# ─────────────────────────────────────────────────────────────────────────────

async def handle_curriculum_menu(client, config: dict, curriculum: list | None) -> list | None:
    """目录管理子菜单"""
    notebook_id = config.get("notebook_id", "")
    book_title = config.get("book_title", "本书")
    book_type = config.get("book_type", "stem")

    if not notebook_id:
        print("\n  ⚠ 请先配置项目（选项 1）\n")
        return curriculum

    while True:
        print(f"\n── 目录管理「{book_title}」────────────────────────")
        if curriculum:
            total = sum(len(s["topics"]) for ch in curriculum for s in ch["sections"])
            print(f"  当前目录：{len(curriculum)} 章 · {total} 个知识点")
        else:
            print("  当前目录：未加载")

        print()
        print("  [1] 查看/加载目录（优先读取 NotebookLM 笔记）")
        print("  [2] 展示完整目录与进度")
        print("  [3] 重新生成目录（会覆盖 NotebookLM 笔记和本地缓存）")
        print("  [4] 删除目录（删除本地缓存 和/或 NotebookLM 笔记）")
        print("  [B] 返回主菜单")
        print()
        choice = input("  请选择：").strip().upper()

        if choice == "B":
            break

        elif choice == "1":
            progress = load_progress()
            result = await find_and_show_curriculum(client, notebook_id, book_title)
            if result:
                curriculum = result
            else:
                print(f"\n  NotebookLM 笔记和本地缓存中均未找到《{book_title}》的目录。")
                gen = input("  是否立即生成？（Y/N）：").strip().upper()
                if gen == "Y":
                    try:
                        curriculum = await get_or_generate_curriculum(
                            client, notebook_id, book_title, book_type, force_regenerate=False
                        )
                    except RuntimeError as e:
                        print(f"  ⚠ {e}")

        elif choice == "2":
            if not curriculum:
                print("\n  尚未加载目录，请先选择 [1]")
            else:
                progress = load_progress()
                print_curriculum(curriculum, progress)

        elif choice == "3":
            confirm = input(
                f"\n  ⚠ 将重新生成《{book_title}》的目录并覆盖已有版本，确认？（Y/N）："
            ).strip().upper()
            if confirm == "Y":
                # 询问目录层级
                print("\n  选择目录层级（默认3级）：")
                print("  [1] 一级目录（仅章）")
                print("  [2] 二级目录（章 + 节）")
                print("  [3] 三级目录（章 + 节 + 知识点）← 默认")
                depth_raw = input("  > ").strip()
                try:
                    depth = int(depth_raw) if depth_raw in ("1", "2", "3") else 3
                except ValueError:
                    depth = 3
                print(f"  ✓ 已选择：{depth} 级目录")
                try:
                    curriculum = await get_or_generate_curriculum(
                        client, notebook_id, book_title, book_type,
                        force_regenerate=True, depth=depth
                    )
                except Exception as e:
                    print(f"  ✗ 失败：{e}")

        elif choice == "4":
            print(f"\n  删除《{book_title}》的目录：")
            print("  [1] 仅删除本地缓存（保留 NotebookLM 笔记）")
            print("  [2] 仅删除 NotebookLM 笔记（保留本地缓存）")
            print("  [3] 全部删除（本地缓存 + NotebookLM 笔记）")
            print("  [Q] 取消")
            del_choice = input("  > ").strip().upper()
            if del_choice == "Q":
                print("  已取消")
                continue

            from curriculum.curriculum_generator import _get_cache_file, _find_note_in_notebooklm
            deleted_local = False
            deleted_note  = False

            if del_choice in ("1", "3"):
                cache_file = _get_cache_file(book_title)
                if cache_file.exists():
                    cache_file.unlink()
                    print(f"  ✓ 已删除本地缓存：{cache_file.name}")
                    deleted_local = True
                else:
                    print("  （本地缓存文件不存在）")

            if del_choice in ("2", "3"):
                try:
                    note = await _find_note_in_notebooklm(client, notebook_id, book_title)
                    if note:
                        await client.notes.delete(notebook_id, note.id)
                        print(f"  ✓ 已删除 NotebookLM 笔记")
                        deleted_note = True
                    else:
                        print("  （NotebookLM 中未找到对应笔记）")
                except Exception as e:
                    print(f"  ✗ 删除笔记失败：{e}")

            if deleted_local or deleted_note:
                curriculum = None
                print("  ✓ 目录已清除，当前内存中的目录已置空")

        else:
            print("  请输入有效选项")

    return curriculum


# ─────────────────────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    print_banner()

    # 加载配置
    config = load_config()
    progress = load_progress()
    curriculum: list | None = None

    # 连接 NotebookLM
    print("  正在连接 NotebookLM（须已运行 `notebooklm login` 完成认证）…")
    try:
        client_ctx = await NotebookLMClient.from_storage()
    except Exception as e:
        print(f"\n  [错误] 无法加载认证信息：{e}")
        print("  请先运行：notebooklm login")
        sys.exit(1)

    async with client_ctx as client:
        print("  ✓ 已连接 NotebookLM\n")

        # 首次运行自动尝试加载目录
        if config.get("notebook_id") and config.get("book_title"):
            try:
                curriculum = await find_and_show_curriculum(
                    client,
                    config["notebook_id"],
                    config["book_title"],
                )
            except Exception:
                pass

        while True:
            progress = load_progress()
            print_status(config, curriculum, progress)
            print_main_menu()

            choice = input("  请选择操作（0-5）：").strip()

            if choice == "0":
                print("\n  再见！\n")
                break

            elif choice == "1":
                config = await run_project_setup(client, config)
                curriculum = None
                try:
                    curriculum = await find_and_show_curriculum(
                        client, config["notebook_id"], config["book_title"]
                    )
                except Exception:
                    pass

            elif choice == "2":
                curriculum = await handle_curriculum_menu(client, config, curriculum)

            elif choice == "3":
                if not config.get("notebook_id"):
                    print("\n  ⚠ 请先配置项目（选项 1）\n")
                    continue
                if not curriculum:
                    print("\n  ⚠ 请先加载或生成目录（选项 2）\n")
                    continue

                progress = load_progress()
                selected_ids, task_types, account_plan = run_task_selection(
                    curriculum, progress
                )
                if not selected_ids:
                    print()
                    continue

                progress = load_progress()
                await run_generation(
                    client,
                    config["notebook_id"],
                    selected_ids,
                    task_types,
                    account_plan,
                    progress,
                    curriculum=curriculum,
                    book_title=config.get("book_title", ""),
                    book_type=config.get("book_type", "stem"),
                )

            elif choice == "4":
                print("\n── 生成 HTML 网页教程 ──────────────────────────────")
                progress = load_progress()
                run_site_wizard(curriculum, progress)
                print()

            elif choice == "5":
                await run_task_manager(
                    client,
                    config.get("notebook_id", ""),
                    curriculum,
                )

            else:
                print("\n  请输入 0-5 之间的数字\n")


if __name__ == "__main__":
    asyncio.run(main())
