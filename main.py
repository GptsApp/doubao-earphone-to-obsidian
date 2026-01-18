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
import logging
import os
import re
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings

# ========== 日志配置 ==========
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# ========== 配置管理 ==========
class Settings(BaseSettings):
    """配置管理类，使用 pydantic 进行验证"""
    OBSIDIAN_VAULT: str = ""
    NOTES_DIR: str = "Inbox/Voice Notes"
    TASKS_DIR: str = "Tasks"
    POLL_INTERVAL: int = Field(10, ge=1, le=300, description="轮询间隔（秒）")
    CHAT_URL: str = "https://www.doubao.com/chat/624642496948226"
    DB_PATH: str = "data/processed.sqlite"
    STATE_PATH: str = "storage_state.json"
    DEBUG: bool = False
    HEADFUL: bool = True
    DEDUP_HOURS: int = Field(36, ge=1, le=168, description="去重时间窗口（小时）")
    KEYWORD_NOTE: str = "记笔记"
    KEYWORD_TASK: str = "记任务"

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


# 加载配置
load_dotenv()
settings = Settings()
VAULT = Path(settings.OBSIDIAN_VAULT).expanduser().resolve()
NOTES_DIR = settings.NOTES_DIR
TASKS_DIR = settings.TASKS_DIR
POLL_INTERVAL = settings.POLL_INTERVAL
CHAT_URL = settings.CHAT_URL
DB_PATH = Path(settings.DB_PATH)
STATE_PATH = Path(settings.STATE_PATH)
DEBUG = settings.DEBUG
HEADFUL = settings.HEADFUL
DEDUP_HOURS = settings.DEDUP_HOURS
KEYWORD_NOTE = settings.KEYWORD_NOTE
KEYWORD_TASK = settings.KEYWORD_TASK

# 设置日志级别
if not DEBUG:
    logger.setLevel(logging.INFO)

# ========== 正则预编译 ==========
def build_cmd_regex() -> re.Pattern[str]:
    """根据配置的关键词构建触发正则，容忍"豆包豆包"前缀"""
    kw_note = re.escape(KEYWORD_NOTE)
    kw_task = re.escape(KEYWORD_TASK)
    return re.compile(rf"^\s*(?:豆包豆包[，,:：。\s]*)?({kw_note}|{kw_task})[：:，,。\s]+(.+)$")

CMD_RE = build_cmd_regex()

# 预编译归一化正则
NORMALIZE_NOTE_RE = re.compile(
    rf"^(豆包豆包[，,:：\s]*)?{re.escape(KEYWORD_NOTE)}[，,:：\s]*{re.escape(KEYWORD_NOTE)}[，,:：\s]*"
)
NORMALIZE_TASK_RE = re.compile(
    rf"^(豆包豆包[，,:：\s]*)?{re.escape(KEYWORD_TASK)}[，,:：\s]*{re.escape(KEYWORD_TASK)}[，,:：\s]*"
)
NORMALIZE_SPACE_RE = re.compile(r"[ \t]+")
NORMALIZE_REMOVE_RE = re.compile(r"[分享\s。．·!！?？、,.，:：;；\-]+")

# ========== 时间工具 ==========
def today() -> str:
    """获取今天的日期字符串"""
    return datetime.now().strftime("%Y-%m-%d")


def hhmm() -> str:
    """获取当前时间字符串"""
    return datetime.now().strftime("%H:%M")


# ========== 文本归一化 & 去重 ==========
def normalize_text(text: str) -> str:
    """清洗文本：去"分享"、合并重复前缀、统一分隔符、压缩空白"""
    result = (text or "").replace("\u200b", "").replace("分享", "").replace("。", "，")

    result = NORMALIZE_NOTE_RE.sub(f"{KEYWORD_NOTE}，", result)
    result = NORMALIZE_TASK_RE.sub(f"{KEYWORD_TASK}，", result)
    result = NORMALIZE_SPACE_RE.sub(" ", result)
    return result.strip()


def compute_dedup_hash(text: str) -> str:
    """对去噪内容做哈希，用于去重"""
    base = normalize_text(text)
    base = NORMALIZE_REMOVE_RE.sub("", base)
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


def cleanup_old_records(horizon_hours: int = 36) -> None:
    """清理超过 horizon_hours 的旧记录"""
    cutoff = time.time() - max(1, horizon_hours) * 3600
    with DB_LOCK:
        cursor = DB.execute("DELETE FROM seen WHERE ts < ?", (cutoff,))
        deleted = cursor.rowcount
        DB.commit()
        if DEBUG and deleted > 0:
            logger.debug(f"清理了 {deleted} 条过期记录")


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

# ========== 并发控制 ==========
WRITE_SEMAPHORE = asyncio.Semaphore(5)


# ========== 文件写入 ==========
async def append_to_file(path: Path, text: str) -> None:
    """追加文本到文件，自动创建父目录"""
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "a", encoding="utf-8") as f:
        await f.write(text)


async def write_to_obsidian(content: str, kind: str) -> None:
    """统一写入接口"""
    async with WRITE_SEMAPHORE:
        try:
            if kind == KEYWORD_NOTE:
                filepath = VAULT / NOTES_DIR / f"{today()}.md"
                prefix = f"- [{hhmm()}] "
                logger.info(f"目标文件: {filepath}")
            else:
                filepath = VAULT / TASKS_DIR / f"{today()}.md"
                prefix = "- [ ] "
                logger.info(f"目标文件: {filepath}")
            
            await append_to_file(filepath, f"{prefix}{content.strip()}\n")
            logger.info(f"写入{kind}: {content.strip()}")
        except IOError as e:
            logger.error(f"写入文件失败: {e}")
            raise

# ========== 文本提取 ==========
JSON_TEXT_KEYS = ("text", "content", "message", "delta", "display_text")


def extract_texts_from_json(obj: Any) -> list[str]:
    """从 JSON 对象中递归提取包含关键词的文本"""
    results = []

    def pick(item: Any) -> None:
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

    try:
        if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
            try:
                obj = json.loads(text)
                results = extract_texts_from_json(obj)
                if results:
                    return results
            except json.JSONDecodeError:
                pass

        matches = re.findall(r'"(?:text|content|message|delta|display_text)"\s*:\s*"(.*?)"', text)
        if matches:
            return [re.sub(r'\\(["\\/bfnrt])', r'\1', m) for m in matches]
    except Exception as e:
        logger.warning(f"提取文本时出错: {e}")

    return [text]

# ========== 消息处理 ==========
async def handle_text(source: str, raw_text: str) -> None:
    """处理文本，匹配命令并写入笔记或任务"""
    try:
        candidates = extract_texts(raw_text)
        prefix_pattern = rf"^(?:豆包豆包[，,:：。\s]*)?(?:{re.escape(KEYWORD_NOTE)}|{re.escape(KEYWORD_TASK)})[：:，,。\s]+"

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
                    if DEBUG:
                        logger.debug(f"[{source}] 重复内容，跳过: {content}")
                    continue

                await write_to_obsidian(content, kind)

                if DEBUG:
                    logger.debug(f"[{source}] 命中并写入")
    except Exception as e:
        logger.error(f"处理文本时出错 [{source}]: {e}")

# ========== 页面抓取通道 ==========
async def poll_dom(page: Page) -> None:
    """DOM 轮询：扫描最近 10 条包含关键词的元素"""
    try:
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
                    logger.debug(f"DOM 元素提取异常: {e}")
    except Exception as e:
        logger.error(f"DOM 轮询异常: {e}")


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


async def brute_scrape(page: Page) -> None:
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
                    logger.debug(f"Brute 子帧异常 [{getattr(frame, 'url', 'unknown')}]: {e}")
    except Exception as e:
        logger.error(f"Brute 扫描异常: {e}")

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


async def start_browser(
    playwright: Any,
    force_headless: bool = False
) -> tuple[Browser, str, bool]:
    """启动浏览器，优先使用本地 Chromium

    Args:
        playwright: Playwright 实例
        force_headless: 强制使用无头模式（用于已登录后的监听）

    Returns:
        tuple: (browser, executable_path, headless)
    """
    script_dir = Path(__file__).parent.resolve()
    default_browsers = str(script_dir / "pw-browsers")
    browsers_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH", default_browsers)

    local_chromium = find_local_chromium(browsers_path)
    candidates = [local_chromium] + BROWSER_CANDIDATES + [None]

    headless = force_headless or (not HEADFUL and STATE_PATH.exists())
    last_error = None

    for exe in candidates:
        try:
            launch_args: dict[str, Any] = {
                "headless": headless,
                "args": ["--no-first-run", "--no-default-browser-check"]
            }
            if exe and os.path.exists(exe):
                launch_args["executable_path"] = exe
                if headless:
                    launch_args["args"].append("--headless=new")

            logger.info(f"准备启动浏览器：exe={exe or 'playwright-default'}, headless={headless}")
            browser = await playwright.chromium.launch(**launch_args)
            return browser, exe or "playwright-default", headless
        except Exception as e:
            last_error = e
            logger.warning(f"启动失败，尝试下一个：{e}")

    raise RuntimeError(f"所有候选浏览器均失败：{last_error}")

# ========== Observer 注入 ==========
async def inject_observer_to_page(page: Page) -> None:
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
                logger.debug(f"[Frame {getattr(frame, 'url', 'unknown')}] add_init_script 失败: {e}")


async def inject_to_frame(frame: Any) -> None:
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

    doubao_cookies = [c for c in cookies if 'doubao.com' in c.get('domain', '')]

    if len(doubao_cookies) < 5:
        return False

    auth_cookie_names = {
        'sessionid', 'sessionid_ss', 'passport_csrf_token',
        'sid_guard', 'sid_tt', 'uid_tt', 'ssid_ucp_v1',
        'ttwid', 'passport_auth_status'
    }

    cookie_names = {c.get('name', '') for c in doubao_cookies}
    matched = auth_cookie_names & cookie_names

    return len(matched) >= 3


async def wait_for_login(context: BrowserContext, browser: Browser) -> bool:
    """
    等待用户登录，返回是否成功

    核心逻辑：持续监测 cookie，只有检测到有效的登录 cookie 才算成功
    容错用户的各种操作（刷新、跳转等），只要最终登录成功即可
    """
    logger.info("首次运行：请在弹出的浏览器中登录豆包...")
    logger.info("登录成功后将自动保存 Cookie 并关闭浏览器")
    logger.info("（您可以正常操作浏览器，刷新页面不会影响登录检测）")

    stable_count = 0
    max_wait_seconds = 300
    check_interval = 2

    for i in range(max_wait_seconds // check_interval):
        await asyncio.sleep(check_interval)

        try:
            cookies = await context.cookies()

            if has_valid_login_cookies(cookies):
                stable_count += 1
                if DEBUG:
                    logger.debug(f"检测到有效登录 cookie，稳定计数: {stable_count}/3")

                if stable_count >= 3:
                    await context.storage_state(path=str(STATE_PATH))

                    logger.info("========================================")
                    logger.info("  登录成功！Cookie 已保存")
                    logger.info("  浏览器将在 3 秒后关闭...")
                    logger.info("========================================")
                    await asyncio.sleep(3)
                    await browser.close()
                    logger.info("浏览器已关闭。请重新运行服务以后台模式启动。")
                    return True
            else:
                if stable_count > 0 and DEBUG:
                    logger.debug("cookie 状态变化，重置稳定计数")
                stable_count = 0

        except Exception as e:
            if DEBUG:
                logger.debug(f"检查 cookie 时出错: {e}")
            stable_count = 0

        elapsed = (i + 1) * check_interval
        if elapsed % 30 == 0:
            logger.info(f"等待登录中... 已等待 {elapsed} 秒（最长 {max_wait_seconds} 秒）")

    logger.error("登录超时（5分钟），请重试")
    return False


async def handle_network_response(resp: Any) -> None:
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
            logger.debug(f"[Network] 命中 {len(texts)} 条, URL: {url}")
    except Exception as e:
        logger.debug(f"处理网络响应异常: {e}")


async def run_polling_loop(page: Page) -> None:
    """运行主轮询循环"""
    logger.info(f"开始监听...（每 {POLL_INTERVAL}s 扫描一次）")

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
                logger.info("检测到页面关闭，退出。")
                break
            if DEBUG:
                logger.debug(f"轮询异常: {e}")

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
    logger.info(f"脚本启动：HEADFUL={HEADFUL}, DEBUG={DEBUG}, CHAT_URL={CHAT_URL}")

    # 检查 VAULT 路径
    vault_path = None
    if str(VAULT).strip():
        vault_path = Path(str(VAULT)).expanduser().resolve()

    if not vault_path or not vault_path.exists():
        print("\n" + "=" * 50)
        print("  ⚠️  Obsidian 仓库路径未设置或不存在")
        print("=" * 50)
        print("\n请选择设置方式：")
        print("  1. 输入 Obsidian 仓库的绝对路径")
        print("  2. 查找常见的 Obsidian 仓库位置")
        print("  3. 退出程序")

        choice = input("\n请输入选项 (1/2/3): ").strip()

        if choice == "1":
            user_path = input("\n请输入 Obsidian 仓库路径: ").strip()
            vault_path = Path(user_path).expanduser().resolve()

            if not vault_path.exists():
                print(f"\n❌ 路径不存在: {vault_path}")
                print("请检查路径后重试。")
                return

            print(f"\n✅ 路径验证成功: {vault_path}")
            print(f"正在更新 .env 文件...")

            # 更新 .env 文件
            env_file = Path(__file__).parent / ".env"
            if not env_file.exists():
                env_file.write_text("")

            env_content = env_file.read_text(encoding='utf-8')

            # 检查并更新 OBSIDIAN_VAULT
            import re
            if re.search(r'^OBSIDIAN_VAULT\s*=', env_content, re.MULTILINE):
                env_content = re.sub(
                    r'^OBSIDIAN_VAULT\s*=.*$',
                    f'OBSIDIAN_VAULT={str(vault_path)}',
                    env_content,
                    count=1,
                    flags=re.MULTILINE
                )
            else:
                env_content += f'\nOBSIDIAN_VAULT={str(vault_path)}\n'

            env_file.write_text(env_content, encoding='utf-8')
            print("✅ .env 文件已更新")
            print("\n请重新启动程序：")
            print("  python main.py")
            return

        elif choice == "2":
            print("\n正在查找常见的 Obsidian 仓库位置...")

            # 常见位置
            home = Path.home()
            common_paths = [
                home / "Documents" / "Obsidian",
                home / "Documents",
                home / "Dropbox" / "Obsidian",
                home / "OneDrive" / "Obsidian",
                home / "Library" / "Mobile Documents" / "iCloud~obsidian",
            ]

            found = False
            for base_path in common_paths:
                if not base_path.exists():
                    continue

                # 查找 .obsidian 文件夹（Obsidian 仓库的标识）
                for vault in base_path.iterdir():
                    if vault.is_dir() and (vault / ".obsidian").exists():
                        print(f"\n✅ 找到仓库: {vault}")
                        found = True

            if not found:
                print("\n❌ 未找到 Obsidian 仓库")
                print("请手动选择选项 1 并输入路径。")
            return

        else:
            print("\n已退出程序。")
            return

    init_database()
    cleanup_old_records(horizon_hours=DEDUP_HOURS)

    already_logged_in = STATE_PATH.exists()

    async with async_playwright() as pw:
        browser: Browser | None = None
        try:
            browser, chosen, headless = await start_browser(pw, force_headless=already_logged_in)
            context = await browser.new_context(
                storage_state=str(STATE_PATH) if already_logged_in else None,
                user_agent=USER_AGENT
            )
            page = await context.new_page()

            page.on("response", handle_network_response)

            if not already_logged_in:
                login_url = "https://www.doubao.com/chat/login"
                logger.info(f"已启动：{chosen} -> 前往登录页 {login_url}")
                await page.goto(login_url, timeout=120000, wait_until="domcontentloaded")
                if await wait_for_login(context, browser):
                    return
                return

            logger.info(f"已启动：{chosen} (后台模式) -> 前往 {CHAT_URL}")
            await page.goto(CHAT_URL, timeout=120000, wait_until="domcontentloaded")

            await inject_observer_to_page(page)
            page.on("frameattached", lambda f: asyncio.create_task(inject_to_frame(f)))

            await run_polling_loop(page)
        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"FATAL: {e}")