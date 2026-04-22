"""Phase 4：将已生成的多类型 Artifact 组装为单机可运行的 HTML 教程"""

import json
import re
import shutil
import zipfile
from pathlib import Path

from curriculum.curriculum_generator import _load_local_cache
from pipeline.progress_tracker import load_progress, is_artifact_done

OUTPUT_DIR = Path(__file__).parent.parent / "output"
WEBSITE_DIR = OUTPUT_DIR / "website"
ASSETS_DIR = WEBSITE_DIR / "assets"
DATA_DIR = WEBSITE_DIR / "data"
VIDEOS_SITE_DIR = WEBSITE_DIR / "videos"
AUDIOS_SITE_DIR = WEBSITE_DIR / "audios"
REPORTS_SITE_DIR = WEBSITE_DIR / "reports"
FLASHCARDS_SITE_DIR = WEBSITE_DIR / "flashcards"
SLIDES_SITE_DIR = WEBSITE_DIR / "slides"
INFO_SITE_DIR = WEBSITE_DIR / "infographics"
TABLE_SITE_DIR = WEBSITE_DIR / "datatables"

# 可选展示类型（HTML 中支持的）
_SITE_KINDS = [
    ("video",     "视频讲解"),
    ("audio",     "音频播客"),
    ("slide",     "演示文稿"),
    ("quiz",      "互动测试题"),
    ("flashcard", "闪卡记忆"),
    ("report",    "学习报告"),
]


def _scan_first(src_dir: Path, prefix: str, suffix: str) -> Path | None:
    """在 src_dir 中找第一个以 prefix 开头、以 suffix 结尾的文件"""
    if not src_dir.exists():
        return None
    for f in src_dir.iterdir():
        if f.name.startswith(prefix) and f.name.endswith(suffix):
            return f
    return None


def build_curriculum_json(
    progress: dict,
    curriculum: list = None,
    selected_ids: list[str] | None = None,
    artifact_types: list[str] | None = None,
) -> list:
    """构建含指定 Artifact 路径和数据的课程 JSON。
    双轨匹配：优先 progress.json，兜底直接扫 output/ 目录（解决 progress 缺失问题）。
    """
    if curriculum is None:
        curriculum = []
    active_types = artifact_types or [
        "video", "audio", "slide", "quiz", "flashcard", "report", "infographic", "datatable"
    ]

    def _ensure_site(src: Path | None, site_dir: Path, dest_name: str) -> str | None:
        """复制文件到网站目录，返回相对路径；找不到返回 None"""
        if not src or not src.exists():
            return None
        site_dir.mkdir(parents=True, exist_ok=True)
        dest = site_dir / dest_name
        if not dest.exists():
            shutil.copy2(src, dest)
        return f"{site_dir.name}/{dest_name}"

    result = []
    for ch in curriculum:
        ch_data = {"id": ch["id"], "title": ch["title"], "sections": []}
        for sec in ch["sections"]:
            sec_data = {"id": sec["id"], "title": sec["title"], "topics": []}
            for tp in sec["topics"]:
                if selected_ids is not None and tp["id"] not in selected_ids:
                    continue
                status = progress.get("topics", {}).get(tp["id"], {})
                tid = tp["id"]

                # ── 视频 ────────────────────────────────────────────
                video_path = None
                if "video" in active_types:
                    vp = Path(status.get("video_path", "")) if status.get("video_downloaded") else None
                    if not (vp and vp.exists()):
                        vp = _scan_first(OUTPUT_DIR / "videos", tid, ".mp4")
                    video_path = _ensure_site(vp, VIDEOS_SITE_DIR, vp.name) if vp else None

                # ── 音频 ────────────────────────────────────────────
                audio_path = None
                if "audio" in active_types:
                    ap = Path(status.get("audio_path", "")) if status.get("audio_downloaded") else None
                    if not (ap and ap.exists()):
                        ap = _scan_first(OUTPUT_DIR / "audios", tid, ".mp3")
                    audio_path = _ensure_site(ap, AUDIOS_SITE_DIR, ap.name) if ap else None

                # ── Quiz ────────────────────────────────────────────
                quiz_data = []
                if "quiz" in active_types:
                    qp = Path(status.get("quiz_path", "")) if status.get("quiz_downloaded") else None
                    if not (qp and qp.exists()):
                        qp = _scan_first(OUTPUT_DIR / "quizzes", tid, "_quiz.json")
                    if qp and qp.exists():
                        try:
                            raw = json.loads(qp.read_text(encoding="utf-8"))
                            quiz_data = _parse_quiz_json(raw)
                        except Exception:
                            pass

                # ── 闪卡 ────────────────────────────────────────────
                flashcard_data = []
                if "flashcard" in active_types:
                    fp = Path(status.get("flashcard_path", "")) if status.get("flashcard_downloaded") else None
                    if not (fp and fp.exists()):
                        fp = _scan_first(OUTPUT_DIR / "flashcards", tid, "_fc.json")
                    if fp and fp.exists():
                        try:
                            raw = json.loads(fp.read_text(encoding="utf-8"))
                            fc = raw if isinstance(raw, dict) else {}
                            flashcard_data = fc.get("cards", [])
                        except Exception:
                            pass

                # ── 学习报告 ────────────────────────────────────────
                report_path = None
                report_content = None
                if "report" in active_types:
                    rp = Path(status.get("report_path", "")) if status.get("report_downloaded") else None
                    if not (rp and rp.exists()):
                        rp = _scan_first(OUTPUT_DIR / "reports", tid, "_report.md")
                    if rp and rp.exists():
                        report_path = _ensure_site(rp, REPORTS_SITE_DIR, rp.name)
                        try:
                            report_content = rp.read_text(encoding="utf-8")
                        except Exception:
                            pass

                # ── 演示文稿 ────────────────────────────────────────
                slide_path = None
                if "slide" in active_types or "audio" in active_types:
                    # 优先标准化命名（website/slides/{tid}.pdf）
                    if (SLIDES_SITE_DIR / f"{tid}.pdf").exists():
                        slide_path = f"slides/{tid}.pdf"
                    else:
                        sp = Path(status.get("slide_path", "")) if status.get("slide_downloaded") else None
                        if not (sp and sp.exists()):
                            sp = _scan_first(OUTPUT_DIR / "slides", tid, ".pdf")
                        if sp and sp.exists():
                            dest_name = f"{tid}.pdf"
                            SLIDES_SITE_DIR.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(sp, SLIDES_SITE_DIR / dest_name)
                            slide_path = f"slides/{dest_name}"

                # ── 信息图 ──────────────────────────────────────────
                infographic_path = None
                if "infographic" in active_types:
                    ip = Path(status.get("infographic_path", "")) if status.get("infographic_downloaded") else None
                    if not (ip and ip.exists()):
                        ip = _scan_first(OUTPUT_DIR / "infographics", tid, ".png")
                    infographic_path = _ensure_site(ip, INFO_SITE_DIR, ip.name) if ip else None

                # ── 数据表 ──────────────────────────────────────────
                datatable_path = None
                if "datatable" in active_types:
                    dp = Path(status.get("datatable_path", "")) if status.get("datatable_downloaded") else None
                    if not (dp and dp.exists()):
                        dp = _scan_first(OUTPUT_DIR / "datatables", tid, ".csv")
                    datatable_path = _ensure_site(dp, TABLE_SITE_DIR, dp.name) if dp else None

                # 如果没有任何数据，则跳过该知识点
                if not (video_path or audio_path or quiz_data or flashcard_data
                        or report_path or infographic_path or datatable_path or slide_path):
                    continue

                sec_data["topics"].append(
                    {
                        "id":      tid,
                        "title":   tp["title"],
                        "video":      video_path,
                        "audio":      audio_path,
                        "quiz":       quiz_data,
                        "flashcards": flashcard_data,
                        "report":     report_path,
                        "report_content": report_content,
                        "infographic": infographic_path,
                        "datatable": datatable_path,
                        "slide":      slide_path,
                        "mindmap":    status.get("mindmap_downloaded") and status.get("mindmap_path"),
                    }
                )
            if sec_data["topics"]:
                ch_data["sections"].append(sec_data)
        if ch_data["sections"]:
            result.append(ch_data)
    return result


def _parse_quiz_json(raw) -> list:
    """将 NotebookLM quiz JSON 标准化为 [{question, options, answer, explanation}]"""
    questions = []
    # NotebookLM quiz JSON 格式：可能是列表或含 questions 字段的 dict
    items = raw if isinstance(raw, list) else raw.get("questions", raw.get("items", []))
    for item in items:
        q = {
            "question": item.get("question", item.get("stem", "")),
            "options": [],
            "answer": "",
            "explanation": item.get("rationale", item.get("explanation", "")),
        }
        # 选项
        opts = item.get("answerOptions", item.get("options", []))
        for opt in opts:
            if isinstance(opt, dict):
                text = opt.get("answer", opt.get("text", ""))
                is_correct = opt.get("isCorrect", opt.get("correct", False))
                q["options"].append({"text": text, "correct": is_correct})
                if is_correct:
                    q["answer"] = text
            else:
                q["options"].append({"text": str(opt), "correct": False})
        questions.append(q)
    return questions


def generate_site(
    curriculum: list = None,
    selected_ids: list[str] | None = None,
    artifact_types: list[str] | None = None,
):
    """生成完整的静态网站"""
    # 若未传入 curriculum，尝试从本地缓存加载
    if curriculum is None:
        try:
            import json as _json
            cfg = _json.loads((Path(__file__).parent.parent / "config.json").read_text("utf-8"))
            book_title = cfg.get("book_title", "")
            if book_title:
                from curriculum.curriculum_generator import _get_cache_file, _validate
                cache = _get_cache_file(book_title)
                if cache.exists():
                    data = _json.loads(cache.read_text("utf-8"))
                    if _validate(data):
                        curriculum = data
        except Exception:
            pass
    if not curriculum:
        print("  [WARN] 未找到课程目录，网页将不含导航结构，请先生成目录")
        curriculum = []

    # 自动探测 progress.json 里有哪些类型已完成，作为默认类型集合
    if artifact_types is None:
        progress_auto = load_progress()
        _all_kinds = ["video", "audio", "slide", "quiz", "flashcard", "report", "infographic", "datatable"]
        auto_detected = [
            k for k in _all_kinds
            if any(
                progress_auto.get("topics", {}).get(tid, {}).get(f"{k}_downloaded")
                for tid in progress_auto.get("topics", {})
            )
        ]
        active_types = auto_detected if auto_detected else _all_kinds
        print(f"  [自动探测] 包含内容类型：{', '.join(active_types)}")
    else:
        active_types = artifact_types

    WEBSITE_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    VIDEOS_SITE_DIR.mkdir(exist_ok=True)
    AUDIOS_SITE_DIR.mkdir(exist_ok=True)
    REPORTS_SITE_DIR.mkdir(exist_ok=True)
    FLASHCARDS_SITE_DIR.mkdir(exist_ok=True)
    SLIDES_SITE_DIR.mkdir(exist_ok=True)

    progress = load_progress()

    # 复制视频文件
    video_src_dir = OUTPUT_DIR / "videos"
    if "video" in active_types and video_src_dir.exists():
        copied = 0
        for mp4 in video_src_dir.glob("*.mp4"):
            dest = VIDEOS_SITE_DIR / mp4.name
            if not dest.exists():
                shutil.copy2(mp4, dest)
                copied += 1
        if copied:
            print(f"  [OK] 复制了 {copied} 个视频文件")

    # 复制音频文件
    audio_src_dir = OUTPUT_DIR / "audios"
    if "audio" in active_types and audio_src_dir.exists():
        copied = 0
        for f in audio_src_dir.glob("*.mp3"):
            dest = AUDIOS_SITE_DIR / f.name
            if not dest.exists():
                shutil.copy2(f, dest)
                copied += 1
        if copied:
            print(f"  [OK] 复制了 {copied} 个音频文件")

    # 复制报告
    report_src_dir = OUTPUT_DIR / "reports"
    if "report" in active_types and report_src_dir.exists():
        for f in report_src_dir.glob("*_report.md"):
            dest = REPORTS_SITE_DIR / f.name
            if not dest.exists():
                shutil.copy2(f, dest)

    # 复制并标准化演示文稿文件名 (Renaming to ID.pdf, slide 或 audio 都需要)
    slide_src_dir = OUTPUT_DIR / "slides"
    if ("slide" in active_types or "audio" in active_types) and slide_src_dir.exists():
        all_pdfs = list(slide_src_dir.glob("*.pdf"))
        copied_slides = 0
        for ch in curriculum:
            for sec in ch["sections"]:
                for tp in sec["topics"]:
                    for pdf in all_pdfs:
                        if pdf.name.startswith(tp["id"]):
                            dest = SLIDES_SITE_DIR / f"{tp['id']}.pdf"
                            shutil.copy2(pdf, dest)
                            copied_slides += 1
                            break
        if copied_slides:
            print(f"  [OK] 复制了 {copied_slides} 个演示文稿文件")

    # 复制并标准化闪卡文件名
    fc_src_dir = OUTPUT_DIR / "flashcards"
    if "flashcard" in active_types and fc_src_dir.exists():
        all_fcs = list(fc_src_dir.glob("*_fc.json"))
        for ch in curriculum:
            for sec in ch["sections"]:
                for tp in sec["topics"]:
                    for fc in all_fcs:
                        if fc.name.startswith(tp["id"]):
                            dest = FLASHCARDS_SITE_DIR / f"{tp['id']}_fc.json"
                            shutil.copy2(fc, dest)
                            break

    # 生成课程数据 JS
    curriculum_data = build_curriculum_json(progress, curriculum, selected_ids, active_types)
    data_file = DATA_DIR / "curriculum.js"
    json_str = json.dumps(curriculum_data, ensure_ascii=False, indent=2)
    data_file.write_text(f"window.CURRICULUM_DATA = {json_str};", encoding="utf-8")
    print(f"  [OK] 课程数据已生成：{data_file}")

    # 生成 CSS / JS / HTML
    _write_css()
    _write_js(active_types)
    _write_html()

    print(f"  [OK] 网站已生成：{WEBSITE_DIR / 'index.html'}")

    # 打包 ZIP
    zip_path = OUTPUT_DIR / "website.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in WEBSITE_DIR.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(WEBSITE_DIR.parent))
    print(f"  [OK] 打包完成：{zip_path}")
    print(f"\n  📦 将 website.zip 拷贝到任意电脑，解压后用浏览器打开 website/index.html 即可使用")


# ─────────────────────────────────────────────────────────────────────────────
# 生成向导（交互选择内容范围）
# ─────────────────────────────────────────────────────────────────────────────

def run_site_wizard(curriculum: list | None, progress: dict):
    """HTML 生成向导：选知识点范围 + 选 Artifact 类型"""
    from pipeline.task_selector import parse_selection, ALL_ARTIFACT_TYPES

    print("\n── 生成 HTML 课程网页 ─────────────────────────────")
    print("  选择要打入网页的知识点范围（all 表示全部）")
    print("  格式：all / ch01 / ch01_s02 / ch01_s02_t01，逗号分隔多个")
    print("  输入 Q 取消返回")

    selected_ids = None
    if curriculum:
        raw = input("\n> ").strip()
        if raw.upper() in ("Q", "B"):
            return
        if raw and raw.lower() != "all":
            selected_ids = parse_selection(raw, curriculum)
            if not selected_ids:
                print("  没有匹配到任何知识点，将包含全部")
                selected_ids = None
            else:
                print(f"  已选中 {len(selected_ids)} 个知识点")
    else:
        print("  （未加载目录，将包含所有知识点）")

    # 选 Artifact 类型
    print("\n  选择在网页中展示哪些内容（数字切换选中，回车确认）")
    site_kinds = [k for k, _ in _SITE_KINDS]
    selected_kinds = {"video", "quiz"}
    while True:
        for idx, (kind, label) in enumerate(_SITE_KINDS, 1):
            mark = "[x]" if kind in selected_kinds else "[ ]"
            has_data = any(
                is_artifact_done(progress, tid, kind)
                for tid in (selected_ids or []) or list(progress.get("topics", {}).keys())
            )
            avail = " ✓有数据" if has_data else ""
            print(f"    {idx}. {mark} {label}{avail}")
        print("    Q. [ ] 取消返回")

        raw = input("\n  输入编号切换选中/取消，或输入 Q 返回，回车确认：").strip()
        if raw.upper() in ("Q", "B"):
            return
        if not raw:
            if not selected_kinds:
                print("  至少选一种！")
                continue
            break
        import re as _re
        for token in _re.split(r"[,\s]+", raw):
            try:
                i = int(token.strip()) - 1
                if 0 <= i < len(_SITE_KINDS):
                    kind = _SITE_KINDS[i][0]
                    if kind in selected_kinds:
                        selected_kinds.discard(kind)
                    else:
                        selected_kinds.add(kind)
            except ValueError:
                pass
        print()

    artifact_types = [k for k, _ in _SITE_KINDS if k in selected_kinds]
    print(f"  将包含：{'  '.join(label for k, label in _SITE_KINDS if k in selected_kinds)}")
    generate_site(curriculum=curriculum, selected_ids=selected_ids, artifact_types=artifact_types)


# ─────────────────────────────────────────────────────────────────────────────
# 静态资源生成
# ─────────────────────────────────────────────────────────────────────────────

def _write_css():
    css = """\
/* ── 全局 ─────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg: #0f1117;
  --surface: #1a1d27;
  --surface2: #252837;
  --border: #2e3248;
  --accent: #6c63ff;
  --accent2: #00d8b4;
  --text: #e2e6ff;
  --muted: #8890b0;
  --correct: #22c55e;
  --wrong: #ef4444;
  --sidebar-w: 300px;
  --header-h: 60px;
}

body {
  font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
  background: var(--bg);
  color: var(--text);
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

/* ── 顶部标题栏 ─────────────────────────────────────────── */
header {
  height: var(--header-h);
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 12px;
  flex-shrink: 0;
}
header h1 { font-size: 18px; font-weight: 700; color: var(--accent); }
header .subtitle { font-size: 13px; color: var(--muted); }

/* ── 主布局 ─────────────────────────────────────────────── */
.main-layout {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* ── 侧边栏 ─────────────────────────────────────────────── */
#sidebar {
  width: var(--sidebar-w);
  background: var(--surface);
  border-right: 1px solid var(--border);
  overflow-y: auto;
  flex-shrink: 0;
}
#sidebar::-webkit-scrollbar { width: 4px; }
#sidebar::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.chapter-item { border-bottom: 1px solid var(--border); }
.chapter-header {
  padding: 12px 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 13px;
  color: var(--text);
  transition: background 0.15s;
}
.chapter-header:hover { background: var(--surface2); }
.chapter-header .arrow { font-size: 10px; transition: transform 0.2s; color: var(--muted); }
.chapter-header.open .arrow { transform: rotate(90deg); }

.section-list { display: none; }
.section-list.open { display: block; }

.section-item { border-top: 1px solid var(--border); }
.section-header {
  padding: 9px 16px 9px 28px;
  font-size: 12px;
  color: var(--muted);
  font-weight: 600;
  background: var(--bg);
}

.topic-item { border-top: 1px solid var(--border); }
.topic-header {
  padding: 9px 16px 9px 28px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text);
  transition: background 0.15s;
}
.topic-header:hover { background: var(--surface2); }
.topic-header .arrow { font-size: 10px; transition: transform 0.2s; color: var(--muted); }
.topic-header.open .arrow { transform: rotate(90deg); }

.resource-list { display: none; }
.resource-list.open { display: block; }

.resource-item {
  padding: 8px 16px 8px 46px;
  cursor: pointer;
  font-size: 12px;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.15s;
  border-left: 3px solid transparent;
}
.resource-item:hover { background: var(--surface2); color: var(--text); }
.resource-item.active {
  color: var(--accent);
  border-left-color: var(--accent);
  background: rgba(108,99,255,0.08);
}
.resource-item .dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--border); flex-shrink: 0;
}

/* ── 内容区 ─────────────────────────────────────────────── */
#content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden; /* 由内部 tab-pane 处理滚动 */
  padding: 24px 32px;
}

.content-placeholder {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; height: 100%; gap: 12px; color: var(--muted);
}
.content-placeholder .icon { font-size: 48px; }
.content-placeholder p { font-size: 15px; }

.topic-title {
  font-size: 22px; font-weight: 700; color: var(--text);
  margin-bottom: 8px; line-height: 1.4;
}
.topic-id { font-size: 12px; color: var(--muted); margin-bottom: 24px; }

/* ── 视频播放器 ─────────────────────────────────────────── */
.video-section { margin-bottom: 36px; }
.section-label {
  font-size: 13px; font-weight: 700; color: var(--accent2);
  text-transform: uppercase; letter-spacing: 1px;
  margin-bottom: 12px;
}
.video-wrapper {
  background: #000;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--border);
  max-width: 860px;
}
.video-wrapper video { width: 100%; display: block; }
.no-video {
  padding: 40px; text-align: center; color: var(--muted);
  background: var(--surface); border-radius: 12px; font-size: 14px;
}

/* ── Quiz ───────────────────────────────────────────────── */
.quiz-section { max-width: 860px; }
.quiz-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 20px;
}
.quiz-stats { font-size: 13px; color: var(--muted); }

.question-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 16px;
  transition: border-color 0.2s;
}
.question-card.correct { border-color: var(--correct); }
.question-card.wrong { border-color: var(--wrong); }

.q-number { font-size: 11px; color: var(--muted); margin-bottom: 8px; font-weight: 700; }
.q-text { font-size: 15px; line-height: 1.6; margin-bottom: 16px; }
.badge {
  display: inline-block; font-size: 10px; padding: 2px 8px;
  border-radius: 4px; font-weight: 700; margin-left: 8px;
  vertical-align: middle;
}
.badge-hard { background: rgba(239,68,68,0.15); color: var(--wrong); }
.badge-easy { background: rgba(34,197,94,0.15); color: var(--correct); }

.options { display: flex; flex-direction: column; gap: 8px; }
.option {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 10px 14px; border-radius: 8px;
  border: 1px solid var(--border);
  cursor: pointer; transition: all 0.15s; font-size: 14px;
}
.option:hover { border-color: var(--accent); background: rgba(108,99,255,0.08); }
.option.selected { border-color: var(--accent); background: rgba(108,99,255,0.1); }
.option.correct-ans { border-color: var(--correct) !important; background: rgba(34,197,94,0.1) !important; }
.option.wrong-ans { border-color: var(--wrong) !important; background: rgba(239,68,68,0.1) !important; }
.option.disabled { cursor: default; }
.opt-letter {
  width: 24px; height: 24px; border-radius: 6px;
  background: var(--surface2); display: flex; align-items: center;
  justify-content: center; font-size: 12px; font-weight: 700;
  flex-shrink: 0; margin-top: 1px;
}

.explanation {
  margin-top: 12px; padding: 10px 14px;
  background: var(--bg); border-radius: 8px;
  font-size: 13px; color: var(--muted); line-height: 1.6;
  display: none;
}
.explanation.visible { display: block; }
.explanation strong { color: var(--text); }

.quiz-result {
  background: var(--surface2); border-radius: 12px;
  padding: 24px; text-align: center; margin-top: 24px;
  display: none;
}
.quiz-result.visible { display: block; }
.score-big { font-size: 48px; font-weight: 900; color: var(--accent); }
.score-label { font-size: 14px; color: var(--muted); margin-top: 4px; }

.btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 9px 20px; border-radius: 8px; font-size: 13px;
  font-weight: 600; cursor: pointer; border: none;
  transition: all 0.15s; font-family: inherit;
}
.btn-primary { background: var(--accent); color: #fff; }
.btn-primary:hover { background: #7c74ff; }
.btn-outline {
  background: transparent; color: var(--text);
  border: 1px solid var(--border);
}
.btn-outline:hover { border-color: var(--accent); color: var(--accent); }

.no-quiz {
  color: var(--muted); font-size: 14px; padding: 32px;
  background: var(--surface); border-radius: 12px; text-align: center;
}

/* ── 响应式 ─────────────────────────────────────────────── */
@media (max-width: 768px) {
  :root { --sidebar-w: 240px; }
  #content { padding: 16px; }
}

/* 选项卡样式已移除，改为侧边栏资源列表 */

/* 窗口化容器 (Iframe Container) */
.window-frame {
  width: 100%;
  height: 100%;
  border: none;
  background: #fff;
  border-radius: 8px;
}

/* 报告显示 (Markdown) */
.report-markdown {
  max-width: 900px;
  margin: 0 auto;
  line-height: 1.8;
  font-size: 15px;
  color: var(--text);
}
.report-markdown h1, .report-markdown h2, .report-markdown h3 {
  margin: 1.5em 0 0.8em;
  color: var(--accent);
}
.report-markdown p { margin-bottom: 1.2em; }
.report-markdown code {
  background: var(--surface2);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: monospace;
}

/* 折叠控制 */
.toggle-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
}
.toggle-icon { transition: transform 0.3s; color: var(--muted); }
.collapsed .toggle-box { display: none !important; }
.collapsed .toggle-icon { transform: rotate(-90deg); }
"""
    (ASSETS_DIR / "style.css").write_text(css, encoding="utf-8")


def _write_js(active_types: list[str] | None = None):
    if active_types is None:
        active_types = ["video", "quiz"]
    show_audio     = "audio" in active_types
    show_quiz      = "quiz" in active_types
    show_flashcard = "flashcard" in active_types
    show_report    = "report" in active_types
    show_slide     = "slide" in active_types
    # 用于注入到 JS 的布尔变量
    js_flags = f"""
const SHOW_AUDIO = {str(show_audio).lower()};
const SHOW_QUIZ = {str(show_quiz).lower()};
const SHOW_FLASHCARD = {str(show_flashcard).lower()};
const SHOW_REPORT = {str(show_report).lower()};
const SHOW_SLIDE = {str(show_slide).lower()};
"""
    js = """\
/* ── 状态 ────────────────────────────────────────────── */
let curriculum = [];
let currentTopic = null;
let answeredMap = {};   // topicId -> {qIdx -> selectedOptIdx}
let finishedMap = {};   // topicId -> bool

/* ── 初始化 ────────────────────────────────────────────── */
function init() {
  if (window.CURRICULUM_DATA && window.CURRICULUM_DATA.length > 0) {
    curriculum = window.CURRICULUM_DATA;
    buildSidebar(curriculum);
  } else {
    document.getElementById('sidebar').innerHTML =
      '<p style="padding:20px;color:#888">课程数据为空或加载失败，请确认 data/curriculum.js 已生成。</p>';
  }
}

/* ── 侧边栏 ───────────────────────────────────────────── */
function buildSidebar(data) {
  const sb = document.getElementById('sidebar');
  sb.innerHTML = '';
  data.forEach((ch, ci) => {
    const chDiv = document.createElement('div');
    chDiv.className = 'chapter-item';
    const chHead = document.createElement('div');
    chHead.className = 'chapter-header';
    chHead.innerHTML = `<span class="arrow">▶</span>${ch.title}`;
    chHead.onclick = () => {
      chHead.classList.toggle('open');
      secList.classList.toggle('open');
    };
    const secList = document.createElement('div');
    secList.className = 'section-list';

    ch.sections.forEach(sec => {
      const secDiv = document.createElement('div');
      secDiv.className = 'section-item';
      const secHead = document.createElement('div');
      secHead.className = 'section-header';
      secHead.textContent = sec.title;
      secDiv.appendChild(secHead);

      sec.topics.forEach(tp => {
        const tpDiv = document.createElement('div');
        tpDiv.className = 'topic-item';
        
        const tpHead = document.createElement('div');
        tpHead.className = 'topic-header';
        tpHead.innerHTML = `<span class="arrow">▶</span>${tp.title}`;
        
        const resList = document.createElement('div');
        resList.className = 'resource-list';

        tpHead.onclick = (e) => {
          e.stopPropagation();
          tpHead.classList.toggle('open');
          resList.classList.toggle('open');
        };

        // 构建资源列表
        let resources = [];
        if (tp.video) resources.push({ id: 'video', label: '📹 讲解视频', render: renderVideo });
        if ((SHOW_AUDIO && tp.audio) || (SHOW_SLIDE && tp.slide)) {
          resources.push({ id: 'media', label: '📽️ 媒体演示', render: renderMedia });
        }
        if (SHOW_REPORT && typeof renderInfographic !== 'undefined' && tp.infographic) resources.push({ id: 'info', label: '🪧 知识图谱', render: renderInfographic });
        if (SHOW_REPORT && typeof renderDatatable !== 'undefined' && tp.datatable) resources.push({ id: 'data', label: '📊 数据表格', render: renderDatatable });
        if (SHOW_REPORT && tp.report) resources.push({ id: 'report', label: '📄 深度报告', render: renderReport });
        if (tp.quiz && tp.quiz.length) resources.push({ id: 'quiz', label: '✏️ 互动测试', render: renderQuiz });
        if (tp.flashcards && tp.flashcards.length) resources.push({ id: 'fc', label: '🃏 记忆闪卡', render: renderFlashcards });

        resources.forEach(res => {
          const resDiv = document.createElement('div');
          resDiv.className = 'resource-item';
          resDiv.dataset.tid = tp.id;
          resDiv.dataset.rid = res.id;
          resDiv.innerHTML = `<span class="dot"></span>${res.label}`;
          resDiv.onclick = (e) => {
            e.stopPropagation();
            showResource(tp, res);
          };
          resList.appendChild(resDiv);
        });

        tpDiv.appendChild(tpHead);
        tpDiv.appendChild(resList);
        secDiv.appendChild(tpDiv);
      });
      secList.appendChild(secDiv);
    });

    chDiv.appendChild(chHead);
    chDiv.appendChild(secList);
    sb.appendChild(chDiv);
  });
}

/* ── 显示资源 ───────────────────────────────────────── */
function showResource(tp, res) {
  document.querySelectorAll('.resource-item').forEach(el => el.classList.remove('active'));
  const el = document.querySelector(`.resource-item[data-tid="${tp.id}"][data-rid="${res.id}"]`);
  if (el) el.classList.add('active');

  currentTopic = tp;
  if (!answeredMap[tp.id]) answeredMap[tp.id] = {};

  const content = document.getElementById('content');
  
  let contentHtml = res.render(tp);

  content.innerHTML = `
    <div class="topic-title">${tp.title} - ${res.label.split(' ')[1] || res.label}</div>
    <div class="topic-id">${tp.id}</div>
    <div class="full-page-content" style="flex:1; overflow-y:auto; overflow-x:hidden; padding-bottom: 20px; display: flex; flex-direction: column;">
      ${contentHtml}
    </div>
  `;
  
  // 渲染完成后，触发 MathJax 重新解析当前区域的公式
  if (window.MathJax && MathJax.typesetPromise) {
    MathJax.typesetPromise([content]).catch(err => console.log('MathJax err', err));
  }
}

function toggleCollapse(el) {
  el.parentElement.classList.toggle('collapsed');
}


/* ── 各组件渲染函数 ─────────────────────────────────────────── */

function renderVideo(tp) {
  if (!tp.video) return '';
  return `<div class="video-section" style="height:100%;">
    <div class="video-wrapper" style="max-width:none; height:calc(100% - 30px);">
      <video controls style="height:100%; background:#000;">
        <source src="${tp.video}" type="video/mp4">
        您的浏览器不支持视频播放
      </video>
    </div>
  </div>`;
}

function renderMedia(tp) {
  // 计算内容区可用高度
  let html = `<div style="flex:1; display:flex; flex-direction:column; gap:12px; min-height:0; height:100%;">`;
  
  // 如果有音频，显示在顶部（固定高度）
  if (tp.audio) {
    html += `
    <div style="background:var(--surface); border-radius:12px; padding:14px 20px; border:1px solid var(--border); display:flex; align-items:center; gap:15px; flex-shrink:0;">
      <div style="font-size:22px;">🎙️</div>
      <div style="flex:1;">
        <div style="font-size:12px; color:var(--muted); margin-bottom:6px;">演示文稿解说音频 · 边看文稿边听</div>
        <audio controls style="width:100%; height:36px;">
          <source src="${tp.audio}" type="audio/mpeg">
          您的浏览器不支持音频播放
        </audio>
      </div>
    </div>`;
  }
  
  // 如果有幻灯片，显示在下方
  if (tp.slide) {
    html += `
    <div style="flex:1; min-height:300px; background:var(--surface); border-radius:12px; border:1px solid var(--border); display:flex; flex-direction:column; overflow:hidden;">
      <div style="background:var(--surface2); padding:10px 16px; display:flex; align-items:center; justify-content:space-between; border-bottom:1px solid var(--border); flex-shrink:0;">
        <span style="font-size:13px; font-weight:600; color:var(--text);">📄 演示文稿 · PDF</span>
        <a href="${tp.slide}" download class="btn btn-outline" style="font-size:11px; padding:4px 12px;">📥 下载</a>
      </div>
      <div style="flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:24px; padding:40px;">
        <div style="font-size:72px; line-height:1;">📑</div>
        <div style="text-align:center;">
          <div style="font-size:16px; font-weight:600; color:var(--text); margin-bottom:8px;">配合音频一起学习的演示文稿</div>
          <div style="font-size:13px; color:var(--muted); margin-bottom:24px;">点击下方按钮，用系统默认程序（Edge / PDF 阅读器）打开</div>
          <a href="${tp.slide}" target="_blank"
             style="display:inline-flex; align-items:center; gap:10px; padding:14px 32px;
                    background:var(--accent); color:#fff; border-radius:10px;
                    font-size:15px; font-weight:700; text-decoration:none;
                    box-shadow:0 4px 20px rgba(108,99,255,0.4);
                    transition:all 0.2s;">
            🔗&nbsp; 打开演示文稿 PDF
          </a>
        </div>
        <div style="font-size:12px; color:var(--muted); text-align:center; max-width:360px; line-height:1.6;">
          💡 建议将 PDF 窗口和本页面并排显示，一边翻阅幻灯片，一边播放上方解说音频
        </div>
      </div>
    </div>`;
  } else if (tp.audio) {
    // 只有音频时占位
    html += `<div style="flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; color:var(--muted); border:2px dashed var(--border); border-radius:12px;">
      <div style="font-size:48px; margin-bottom:10px;">📻</div>
      <p>知识音频播放中，建议配合左侧报告或测试一起学习</p>
    </div>`;
  }
  
  html += `</div>`;
  return html;
}

function renderReport(tp) {
  if (!tp.report) return '';
  let markdownHtml = tp.report_content ? marked.parse(tp.report_content) : '报告内容加载中...';
  return `<div class="video-section">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
      <b>📄 深度学习报告</b>
      <a href="${tp.report}" download class="btn btn-outline" style="font-size:12px;">下载原始版式</a>
    </div>
    <div class="report-markdown" style="background:var(--surface); padding: 40px; border-radius:12px; border:1px solid var(--border); box-shadow: 0 10px 30px rgba(0,0,0,0.1);">
      ${markdownHtml}
    </div>
  </div>`;
}

function renderInfographic(tp) {
  if (!tp.infographic) return '';
  return `<div style="text-align:center; height:100%; padding:20px;">
    <img src="${tp.infographic}" style="max-width:100%; max-height:100%; border-radius:8px; box-shadow:0 4px 20px rgba(0,0,0,0.3);" alt="信息图">
  </div>`;
}

function renderDatatable(tp) {
  if (!tp.datatable) return '';
  return `<div class="video-section" style="text-align:center; padding:50px;">
    <div style="font-size:48px; margin-bottom:20px;">📊</div>
    <h3>数据分析表格</h3>
    <p style="color:var(--muted); margin:15px 0 30px;">完整的数据对比表已准备就绪，支持 CSV 格式导出。</p>
    <a href="${tp.datatable}" download class="btn btn-primary">📥 立即下载数据表格</a>
  </div>`;
}



/* ── 闪卡区 ───────────────────────────────────────────── */
function renderFlashcards(tp) {
  if (!tp.flashcards || !tp.flashcards.length) {
    return `<div class="quiz-section">
      <div class="section-label">🃏 闪卡记忆</div>
      <div class="no-quiz">该知识点的闪卡尚未生成</div>
    </div>`;
  }
  const cards = tp.flashcards;
  let cardsHtml = cards.map((c, i) => `
    <div class="question-card" id="fc-${i}">
      <div class="q-number" style="margin-bottom:8px; font-weight:bold;">闪卡 ${i + 1} / ${cards.length}</div>
      <div style="cursor:pointer;" onclick="flipCard(${i})">
        <div style="font-size:12px; color:var(--muted); margin-bottom:8px;">💡 点击卡片查看背面答案</div>
        <div class="q-text" id="fc-front-${i}">${c.front || c.f || ''}</div>
        <div class="explanation" id="fc-back-${i}"><strong>答：</strong>${c.back || c.b || ''}</div>
      </div>
    </div>`).join('');
  return `<div class="quiz-section">
    <div class="section-label">🃏 闪卡记忆（共 ${cards.length} 张）</div>
    ${cardsHtml}
  </div>`;
}


function renderQuiz(tp) {
  if (!tp.quiz || !tp.quiz.length) {
    return `<div class="quiz-section">
      <div class="section-label">📝 测试题</div>
      <div class="no-quiz">该知识点的测试题尚未生成</div>
    </div>`;
  }
  const answered = answeredMap[tp.id] || {};
  const totalQ = tp.quiz.length;
  const totalBasic = Math.min(10, totalQ);
  const totalAdv = totalQ - totalBasic;

  let cardsHtml = tp.quiz.map((q, qi) => {
    const letters = ['A','B','C','D','E','F'];
    const isAdv = qi >= 10;
    const badgeHtml = isAdv
      ? '<span class="badge badge-hard">拔高</span>'
      : '<span class="badge badge-easy">巩固</span>';

    const hasOptions = q.options && q.options.length > 0;
    const optsHtml = hasOptions ? (q.options).map((opt, oi) => {
      let cls = 'option';
      const sel = answered[qi];
      const disabled = sel !== undefined ? 'disabled' : '';
      if (sel !== undefined) {
        cls += ' disabled';
        if (opt.correct) cls += ' correct-ans';
        else if (sel === oi && !opt.correct) cls += ' wrong-ans';
      }
      const clickFn = sel !== undefined ? '' : `onclick="selectOption(${qi},${oi})"`;
      return `<div class="${cls}" ${clickFn}>
        <div class="opt-letter">${letters[oi]}</div>${opt.text}
      </div>`;
    }).join('') : `<div style="padding:10px; color:var(--muted); font-style:italic;">（本题无选项，请自由回答后展开查看解析）</div>`;

    const expVisible = (answered[qi] !== undefined || !hasOptions) ? 'visible' : '';
    const cardCls = answered[qi] !== undefined
      ? ((q.options[answered[qi]]?.correct) ? 'correct' : 'wrong')
      : '';

    const correctIdx = q.options ? q.options.findIndex(o => o.correct) : -1;
    const correctLabel = correctIdx !== -1 ? letters[correctIdx] : '';
    const questionExp = q.explanation ? q.explanation : (q.answer ? '正确答案是：' + correctLabel + ' ' + q.answer : '（暂无解析）');
    return `<div class="question-card ${cardCls}" id="q-${qi}">
      <div class="q-number" style="margin-bottom:8px; font-weight:bold;">第 ${qi+1} 题 ${badgeHtml}</div>
      <div class="q-text">${q.question}</div>
      <div class="options">${optsHtml}</div>
      <div class="explanation ${expVisible}" id="exp-${qi}" style="margin-top:10px;">
        <strong>解析/答案：</strong>${questionExp}
      </div>
    </div>`;
  }).join('');

  const answered_count = Object.keys(answered).length;
  const correct_count = Object.keys(answered).filter(qi => {
    const q = tp.quiz[parseInt(qi)];
    const oi = answered[qi];
    return q?.options?.[oi]?.correct;
  }).length;

  const resultHtml = finishedMap[tp.id]
    ? `<div class="quiz-result visible" id="quiz-result">
        <div class="score-big">${correct_count} / ${totalQ}</div>
        <div class="score-label">答题完成！</div>
      </div>`
    : `<div class="quiz-result" id="quiz-result"></div>`;

  return `<div class="quiz-section">
    <div class="section-label">📝 测试题（共 ${totalQ} 题：${totalBasic} 道巩固 + ${totalAdv > 0 ? totalAdv + ' 道拔高' : ''}）</div>
    <div class="quiz-header">
      <div class="quiz-stats">已答 ${answered_count}/${totalQ} 题</div>
      <button class="btn btn-outline" onclick="resetQuiz()">重置答题</button>
    </div>
    ${cardsHtml}
    ${resultHtml}
  </div>`;
}

/* ── 选择答案 ─────────────────────────────────────────── */
function selectOption(qi, oi) {
  if (!currentTopic) return;
  const tp = currentTopic;
  answeredMap[tp.id][qi] = oi;

  const q = tp.quiz[qi];
  const isCorrect = q.options[oi]?.correct;

  // 更新卡片样式
  const card = document.getElementById(`q-${qi}`);
  card.classList.remove('correct','wrong');
  card.classList.add(isCorrect ? 'correct' : 'wrong');

  // 更新选项样式
  const opts = card.querySelectorAll('.option');
  opts.forEach((el, idx) => {
    el.classList.add('disabled');
    el.onclick = null;
    if (q.options[idx]?.correct) el.classList.add('correct-ans');
    else if (idx === oi && !q.options[idx]?.correct) el.classList.add('wrong-ans');
  });

  // 显示解析
  const exp = document.getElementById(`exp-${qi}`);
  if (exp) exp.classList.add('visible');

  // 更新已答统计
  updateStats(tp);

  // 检查全部完成
  const totalQ = tp.quiz.length;
  if (Object.keys(answeredMap[tp.id]).length === totalQ) {
    finishedMap[tp.id] = true;
    showResult(tp);
  }
}

function updateStats(tp) {
  const answered = answeredMap[tp.id] || {};
  const el = document.querySelector('.quiz-stats');
  if (el) el.textContent = `已答 ${Object.keys(answered).length}/${tp.quiz.length} 题`;
}

function showResult(tp) {
  const answered = answeredMap[tp.id] || {};
  const correct = Object.keys(answered).filter(qi => {
    const q = tp.quiz[parseInt(qi)];
    return q?.options?.[answered[qi]]?.correct;
  }).length;
  const total = tp.quiz.length;
  const result = document.getElementById('quiz-result');
  if (result) {
    result.innerHTML = `<div class="score-big">${correct} / ${total}</div>
      <div class="score-label">答题完成！共答对 ${correct} 题</div>`;
    result.classList.add('visible');
    result.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

function resetQuiz() {
  if (!currentTopic) return;
  delete answeredMap[currentTopic.id];
  delete finishedMap[currentTopic.id];
  showTopic(currentTopic);
}

/* ── 闪卡翻转 ───────────────────────────────────────────── */
function flipCard(idx) {
  const back = document.getElementById('fc-back-' + idx);
  if (back) back.classList.toggle('visible');
}

window.selectOption = selectOption;
window.resetQuiz = resetQuiz;
window.flipCard = flipCard;
window.toggleCollapse = toggleCollapse;
document.addEventListener('DOMContentLoaded', init);
"""
    full_js = js_flags + js
    (ASSETS_DIR / "app_v3.js").write_text(full_js, encoding="utf-8")


def _write_html():
    html = """\
<!DOCTYPE html>
<html lang="zh-Hans">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>《什么是数学》— 知识点讲解与练习</title>
  <meta name="description" content="基于 NotebookLM 生成的《什么是数学》视频讲解与互动测试题，支持单机离线使用">
  <link rel="stylesheet" href="assets/style.css">
  
  <!-- 引入 MathJax 处理数学公式渲染 -->
  <script>
    MathJax = {
      tex: {
        inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
        displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']]
      },
      svg: {
        fontCache: 'global'
      },
      startup: {
        typeset: false
      }
    };
  </script>
  <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
  <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
</head>
<body>
  <header>
    <h1>📐 什么是数学</h1>
    <span class="subtitle">—— 视频讲解 · 互动测试 · 离线可用</span>
  </header>
  <div class="main-layout">
    <nav id="sidebar" aria-label="课程目录"></nav>
    <main id="content">
      <div class="content-placeholder">
        <div class="icon">📚</div>
        <p>从左侧目录选择一个知识点开始学习</p>
      </div>
    </main>
  </div>
  <script src="data/curriculum.js"></script>
  <script src="assets/app_v3.js"></script>
</body>
</html>
"""
    (WEBSITE_DIR / "index.html").write_text(html, encoding="utf-8")
