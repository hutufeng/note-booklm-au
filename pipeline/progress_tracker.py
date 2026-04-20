"""进度跟踪器：管理 progress.json 断点续传（支持所有 Artifact 类型）"""

import json
from pathlib import Path

PROGRESS_FILE = Path(__file__).parent.parent / "progress.json"

# 所有支持的 Artifact 类型及其本地目录 / 扩展名
ARTIFACT_KINDS = {
    "video":     {"dir": "videos",    "ext": ".mp4"},
    "audio":     {"dir": "audios",    "ext": ".mp3"},
    "quiz":      {"dir": "quizzes",   "ext": "_quiz.json"},
    "flashcard": {"dir": "flashcards","ext": "_fc.json"},
    "report":    {"dir": "reports",   "ext": "_report.md"},
    "slide":     {"dir": "slides",    "ext": ".pdf"},
    "infographic":{"dir":"infographics","ext": ".png"},
    "datatable": {"dir": "datatables","ext": ".csv"},
}

OUTPUT_DIR = Path(__file__).parent.parent / "output"


# ─────────────────────────────────────────────────────────────────────────────
# 读 / 写
# ─────────────────────────────────────────────────────────────────────────────

def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"topics": {}}


def save_progress(progress: dict):
    PROGRESS_FILE.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 泛化接口（所有类型统一）
# ─────────────────────────────────────────────────────────────────────────────

def get_topic_status(progress: dict, topic_id: str) -> dict:
    return progress.get("topics", {}).get(topic_id, {})


def mark_artifact_generated(progress: dict, topic_id: str, kind: str, artifact_id: str):
    """记录已提交到 NotebookLM 的任务 ID（等待下载阶段）"""
    progress.setdefault("topics", {}).setdefault(topic_id, {})[f"{kind}_artifact_id"] = artifact_id
    save_progress(progress)


def mark_artifact_downloaded(progress: dict, topic_id: str, kind: str, path: str):
    """记录已下载到本地文件的状态"""
    st = progress.setdefault("topics", {}).setdefault(topic_id, {})
    st[f"{kind}_downloaded"] = True
    st[f"{kind}_path"] = path
    save_progress(progress)


def is_artifact_done(progress: dict, topic_id: str, kind: str) -> bool:
    return get_topic_status(progress, topic_id).get(f"{kind}_downloaded", False)


def get_artifact_id(progress: dict, topic_id: str, kind: str) -> str | None:
    """获取云端 Artifact ID（用于定向删除）"""
    return get_topic_status(progress, topic_id).get(f"{kind}_artifact_id")


def get_artifact_path(progress: dict, topic_id: str, kind: str) -> str | None:
    """获取本地文件路径"""
    return get_topic_status(progress, topic_id).get(f"{kind}_path")


# ─────────────────────────────────────────────────────────────────────────────
# 向后兼容别名（旧代码不用改）
# ─────────────────────────────────────────────────────────────────────────────

def mark_video_generated(progress, topic_id, artifact_id):
    mark_artifact_generated(progress, topic_id, "video", artifact_id)

def mark_video_downloaded(progress, topic_id, path):
    mark_artifact_downloaded(progress, topic_id, "video", path)

def mark_quiz_generated(progress, topic_id, artifact_id):
    mark_artifact_generated(progress, topic_id, "quiz", artifact_id)

def mark_quiz_downloaded(progress, topic_id, path):
    mark_artifact_downloaded(progress, topic_id, "quiz", path)

def is_video_done(progress, topic_id):
    return is_artifact_done(progress, topic_id, "video")

def is_quiz_done(progress, topic_id):
    return is_artifact_done(progress, topic_id, "quiz")

def is_topic_fully_done(progress: dict, topic_id: str) -> bool:
    """旧版兼容：仅视频+Quiz 都完成才算完整"""
    s = get_topic_status(progress, topic_id)
    return s.get("video_downloaded", False) and s.get("quiz_downloaded", False)


# ─────────────────────────────────────────────────────────────────────────────
# 删除操作
# ─────────────────────────────────────────────────────────────────────────────

def clear_topic_progress(progress: dict, topic_id: str, kinds: list[str] | None = None):
    """
    清除 progress.json 中某知识点的记录。
    kinds=None 时清除全部类型；否则只清除指定类型。
    """
    topics = progress.get("topics", {})
    if topic_id not in topics:
        return
    if kinds is None:
        del topics[topic_id]
    else:
        st = topics[topic_id]
        for kind in kinds:
            for suffix in ("_artifact_id", "_downloaded", "_path"):
                st.pop(f"{kind}{suffix}", None)
        if not st:
            del topics[topic_id]
    save_progress(progress)


def mark_artifact_failed(progress: dict, topic_id: str, kind: str):
    """
    将失败的 artifact 从 progress.json 中清除，
    这样下次运行时会自动重新提交该任务。
    """
    st = progress.get("topics", {}).get(topic_id, {})
    st.pop(f"{kind}_artifact_id", None)
    st.pop(f"{kind}_downloaded",  None)
    st.pop(f"{kind}_path",        None)
    save_progress(progress)


def delete_local_files(progress: dict, topic_id: str, kinds: list[str] | None = None) -> list[str]:
    """
    删除本地文件。返回被删除的文件路径列表。
    调用前须先 clear_topic_progress 或单独使用。
    """
    deleted = []
    st = get_topic_status(progress, topic_id)
    target_kinds = kinds or list(ARTIFACT_KINDS.keys())
    for kind in target_kinds:
        path_str = st.get(f"{kind}_path")
        if path_str:
            p = Path(path_str)
            if p.exists():
                p.unlink()
                deleted.append(str(p))
    return deleted


def get_all_artifact_ids(progress: dict, topic_id: str, kinds: list[str] | None = None) -> dict[str, str]:
    """返回 {kind: artifact_id} 用于云端删除"""
    st = get_topic_status(progress, topic_id)
    target_kinds = kinds or list(ARTIFACT_KINDS.keys())
    result = {}
    for kind in target_kinds:
        aid = st.get(f"{kind}_artifact_id")
        if aid:
            result[kind] = aid
    return result
