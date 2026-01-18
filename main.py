"""
@input  .env 配置、豆包网页
@output Obsidian 笔记/任务文件
@pos    核心监控服务，监听豆包聊天并写入 Obsidian

自指声明：更新此文件时同步更新根目录 _INDEX.md
"""

import asyncio
import atexit
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

import aiofiles
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# ========== 环境配置 ==========
load_dotenv()

VAULT = Path(os.getenv("OBSIDIAN_VAULT", "")).expanduser().resolve()
NOTES_DIR = os.getenv("NOTES_DIR", "Inbox/Voice Notes")
TASKS_DIR = os.getenv("TASKS_DIR", "Tasks")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
CHAT_URL = os.getenv("CHAT_URL", "https://www.doubao.com/chat/624642496948226")
DB_PATH = Path("data/processed.sqlite")
STATE_PATH = Path("storage_state.json")
DEBUG = os.getenv("DEBUG", "0") == "1"
HEADFUL = os.getenv("HEADFUL", "1") == "1"
DEDUP_HOURS = int(os.getenv("DEDUP_HOURS", "36"))
KEYWORD_NOTE = os.getenv("KEYWORD_NOTE", "记笔记")
KEYWORD_TASK = os.getenv("KEYWORD_TASK", "记任务")

def build_cmd_regex() -> re.Pattern:
    """根据配置的关键词构建触发正则，容忍"豆包豆包"前缀"""
    kw_note = re.escape(KEYWORD_NOTE)
    kw_task = re.escape(KEYWORD_TASK)
    return re.compile(rf"^\s*(?:豆包豆包[，,:：。\s]*)?({kw_note}|{kw_task})[：:，,。\s]+(.+)$")

CMD_RE = build_cmd_regex()

# ========== 日志 & 时间工具 ==========
def log(*args) -> None:
    print(datetime.now().strftime("[%H:%M:%S]"), *args, flush=True)


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def hhmm() -> str:
    return datetime.now().strftime("%H:%M")

# ========== 文本归一化 & 去重 ==========
def normalize_text(text: str) -> str:
    """清洗文本：去"分享"、合并重复前缀、统一分隔符、压缩空白"""
    result = (text or "").replace("\u200b", "").replace("分享", "").replace("。", "，")

    kw_note = re.escape(KEYWORD_NOTE)
    kw_task = re.escape(KEYWORD_TASK)
    result = re.sub(
        rf"^(豆包豆包[，,:：\s]*)?{kw_note}[，,:：\s]*{kw_note}[，,:：\s]*",
        f"{KEYWORD_NOTE}，",
        result
    )
    result = re.sub(
        rf"^(豆包豆包[，,:：\s]*)?{kw_task}[，,:：\s]*{kw_task}[，,:：\s]*",
        f"{KEYWORD_TASK}，",
        result
    )
    result = re.sub(r"[ \t]+", " ", result)
    return result.strip()


def compute_dedup_hash(text: str) -> str:
    """对去噪内容做哈希，用于去重"""
    base = normalize_text(text)
    base = re.sub(r"[分享\s。．·!！?？、,.，:：;；\-]+", "", base)
    return hashlib.sha256(base.encode()).hexdigest()

# ========== SQLite 数据库 ==========
DB: sqlite3.Connection | None = None
DB_LOCK = threading.Lock()


def init_database() -> None:
    """初始化全局数据库连接，使用 WAL 模式"""
    global DB
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB = sqlite3.connect(DB_PATH, check_same_thread=False)
    DB.execute("PRAGMA journal_mode=WAL;")
    DB.execute("PRAGMA synchronous=NORMAL;")
    DB.execute("CREATE TABLE IF NOT EXISTS seen(id TEXT PRIMARY KEY, ts REAL)")
    DB.commit()
    atexit.register(lambda: DB and DB.close())

def is_duplicate_or_mark_seen(key: str, horizon_hours: int = 36) -> bool:
    """
    滑动窗口去重：若 key 在最近 horizon_hours 小时内见过则返回 True（重复），
    否则插入/更新时间戳并返回 False（首次/过期）
    """
    now = time.time()
    cutoff = now - max(1, horizon_hours) * 3600

    with DB_LOCK:
        row = DB.execute("SELECT ts FROM seen WHERE id=?", (key,)).fetchone()
        if row:
            last_ts = row[0] or 0.0
            DB.execute("UPDATE seen SET ts=? WHERE id=?", (now, key))
            DB.commit()
            return last_ts >= cutoff

        DB.execute("INSERT INTO seen(id, ts) VALUES(?, ?)", (key, now))
        DB.commit()
        return False

# ========== 文件写入 ==========
async def append_to_file(path: Path, text: str) -> None:
    """追加文本到文件，自动创建父目录"""
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "a", encoding="utf-8") as f:
        await f.write(text)


async def write_note(content: str) -> None:
    """写入笔记到 Obsidian"""
    filepath = VAULT / NOTES_DIR / f"{today()}.md"
    log("目标文件:", filepath)
    await append_to_file(filepath, f"- [{hhmm()}] {content.strip()}\n")
    log("写入笔记:", content.strip())


async def write_task(content: str) -> None:
    """写入任务到 Obsidian"""
    filepath = VAULT / TASKS_DIR / f"{today()}.md"
    log("目标文件:", filepath)
    await append_to_file(filepath, f"- [ ] {content.strip()}\n")
    log("写入任务:", content.strip())

# ========== 文本提取 ==========
JSON_TEXT_KEYS = ("text", "content", "message", "delta", "display_text")


def extract_texts_from_json(obj) -> list[str]:
    """从 JSON 对象中递归提取包含关键词的文本"""
    results = []

    def pick(item):
        if isinstance(item, str):
            if KEYWORD_NOTE in item or KEYWORD_TASK in item:
                results.append(item)
        elif isinstance(item, list):
            for element in item:
                pick(element)
        elif isinstance(item, dict):
            for key in JSON_TEXT_KEYS:
                if key in item:
                    pick(item[key])
            for value in item.values():
                pick(value)

    pick(obj)
    return results[:50]


def extract_texts(raw: str) -> list[str]:
    """从字符串或 JSON 中提取文本列表"""
    text = (raw or "").strip()
    if not text:
        return []

    # 尝试 JSON 解析
    if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
        try:
            obj = json.loads(text)
            results = extract_texts_from_json(obj)
            if results:
                return results
        except json.JSONDecodeError:
            pass

    # 简单 JSON 片段提取
    matches = re.findall(r'"(?:text|content|message|delta|display_text)"\s*:\s*"(.*?)"', text)
    if matches:
        return [re.sub(r'\\(["\\/bfnrt])', r'\1', m) for m in matches]

    return [text]

# ========== 消息处理 ==========
async def handle_text(source: str, raw_text: str) -> None:
    """处理文本，匹配命令并写入笔记或任务"""
    candidates = extract_texts(raw_text)
    kw_note = re.escape(KEYWORD_NOTE)
    kw_task = re.escape(KEYWORD_TASK)
    prefix_pattern = rf"^(?:豆包豆包[，,:：。\s]*)?(?:{kw_note}|{kw_task})[：:，,。\s]+"

    for raw in candidates:
        normalized = normalize_text(raw)
        if not normalized:
            continue

        for line in normalized.splitlines():
            line = line.strip()
            if not line:
                continue

            match = CMD_RE.match(line)
            if not match:
                continue

            kind, content = match.group(1), match.group(2).strip()
            content = re.sub(prefix_pattern, "", content).strip()

            dedup_key = compute_dedup_hash(kind + "|" + content)
            if is_duplicate_or_mark_seen(dedup_key, horizon_hours=DEDUP_HOURS):
                continue

            if kind == KEYWORD_NOTE:
                await write_note(content)
            else:
                await write_task(content)

            if DEBUG:
                log(f"[{source}] 命中并写入")

# ========== 页面抓取通道 ==========
async def poll_dom(page) -> None:
    """DOM 轮询：扫描最近 10 条包含关键词的元素"""
    selector = (
        f":is(div,li,article,section,p,span):has-text('{KEYWORD_NOTE}'), "
        f":is(div,li,article,section,p,span):has-text('{KEYWORD_TASK}')"
    )
    nodes = page.locator(selector)
    count = await nodes.count()
    start = max(0, count - 10)

    for i in range(start, count):
        try:
            raw = await nodes.nth(i).inner_text()
            if raw:
                await handle_text("DOM", raw)
        except Exception as e:
            if DEBUG:
                log("DOM异常:", e)

def build_mutation_observer_js() -> str:
    """构建 MutationObserver JavaScript 代码"""
    kw_note = KEYWORD_NOTE.replace('\\', '\\\\').replace('/', '\\/')
    kw_task = KEYWORD_TASK.replace('\\', '\\\\').replace('/', '\\/')
    return f"""
(() => {{
  const send = window.__emitMessage || (()=>{{}});
  const scan = (n) => {{
    try {{
      const t = (n.innerText || n.textContent || "").slice(0,4000);
      if (/{kw_note}|{kw_task}/.test(t)) send(t);
    }} catch(e){{}}
  }};
  const obs = new MutationObserver(muts => {{
    for (const m of muts) if (m.addedNodes)
      m.addedNodes.forEach(n => {{ if (n.nodeType===1) scan(n); }});
  }});
  obs.observe(document.documentElement, {{childList:true,subtree:true}});
  scan(document.body || document.documentElement);
}})();
"""


MUTATION_JS = build_mutation_observer_js()


async def brute_scrape(page) -> None:
    """暴力扫描：遍历所有 frame 的 innerText"""
    try:
        for frame in page.frames:
            try:
                txt = await frame.evaluate(
                    "document.body ? document.body.innerText.slice(0,50000) : ''"
                )
                if txt:
                    await handle_text("Brute", txt)
            except Exception as e:
                if DEBUG:
                    log("Brute子帧异常:", getattr(frame, 'url', ''), e)
    except Exception as e:
        if DEBUG:
            log("Brute异常:", e)

# ========== 浏览器启动 ==========
BROWSER_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


def find_local_chromium(browsers_dir: str) -> str | None:
    """查找本地 Chromium 可执行文件"""
    if not os.path.isdir(browsers_dir):
        return None

    for name in sorted(os.listdir(browsers_dir), reverse=True):
        if name.startswith("chromium-"):
            exe = os.path.join(
                browsers_dir, name, "chrome-mac", "Chromium.app",
                "Contents", "MacOS", "Chromium"
            )
            if os.path.exists(exe):
                return exe
    return None


async def start_browser(playwright, force_headless: bool = False):
    """启动浏览器，优先使用本地 Chromium

    Args:
        force_headless: 强制使用无头模式（用于已登录后的监听）
    """
    script_dir = Path(__file__).parent.resolve()
    default_browsers = str(script_dir / "pw-browsers")
    browsers_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH", default_browsers)

    local_chromium = find_local_chromium(browsers_path)
    candidates = [local_chromium] + BROWSER_CANDIDATES + [None]

    # 已登录后强制 headless，首次登录需要显示窗口
    headless = force_headless or (not HEADFUL and STATE_PATH.exists())
    last_error = None

    for exe in candidates:
        try:
            launch_args = {
                "headless": headless,
                "args": ["--no-first-run", "--no-default-browser-check"]
            }
            if exe and os.path.exists(exe):
                launch_args["executable_path"] = exe
                if headless:
                    launch_args["args"].append("--headless=new")

            log(f"准备启动浏览器：exe={exe or 'playwright-default'}, headless={headless}")
            browser = await playwright.chromium.launch(**launch_args)
            return browser, exe or "playwright-default", headless
        except Exception as e:
            last_error = e
            log(f"启动失败，尝试下一个：{e}")

    raise RuntimeError(f"所有候选浏览器均失败：{last_error}")

# ========== Observer 注入 ==========
async def inject_observer_to_page(page) -> None:
    """向页面注入 MutationObserver"""
    try:
        await page.expose_function(
            "__emitMessage",
            lambda s: asyncio.create_task(handle_text("Observer", s))
        )
    except Exception:
        pass  # 已暴露过则忽略

    for frame in page.frames:
        try:
            await frame.add_init_script(MUTATION_JS)
        except Exception as e:
            if DEBUG:
                log("[Frame] add_init_script 失败:", getattr(frame, "url", ""), e)


async def inject_to_frame(frame) -> None:
    """向单个 frame 注入 Observer"""
    try:
        await frame.evaluate(MUTATION_JS)
    except Exception:
        pass

# ========== 主逻辑 ==========
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
NETWORK_URL_KEYWORDS = ("samantha", "alice", "message", "chat", "conversation", "stream", "history")


def has_valid_login_cookies(cookies: list[dict]) -> bool:
    """
    检查是否包含有效的豆包登录 cookie
    豆包登录后会设置特定的认证 cookie，如 sessionid、passport_csrf_token 等
    """
    if not cookies:
        return False

    # 豆包登录成功的关键 cookie 标识
    # 需要同时满足：有 doubao.com 域名的 cookie，且包含认证相关的 cookie
    doubao_cookies = [c for c in cookies if 'doubao.com' in c.get('domain', '')]

    if len(doubao_cookies) < 5:  # 登录后通常会有多个 cookie
        return False

    # 检查是否有认证相关的 cookie（这些是登录后才会有的）
    auth_cookie_names = {
        'sessionid', 'sessionid_ss', 'passport_csrf_token',
        'sid_guard', 'sid_tt', 'uid_tt', 'ssid_ucp_v1',
        'ttwid', 'passport_auth_status'
    }

    cookie_names = {c.get('name', '') for c in doubao_cookies}
    matched = auth_cookie_names & cookie_names

    # 至少匹配 3 个认证 cookie 才认为登录成功
    return len(matched) >= 3


async def wait_for_login(context, browser) -> bool:
    """
    等待用户登录，返回是否成功

    核心逻辑：持续监测 cookie，只有检测到有效的登录 cookie 才算成功
    容错用户的各种操作（刷新、跳转等），只要最终登录成功即可
    """
    log("首次运行：请在弹出的浏览器中登录豆包...")
    log("登录成功后将自动保存 Cookie 并关闭浏览器")
    log("（您可以正常操作浏览器，刷新页面不会影响登录检测）")

    stable_count = 0
    max_wait_seconds = 300  # 最长等待 5 分钟
    check_interval = 2  # 每 2 秒检查一次

    for i in range(max_wait_seconds // check_interval):
        await asyncio.sleep(check_interval)

        try:
            # 获取当前所有 cookie
            cookies = await context.cookies()

            if has_valid_login_cookies(cookies):
                stable_count += 1
                if DEBUG:
                    log(f"检测到有效登录 cookie，稳定计数: {stable_count}/3")

                # 连续 3 次检测到有效 cookie 才确认登录成功（防止瞬时状态）
                if stable_count >= 3:
                    # 保存 storage state
                    await context.storage_state(path=str(STATE_PATH))

                    log("========================================")
                    log("  登录成功！Cookie 已保存")
                    log("  浏览器将在 3 秒后关闭...")
                    log("========================================")
                    await asyncio.sleep(3)
                    await browser.close()
                    log("浏览器已关闭。请重新运行服务以后台模式启动。")
                    return True
            else:
                # cookie 无效时重置计数（用户可能刷新了页面）
                if stable_count > 0 and DEBUG:
                    log("cookie 状态变化，重置稳定计数")
                stable_count = 0

        except Exception as e:
            if DEBUG:
                log(f"检查 cookie 时出错: {e}")
            stable_count = 0

        # 定期提示用户
        elapsed = (i + 1) * check_interval
        if elapsed % 30 == 0:
            log(f"等待登录中... 已等待 {elapsed} 秒（最长 {max_wait_seconds} 秒）")

    log("登录超时（5分钟），请重试")
    return False


async def handle_network_response(resp) -> None:
    """处理网络响应，提取 JSON 中的文本"""
    try:
        content_type = (resp.headers.get("content-type") or "").lower()
        if "application/json" not in content_type:
            return

        url = resp.url
        if not any(keyword in url for keyword in NETWORK_URL_KEYWORDS):
            return

        try:
            data = await resp.json()
        except Exception:
            return

        texts = extract_texts_from_json(data)
        for text in texts:
            await handle_text("Network", text)

        if DEBUG and texts:
            log("[Network] 命中", len(texts), url)
    except Exception as e:
        if DEBUG:
            log("on_response异常:", e)


async def run_polling_loop(page) -> None:
    """运行主轮询循环"""
    log(f"开始监听...（每 {POLL_INTERVAL}s 扫描一次）")

    while True:
        try:
            await poll_dom(page)
            await brute_scrape(page)
            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            except Exception:
                pass
        except Exception as e:
            if "has been closed" in str(e):
                log("检测到页面关闭，退出。")
                break
            if DEBUG:
                log("轮询异常:", e)

        await asyncio.sleep(POLL_INTERVAL)


def print_startup_banner() -> None:
    """打印启动横幅和使用说明"""
    print()
    print("=" * 50)
    print("  豆包语音笔记助手 - Obsidian 同步工具")
    print("=" * 50)
    print()
    print("使用方法：")
    print(f"  1. 说「豆包豆包，{KEYWORD_NOTE}，<内容>」记录笔记")
    print(f"  2. 说「豆包豆包，{KEYWORD_TASK}，<内容>」记录任务")
    print()
    print("查看结果：")
    print(f"  笔记保存位置: {VAULT / NOTES_DIR}")
    print(f"  任务保存位置: {VAULT / TASKS_DIR}")
    print()
    print("-" * 50)
    print("如果这个工具对你有帮助，欢迎关注开发者：")
    print("  @WeWill_Rocky  https://x.com/WeWill_Rocky")
    print("-" * 50)
    print()


async def main() -> None:
    """主入口函数"""
    print_startup_banner()
    log("脚本启动：HEADFUL=", HEADFUL, " DEBUG=", DEBUG, " CHAT_URL=", CHAT_URL)

    if not str(VAULT):
        log("环境变量 OBSIDIAN_VAULT 未设置")
        return

    init_database()

    # 判断是否已登录
    already_logged_in = STATE_PATH.exists()

    async with async_playwright() as pw:
        # 已登录时强制使用 headless 模式（后台运行，用户看不到浏览器）
        browser, chosen, headless = await start_browser(pw, force_headless=already_logged_in)
        context = await browser.new_context(
            storage_state=str(STATE_PATH) if already_logged_in else None,
            user_agent=USER_AGENT
        )
        page = await context.new_page()

        page.on("response", handle_network_response)

        # 首次运行需要登录，打开登录页面
        if not already_logged_in:
            login_url = "https://www.doubao.com/chat/login"
            log(f"已启动：{chosen} -> 前往登录页 {login_url}")
            await page.goto(login_url, timeout=120000, wait_until="domcontentloaded")
            if await wait_for_login(context, browser):
                return
            return

        # 已登录，直接打开聊天页面（后台 headless 模式）
        log(f"已启动：{chosen} (后台模式) -> 前往 {CHAT_URL}")
        await page.goto(CHAT_URL, timeout=120000, wait_until="domcontentloaded")

        # 注入 observer 并监听新 frame
        await inject_observer_to_page(page)
        page.on("frameattached", lambda f: asyncio.create_task(inject_to_frame(f)))

        await run_polling_loop(page)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        log("FATAL:", e)