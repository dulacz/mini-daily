# -*- coding: UTF-8 -*-
"""
S1 Newsfeed module - pulls latest top posts from S1,
and uses GitHub Models API to summarize each thread's content.
"""

import re
import json
import subprocess
import threading
import time
import os
from pathlib import Path
from datetime import datetime, timedelta, date, timezone
from collections import Counter
from typing import Optional

try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# ---------------------------------------------------------------------------
# Configuration — override via environment variables
# ---------------------------------------------------------------------------
S1_REPO_PATH = Path(os.environ.get("S1_REPO_PATH", "../S1PlainTextBackup"))
NEWSFEED_DATA_PATH = Path("data/newsfeed")
GITHUB_TOKEN_FILE = Path("data/github_token.txt")
SECTION = "外野"
TOP_N = 20
# Max characters of a thread file sent to LLM to avoid token limits
MAX_CONTENT_CHARS = 60000  # default for large-context models (gpt-4o etc.)

# Per-model (max_content_chars, max_completion_tokens, request_delay_secs)
# Rate limits from GitHub Models free tier docs (Copilot Pro):
#   Low tier  (Llama, Mistral, Jamba): 15 RPM  → ~4s gap
#   High tier (gpt-4o, gpt-4o-mini):   10 RPM  → ~7s gap
#   DeepSeek-V3-0324:                   2 RPM   → 35s gap (confirmed by 429 error)
_MODEL_LIMITS: dict[str, tuple[int, int, int]] = {
    "DeepSeek-V3-0324": (5000, 500, 35),  # 2 RPM free tier
    "gpt-4o": (60000, 1200, 4),  # 15 RPM low tier
    "gpt-4o-mini": (60000, 1200, 4),  # 15 RPM low tier
    "llama": (30000, 1200, 4),  # 15 RPM low tier
    "mistral": (30000, 1200, 4),  # 15 RPM low tier
    "jamba": (30000, 1200, 4),  # 15 RPM low tier
    "grok": (3000, 800, 7),  # 4000 token input cap (grok-3, grok-2, etc.)
}


def _get_model_limits(model: str) -> tuple[int, int, int]:
    """Return (max_content_chars, max_completion_tokens, request_delay_secs) for the given model."""
    model_lower = model.lower()
    for key, limits in _MODEL_LIMITS.items():
        if key in model_lower:
            return limits
    return (20000, 1200, 7)  # safe fallback: assume high-tier rate limit


def _clean_md_content(raw: str) -> str:
    """
    Strip noise from a raw S1 forum .md cache before sending to the LLM.
    Goal: keep only readable post body text; discard all metadata, markup and UI chrome.
    """
    # 1. Strip all HTML tags
    raw = re.sub(r"<[^>]+>", "", raw)
    # 2. Remove leftover inline CSS blocks (#pidXXX{...})
    raw = re.sub(r"#pid\w+\{[^}]*\}", "", raw)
    # 3. Remove all http/https URLs (plain or markdown-linked)
    raw = re.sub(r"\[?https?://\S+\]?(?:\([^\)]*\))?", "", raw)
    # 4. Remove image / attachment metadata lines
    #    e.g. "1.png (37.72 KB, 下载次数: 0)" / "下载附件" / "2026-3-5 19:53 上传"
    raw = re.sub(r"\S+\.(jpg|jpeg|png|gif|webp|mp4|mov)\s*\([^)]*\)", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"^下载附件\s*$", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"^\d{4}-\d{1,2}-\d{1,2}\s+\d{2}:\d{2}\s+上传\s*$", "", raw, flags=re.MULTILINE)
    # 5. Remove any line containing 发表于 (post headers, attribution lines, timestamps)
    raw = re.sub(r"^[^\n]*发表于[^\n]*$", "", raw, flags=re.MULTILINE)
    # 6. Remove edit notices: "本帖最后由 X 于 2026-3-5 19:54 编辑"
    raw = re.sub(r"本帖最后由.{1,30}编辑", "", raw)
    # 7. Remove mobile-app tail signatures and device/Android identifier remnants
    #    e.g. "—— 来自 Xiaomi 23113RKC6C" / "2210132C, Android 16上的 [S1Next-鹅版] v2.2.2.1"
    raw = re.sub(
        r"——\s*[来來]自\s*\S+|" r"— from \[S1 Next Goose\][^\n]*|" r"https://s1fun\.koalcat\.com",
        "",
        raw,
    )
    # Remove leftover device model + Android/iPhone signature lines
    raw = re.sub(r"^[^\n]*(Android|iPhone)[^\n]*$", "", raw, flags=re.MULTILINE)
    # 8. Remove bare date strings (YYYY-M-D or YYYY-MM-DD)
    raw = re.sub(r"\d{4}-\d{1,2}-\d{1,2}", "", raw)
    # 9. Drop any line whose first non-whitespace character is # * = < >
    raw = re.sub(r"^[ \t]*[#*=<>][^\n]*$", "", raw, flags=re.MULTILINE)
    # 10. Collapse 3+ consecutive blank lines into two
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


# ---------------------------------------------------------------------------
# Token loading
# ---------------------------------------------------------------------------


def _load_github_token() -> str:
    """
    Load GitHub token from data/github_token.txt.
    Falls back to GITHUB_TOKEN environment variable if the file is missing
    or still contains the placeholder text.
    """
    try:
        text = GITHUB_TOKEN_FILE.read_text(encoding="utf-8").strip()
        if text and not text.startswith("paste_your"):
            return text
    except Exception:
        pass
    return os.environ.get("GITHUB_TOKEN", "")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_date_str(days_ago: int = 1) -> str:
    """Return a date string N days ago in YYYY-MM-DD format."""
    target = datetime.today() - timedelta(days=days_ago)
    return target.strftime("%Y-%m-%d")


def _utc_now() -> datetime:
    """Return the current UTC-aware datetime."""
    return datetime.now(timezone.utc)


def _utc_now_filename() -> str:
    """Return a filesystem-safe UTC datetime string suitable for cache filenames."""
    return _utc_now().strftime("%Y-%m-%dT%H-%M-%SZ")


def _extract_title_from_path(path: Path) -> str:
    """
    Extract thread title from filenames. Returns the part inside brackets, or the stem if not found.
    """
    # Try the parent directory name first (subdirectory threads)
    for part in [path.parent.name, path.stem, path.name]:
        m = re.search(r"\[(.+)\]", part)
        if m:
            return m.group(1)
    return path.stem


def _extract_thread_id(path: Path) -> Optional[str]:
    """Extract the 5-9 digit thread ID from the file path."""
    matches = re.findall(r"\d{5,9}", str(path))
    return matches[0] if matches else None


# ---------------------------------------------------------------------------
# Git pull
# ---------------------------------------------------------------------------


def git_pull() -> dict:
    """
    Run `git pull` inside S1_REPO_PATH.
    Returns dict with success flag and output message.
    """
    try:
        result = subprocess.run(
            ["git", "pull"],
            cwd=str(S1_REPO_PATH),
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout.strip() or result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "git pull timed out after 60s"}
    except Exception as e:
        return {"success": False, "output": str(e)}


# ---------------------------------------------------------------------------
# Top posts ranking
# ---------------------------------------------------------------------------


def get_top_posts(n: int = TOP_N, days_ago: int = 1) -> list:
    """
    Scan and return the top N threads
    ranked by reply count on the target date.

    Each entry: {thread_id, title, file_path, reply_count, url}
    """
    target_date = _get_date_str(days_ago)  # YYYY-MM-DD — used for filenames/JSON
    # Forum files store dates without leading zeros (e.g. 2026-3-4); build that form for matching
    dt = datetime.today() - timedelta(days=days_ago)
    content_date = f"{dt.year}-{dt.month}-{dt.day}"  # no leading zeros

    section_path = S1_REPO_PATH / SECTION

    if not section_path.exists():
        return []

    thread_counts: dict[str, int] = {}
    thread_files: dict[str, Path] = {}
    thread_titles: dict[str, str] = {}

    for md_file in section_path.rglob("*.md"):
        thread_id = _extract_thread_id(md_file)
        if not thread_id:
            continue

        try:
            content = md_file.read_text(encoding="utf-8-sig")
        except Exception:
            continue

        if content_date not in content:
            continue

        # Count posts made on target_date
        date_matches = re.findall(r"发表于\s(\d{4}-\d{1,2}-\d{1,2}) \d{2}:\d{2}", content)
        count_today = sum(1 for d in date_matches if d == content_date)

        if count_today > 0:
            # Accumulate (a thread may span multiple pages / files)
            thread_counts[thread_id] = thread_counts.get(thread_id, 0) + count_today
            # Keep the LATEST page file for summarisation (highest page number = largest filename)
            if thread_id not in thread_files or md_file > thread_files[thread_id]:
                thread_files[thread_id] = md_file
            if thread_id not in thread_titles:
                thread_titles[thread_id] = _extract_title_from_path(md_file)

    # Sort and take top N
    ranked = sorted(thread_counts.items(), key=lambda x: x[1], reverse=True)[:n]

    result = []
    for tid, count in ranked:
        result.append(
            {
                "thread_id": tid,
                "title": thread_titles.get(tid, tid),
                "file_path": str(thread_files.get(tid, "")),
                "reply_count": count,
                "url": f"https://stage1st.com/2b/thread-{tid}-1-1.html",
            }
        )
    return result


# ---------------------------------------------------------------------------
# LLM summarisation via GitHub Models API
# ---------------------------------------------------------------------------


def summarize_post(file_path: str, github_token: str, model: str) -> str:
    """
    Read the .md file and call GitHub Models API to produce a summary.
    Returns the summary string, or an error message.
    """
    if not OPENAI_AVAILABLE:
        return "openai package not installed — run: pip install openai"

    if not github_token:
        return "GitHub token not set — edit data/github_token.txt or set GITHUB_TOKEN env var"

    max_content_chars, max_completion_tokens, _ = _get_model_limits(model)

    try:
        raw = Path(file_path).read_text(encoding="utf-8-sig")
        content = _clean_md_content(raw)
        # Truncate only after cleaning (cleaned text is much shorter)
        if len(content) > max_content_chars:
            content = content[:max_content_chars] + "\n\n[内容过长，已截断]"
    except Exception as e:
        return f"无法读取文件: {e}"

    client = OpenAI(
        base_url="https://models.inference.ai.azure.com",
        api_key=github_token,
    )
    prompt = (
        "这是很多网友的评论集合，请按照以下格式输出，不要偏离格式：\n\n"
        "### 新闻解读\n"
        "（将新闻事件按bulletpoint拆分，尽可能详细的说明）\n"
        "### 网友评论综合\n"
        "（综合网友观点，假装你是一名网友发表评论，按bulletpoint拆分。"
        '你作为一名网友评论的时候，不要用"网友认为"或类似表达，而是直接说话，复述其评论）\n\n'
        "格式例子：### 新闻解读\n- ...\n- ...\n### 网友评论综合\n- “...”\n- “...”\n\n"
        "在每个bulletpoint写完整的一段话，尽量详细。不要用sub bulletpoints。格式不要用黑体bold。\n"
        "以下是原始内容：\n\n" + content
    )

    # Retry up to 3 times on 429 rate-limit errors with exponential backoff
    for attempt in range(3):
        try:
            print(f"[Newsfeed] LLM call: model={model} attempt={attempt + 1}/3 " f"prompt_chars={len(prompt):,} max_tokens={max_completion_tokens}")
            t0 = time.monotonic()
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=max_completion_tokens,
            )
            elapsed = time.monotonic() - t0
            result_text = response.choices[0].message.content.strip()
            print(f"[Newsfeed] LLM done: {elapsed:.1f}s  reply_chars={len(result_text):,}")
            return result_text
        except Exception as e:
            err = str(e)
            if "429" in err and attempt < 2:
                wait = 65 * (attempt + 1)  # 65s, then 130s
                print(f"[Newsfeed] Rate limited, waiting {wait}s before retry {attempt + 2}/3...")
                time.sleep(wait)
            else:
                print(f"[Newsfeed] LLM error (attempt {attempt + 1}/3): {e}")
                return f"LLM 调用失败: {e}"
    return "LLM 调用失败: max retries exceeded"


# ---------------------------------------------------------------------------
# Daily job orchestration
# ---------------------------------------------------------------------------


def run_daily_job(days_ago: int = 1, model: str = "gpt-4o") -> dict:
    """
    Full pipeline:
    1. git pull
    2. get top posts
    3. summarise each post
    4. persist results to data/newsfeed/<date>.json
    Returns the result dict.
    """
    github_token = _load_github_token()
    job_utc = _utc_now()
    target_date = _get_date_str(days_ago)
    _, _, request_delay = _get_model_limits(model)

    print(f"[Newsfeed] Starting daily job for {target_date} at {job_utc.isoformat()}")

    # Step 1 — git pull
    pull_result = git_pull()
    print(f"[Newsfeed] git pull: {pull_result}")

    # Step 2 — rank top posts
    posts = get_top_posts(days_ago=days_ago)
    print(f"[Newsfeed] Found {len(posts)} threads with activity on {target_date}")

    # Step 3 — summarise; persist partial results after each post so the UI
    # can show cards as they arrive instead of waiting for all 20.
    NEWSFEED_DATA_PATH.mkdir(parents=True, exist_ok=True)
    # Filename encodes the GMT time the job was started, e.g. 2026-03-08T14-30-00Z.json
    output_file = NEWSFEED_DATA_PATH / f"{job_utc.strftime('%Y-%m-%dT%H-%M-%SZ')}.json"
    total = len(posts)
    completed_posts: list = []

    # Rate limit: delay between API calls varies by model tier
    for i, post in enumerate(posts):
        if i > 0:
            print(f"[Newsfeed] Waiting {request_delay}s to respect rate limit...")
            time.sleep(request_delay)
        print(f"[Newsfeed] Summarising {i+1}/{total}: {post['title']}")
        if post["file_path"]:
            post["summary"] = summarize_post(post["file_path"], github_token, model=model)
        else:
            post["summary"] = "文件路径未找到"
        completed_posts.append(post)

        # Write partial snapshot after every post
        partial_output = {
            "generated_at": _utc_now().isoformat(),
            "date": target_date,
            "pull_result": pull_result,
            "partial": True,
            "progress": {"done": i + 1, "total": total},
            "posts": completed_posts,
        }
        output_file.write_text(json.dumps(partial_output, ensure_ascii=False, indent=2), encoding="utf-8")

    # Step 4 — mark complete
    output = {
        "generated_at": _utc_now().isoformat(),
        "date": target_date,
        "pull_result": pull_result,
        "partial": False,
        "progress": {"done": total, "total": total},
        "posts": completed_posts,
    }
    output_file.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Newsfeed] Saved results to {output_file}")

    return output


# ---------------------------------------------------------------------------
# Read stored results
# ---------------------------------------------------------------------------


def get_latest_result() -> Optional[dict]:
    """Return the most recently generated newsfeed data, or None."""
    NEWSFEED_DATA_PATH.mkdir(parents=True, exist_ok=True)
    files = sorted(NEWSFEED_DATA_PATH.glob("*.json"), reverse=True)
    if not files:
        return None
    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except Exception:
        return None


def get_status() -> dict:
    """Return metadata about the last run and the next scheduled run."""
    result = get_latest_result()
    if result:
        return {
            "last_run": result.get("generated_at"),
            "last_date": result.get("date"),
            "post_count": len(result.get("posts", [])),
            "ready": True,
        }
    return {"last_run": None, "last_date": None, "post_count": 0, "ready": False}


# ---------------------------------------------------------------------------
# Background scheduler (runs once per day; checks every hour)
# ---------------------------------------------------------------------------

# _job_lock is held for the FULL duration of a running job so that no two
# jobs (background + manual) can call the LLM concurrently.
_job_lock = threading.Lock()
_is_running = False


def _background_worker():
    """
    Worker that runs in a daemon thread.
    On first iteration (including server startup) and every hour thereafter,
    checks whether the latest cached newsfeed is more than 12 hours old (GMT).
    If so — or if no cache exists — runs the daily job.
    """
    global _is_running
    while True:
        try:
            # Determine whether a fresh run is needed based on GMT age of latest cache
            needs_run = True
            result = get_latest_result()
            if result and not result.get("partial", True):
                generated_at_str = result.get("generated_at", "")
                try:
                    dt = datetime.fromisoformat(generated_at_str)
                    if dt.tzinfo is None:
                        # Legacy naive timestamp — assume UTC
                        dt = dt.replace(tzinfo=timezone.utc)
                    age = _utc_now() - dt.astimezone(timezone.utc)
                    if age < timedelta(hours=12):
                        needs_run = False
                        print(f"[Newsfeed] Latest cache is {age.total_seconds() / 3600:.1f}h old " "(< 12 h), skipping.")
                except Exception:
                    pass  # Unparseable timestamp → re-run

            if needs_run:
                # Non-blocking acquire: skip if a manual run is already holding the lock
                if _job_lock.acquire(blocking=False):
                    _is_running = True
                    try:
                        run_daily_job(days_ago=1)
                    finally:
                        _is_running = False
                        _job_lock.release()
                else:
                    print("[Newsfeed] Background worker skipping — job already in progress.")
        except Exception as e:
            print(f"[Newsfeed] Background worker error: {e}")

        # Sleep 1 hour before checking again
        time.sleep(3600)


def start_background_worker():
    """Start the daemon background worker thread."""
    t = threading.Thread(target=_background_worker, daemon=True, name="newsfeed-worker")
    t.start()
    print("[Newsfeed] Background worker started")


def trigger_manual_job(days_ago: int = 1) -> bool:
    """
    Try to start a manual job in a background thread.
    Returns True if the job was started, False if one is already running.
    Holds _job_lock for the full duration so no LLM calls run in parallel.
    """
    global _is_running
    if not _job_lock.acquire(blocking=False):
        return False
    _is_running = True

    def _run():
        global _is_running
        try:
            run_daily_job(days_ago=days_ago)
        except Exception as e:
            print(f"[Newsfeed] Manual run error: {e}")
        finally:
            _is_running = False
            _job_lock.release()

    threading.Thread(target=_run, daemon=True, name="newsfeed-manual-run").start()
    return True


def is_running() -> bool:
    """Return True if a job is currently in progress."""
    return _is_running
