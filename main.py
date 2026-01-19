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

# 菜单栏图标和系统通知
import pystray
from PIL import Image, ImageDraw
from plyer import notification

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
    SMART_POLLING: bool = Field(True, description="智能轮询：活跃时快速，空闲时慢速")
    FAST_POLL_INTERVAL: int = Field(5, ge=1, le=60, description="活跃时轮询间隔（秒）")
    SLOW_POLL_INTERVAL: int = Field(30, ge=10, le=300, description="空闲时轮询间隔（秒）")
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

# ========== 日志频率控制 ==========
_log_counters = {}
_log_last_time = {}

def should_log_debug(key: str, interval_seconds: int = 30) -> bool:
    """控制调试日志频率，避免日志刷屏"""
    if not DEBUG:
        return False

    current_time = time.time()
    last_time = _log_last_time.get(key, 0)

    if current_time - last_time >= interval_seconds:
        _log_last_time[key] = current_time
        # 显示累计次数
        count = _log_counters.get(key, 0)
        if count > 0:
            logger.debug(f"[{key}] (过去{interval_seconds}秒内重复{count}次)")
        _log_counters[key] = 0
        return True
    else:
        _log_counters[key] = _log_counters.get(key, 0) + 1
        return False

# ========== 正则预编译 ==========
def build_cmd_regex() -> re.Pattern[str]:
    """根据配置的关键词构建触发正则，容忍"豆包豆包"前缀和语音识别问题"""
    # 基础关键词
    kw_note = re.escape(KEYWORD_NOTE)
    kw_task = re.escape(KEYWORD_TASK)

    # 语音识别可能的变体
    note_variants = [
        kw_note,           # 记笔记
        "笔记",            # 记字丢失
        "几笔记", "及笔记", "即笔记", "寄笔记",  # 同音字/近音字
        "记个笔记", "记一下笔记", "记录笔记", "记1个笔记", "记一个笔记",  # 口语化+数字
        "帮我记笔记", "帮我记个笔记", "帮我记一下笔记",  # 更口语化
        "记记笔记", "笔笔记",  # 重复字符
        "记比记",  # 方言变体
    ]

    task_variants = [
        kw_task,           # 记任务
        "任务",            # 记字丢失
        "几任务", "及任务", "即任务", "寄任务",  # 同音字/近音字
        "记个任务", "记一下任务", "记录任务", "记1个任务", "记一个任务",  # 口语化+数字
        "添加任务", "新增任务", "创建任务",  # 同义词
        "帮我记任务", "帮我记个任务", "帮我添加任务", "帮我记一下任务",  # 更口语化
        "记记任务", "任任务",  # 重复字符
        "人务", "认务", "仁务",  # 方言/近音变体
    ]

    # 构建正则模式
    note_pattern = "|".join(re.escape(v) for v in note_variants)
    task_pattern = "|".join(re.escape(v) for v in task_variants)

    # 更宽松的分隔符匹配，包括语气词和填充词
    # 支持：嗯、那个、OK等常见语气词
    filler_words = r"(?:嗯[，,\s]*|那个[，,\s]*|OK[，,\s]*|好的[，,\s]*|呃[，,\s]*)?"

    return re.compile(rf"^\s*{filler_words}(?:豆包豆包[，,:：。\s]*)?{filler_words}(?:帮我\s*)?({note_pattern}|{task_pattern})(?:[，,:：。\s吧呢啊]*)?(.+)$", re.IGNORECASE)

CMD_RE = build_cmd_regex()

def normalize_matched_keyword(matched_keyword: str) -> str:
    """将匹配到的关键词变体标准化为基础关键词"""
    matched_lower = matched_keyword.lower().strip()

    # 笔记相关的所有变体
    note_variants = [
        KEYWORD_NOTE.lower(), "笔记", "几笔记", "及笔记", "即笔记", "寄笔记",
        "记个笔记", "记一下笔记", "记录笔记", "记1个笔记", "记一个笔记",
        "帮我记笔记", "帮我记个笔记", "帮我记一下笔记",
        "记记笔记", "笔笔记", "记比记"
    ]

    # 任务相关的所有变体
    task_variants = [
        KEYWORD_TASK.lower(), "任务", "几任务", "及任务", "即任务", "寄任务",
        "记个任务", "记一下任务", "记录任务", "记1个任务", "记一个任务",
        "添加任务", "新增任务", "创建任务",
        "帮我记任务", "帮我记个任务", "帮我添加任务", "帮我记一下任务",
        "记记任务", "任任务", "人务", "认务", "仁务"
    ]

    if matched_lower in note_variants:
        return KEYWORD_NOTE
    elif matched_lower in task_variants:
        return KEYWORD_TASK
    else:
        # 如果没有匹配到，返回原始值（不应该发生，但作为后备）
        return matched_keyword

# 预编译归一化正则
NORMALIZE_NOTE_RE = re.compile(
    rf"^(豆包豆包[，,:：\s]*)?{re.escape(KEYWORD_NOTE)}[，,:：\s]*{re.escape(KEYWORD_NOTE)}[，,:：\s]*"
)
NORMALIZE_TASK_RE = re.compile(
    rf"^(豆包豆包[，,:：\s]*)?{re.escape(KEYWORD_TASK)}[，,:：\s]*{re.escape(KEYWORD_TASK)}[，,:：\s]*"
)
NORMALIZE_SPACE_RE = re.compile(r"[ \t]+")
NORMALIZE_REMOVE_RE = re.compile(r"[分享\s。．·!！?？、,.，:：;；\-]+")

# ========== 上下文状态管理 ==========
class PendingCommand:
    """等待内容的命令状态"""
    def __init__(self, command_type: str, timestamp: float):
        self.command_type = command_type  # "记笔记" 或 "记任务"
        self.timestamp = timestamp

    def is_expired(self, timeout_seconds: float = 30.0) -> bool:
        """检查命令是否已过期（默认30秒超时）"""
        import time
        return time.time() - self.timestamp > timeout_seconds

# 全局状态：等待内容的命令
pending_command: PendingCommand | None = None

# ========== 统计计数器 ==========
class DailyStats:
    """今日统计数据"""
    def __init__(self):
        self.notes_count = 0
        self.tasks_count = 0
        self.last_record_time = None
        self.date = datetime.now().strftime("%Y-%m-%d")
        # 性能监控
        self.processed_messages = 0
        self.duplicate_skipped = 0
        self.start_time = time.time()

    def reset_if_new_day(self):
        """如果是新的一天，重置计数器"""
        current_date = datetime.now().strftime("%Y-%m-%d")
        if current_date != self.date:
            self.notes_count = 0
            self.tasks_count = 0
            self.last_record_time = None
            self.date = current_date
            self.processed_messages = 0
            self.duplicate_skipped = 0
            self.start_time = time.time()

    def add_note(self):
        """添加笔记计数"""
        self.reset_if_new_day()
        self.notes_count += 1
        self.last_record_time = datetime.now()

    def add_task(self):
        """添加任务计数"""
        self.reset_if_new_day()
        self.tasks_count += 1
        self.last_record_time = datetime.now()

    def add_processed_message(self):
        """增加处理消息计数"""
        self.processed_messages += 1

    def add_duplicate_skipped(self):
        """增加跳过重复消息计数"""
        self.duplicate_skipped += 1

    def get_summary(self) -> str:
        """获取统计摘要"""
        self.reset_if_new_day()
        total = self.notes_count + self.tasks_count
        uptime = time.time() - self.start_time
        uptime_str = f"{int(uptime//3600)}h{int((uptime%3600)//60)}m"
        return f"今日记录: {total} 条 (笔记{self.notes_count}, 任务{self.tasks_count})\n运行时间: {uptime_str}, 处理: {self.processed_messages}, 跳过: {self.duplicate_skipped}"

# 全局统计实例
daily_stats = DailyStats()

# ========== 时间工具 ==========
def today() -> str:
    """获取今天的日期字符串"""
    return datetime.now().strftime("%Y-%m-%d")


def hhmm(timestamp: int | None = None) -> str:
    """获取时间字符串，支持Unix时间戳或当前时间"""
    if timestamp:
        return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
    return datetime.now().strftime("%H:%M:%S")


# ========== 文本归一化 & 去重 ==========
# 内存缓存：最近处理过的内容哈希
_recent_hashes = set()
_max_cache_size = 1000

def normalize_text(text: str) -> str:
    """清洗文本：去"分享"、合并重复前缀、统一分隔符、压缩空白"""
    result = (text or "").replace("\u200b", "").replace("分享", "")

    result = NORMALIZE_NOTE_RE.sub(f"{KEYWORD_NOTE} ", result)
    result = NORMALIZE_TASK_RE.sub(f"{KEYWORD_TASK} ", result)
    result = NORMALIZE_SPACE_RE.sub(" ", result)

    # 清理末尾的标点符号（句号、逗号、感叹号、问号等）
    result = result.strip()
    while result and result[-1] in "。，！？、；：":
        result = result[:-1].strip()

    return result


def compute_dedup_hash(text: str) -> str:
    """对去噪内容做哈希，用于去重"""
    base = normalize_text(text)
    base = NORMALIZE_REMOVE_RE.sub("", base)
    return hashlib.sha256(base.encode()).hexdigest()


def is_recently_processed(text: str) -> bool:
    """检查是否最近已处理过（内存缓存），优化去重策略"""
    global _recent_hashes

    # 对于关键词消息，使用更宽松的去重策略
    if KEYWORD_NOTE in text or KEYWORD_TASK in text:
        # 只对完全相同的内容进行去重，避免误判
        text_hash = hashlib.sha256(text.encode()).hexdigest()
    else:
        # 对于非关键词消息，使用原有的归一化去重
        text_hash = compute_dedup_hash(text)

    if text_hash in _recent_hashes:
        return True

    # 添加到缓存
    _recent_hashes.add(text_hash)

    # 限制缓存大小
    if len(_recent_hashes) > _max_cache_size:
        # 清理一半缓存
        _recent_hashes = set(list(_recent_hashes)[_max_cache_size//2:])

    return False

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


# ========== 系统通知 ==========
def send_notification(title: str, message: str) -> None:
    """发送系统通知"""
    try:
        notification.notify(
            title=title,
            message=message,
            app_name="豆包语音笔记",
            timeout=3
        )
    except Exception as e:
        logger.debug(f"发送通知失败: {e}")


# ========== 文件写入 ==========
async def append_to_file(path: Path, text: str) -> None:
    """追加文本到文件，自动创建父目录"""
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "a", encoding="utf-8") as f:
        await f.write(text)


async def write_to_obsidian(content: str, kind: str, timestamp: int | None = None) -> None:
    """统一写入接口"""
    async with WRITE_SEMAPHORE:
        try:
            if kind == KEYWORD_NOTE:
                filepath = VAULT / NOTES_DIR / f"{today()}.md"
                prefix = f"- [{hhmm(timestamp)}] "
                logger.info(f"目标文件: {filepath}")
                # 更新统计
                daily_stats.add_note()
                # 发送通知
                send_notification("📝 笔记已记录", f"{content.strip()}")
            else:
                filepath = VAULT / TASKS_DIR / f"{today()}.md"
                prefix = "- [ ] "
                logger.info(f"目标文件: {filepath}")
                # 更新统计
                daily_stats.add_task()
                # 发送通知
                send_notification("✅ 任务已添加", f"{content.strip()}")

            await append_to_file(filepath, f"{prefix}{content.strip()}\n")
            logger.info(f"写入{kind}: {content.strip()}")
        except IOError as e:
            logger.error(f"写入文件失败: {e}")
            raise

# ========== 文本提取 ==========
JSON_TEXT_KEYS = ("text", "content", "message", "delta", "display_text")


def extract_texts_from_json(obj: Any) -> list[tuple[str, int | None]]:
    """从 JSON 对象中递归提取包含关键词的文本，返回 (文本, 时间戳) 元组列表"""
    results = []

    def pick(item: Any, timestamp: int | None = None, is_user_message: bool = True) -> None:
        if isinstance(item, str):
            # 只有在是用户消息时才提取文本
            if is_user_message and (KEYWORD_NOTE in item or KEYWORD_TASK in item):
                results.append((item, timestamp))
        elif isinstance(item, list):
            for element in item:
                pick(element, timestamp, is_user_message)
        elif isinstance(item, dict):
            # 检查是否是豆包的消息（过滤掉豆包的回复）
            current_is_user_message = is_user_message
            if "user_type" in item:
                # user_type = 2 表示豆包的消息，需要过滤掉
                current_is_user_message = item["user_type"] != 2
            elif "sender_id" in item:
                # 特定的 sender_id 也可能表示豆包
                # 从日志中看到豆包的 sender_id 是 "7234781073513644036"
                current_is_user_message = item["sender_id"] != "7234781073513644036"

            # 尝试提取时间戳
            current_timestamp = None
            if "create_time" in item:
                try:
                    current_timestamp = int(item["create_time"])
                except (ValueError, TypeError):
                    pass

            # 如果没有找到时间戳，使用父级传递的时间戳
            if current_timestamp is None:
                current_timestamp = timestamp

            for key in JSON_TEXT_KEYS:
                if key in item:
                    pick(item[key], current_timestamp, current_is_user_message)
            for value in item.values():
                pick(value, current_timestamp, current_is_user_message)

    pick(obj)
    return results[:50]


def extract_texts(raw: str) -> list[tuple[str, int | None]]:
    """从字符串或 JSON 中提取文本列表，返回 (文本, 时间戳) 元组列表"""
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
            return [(re.sub(r'\\(["\\/bfnrt])', r'\1', m), None) for m in matches]
    except Exception as e:
        logger.warning(f"提取文本时出错: {e}")

    return [(text, None)]


def is_keyword_only_message(text: str) -> str | None:
    """检测是否为只包含关键词的消息，返回关键词类型或None"""
    normalized = normalize_text(text)
    if not normalized:
        return None

    # 使用与CMD_RE相同的关键词变体，但只匹配关键词部分（没有内容）
    # 构建所有可能的关键词变体
    note_variants = [
        KEYWORD_NOTE, "笔记", "几笔记", "及笔记", "即笔记", "寄笔记",
        "记个笔记", "记一下笔记", "记录笔记", "记1个笔记", "记一个笔记",
        "帮我记笔记", "帮我记个笔记", "帮我记一下笔记",
        "记记笔记", "笔笔记", "记比记"
    ]
    task_variants = [
        KEYWORD_TASK, "任务", "几任务", "及任务", "即任务", "寄任务",
        "记个任务", "记一下任务", "记录任务", "记1个任务", "记一个任务",
        "添加任务", "新增任务", "创建任务",
        "帮我记任务", "帮我记个任务", "帮我添加任务", "帮我记一下任务",
        "记记任务", "任任务", "人务", "认务", "仁务"
    ]

    all_variants = note_variants + task_variants
    variants_pattern = "|".join(re.escape(v) for v in all_variants)

    # 包含语气词和填充词的匹配
    filler_words = r"(?:嗯[，,\s]*|那个[，,\s]*|OK[，,\s]*|好的[，,\s]*|呃[，,\s]*)?"

    # 检查是否只包含关键词（可能带豆包豆包前缀和语气词）
    keyword_only_pattern = rf"^\s*{filler_words}(?:豆包豆包[，,:：。\s]*)?{filler_words}(?:帮我\s*)?({variants_pattern})(?:[，,:：。\s吧呢啊]*)?$"
    match = re.match(keyword_only_pattern, normalized, re.IGNORECASE)
    if match:
        return normalize_matched_keyword(match.group(1))
    return None


def is_content_message(text: str) -> bool:
    """检测是否为纯内容消息（不包含关键词）"""
    normalized = normalize_text(text)
    if not normalized:
        return False

    # 检查是否不包含关键词，但有实际内容
    has_keyword = KEYWORD_NOTE in normalized or KEYWORD_TASK in normalized
    has_content = len(normalized.strip()) > 0

    return has_content and not has_keyword


# ========== 消息处理 ==========
async def handle_text(source: str, raw_text: str) -> None:
    """处理文本，匹配命令并写入笔记或任务，支持分离的关键词和内容"""
    global pending_command
    import time

    try:
        candidates = extract_texts(raw_text)
        prefix_pattern = rf"^(?:豆包豆包[，,:：。\s]*)?(?:{re.escape(KEYWORD_NOTE)}|{re.escape(KEYWORD_TASK)})[：:，,。\s]+"

        for raw, msg_timestamp in candidates:
            normalized = normalize_text(raw)
            if not normalized:
                continue

            for line in normalized.splitlines():
                line = line.strip()
                if not line:
                    continue

                # 快速内存缓存检查，避免重复处理
                if is_recently_processed(line):
                    daily_stats.add_duplicate_skipped()
                    if should_log_debug(f"{source}_duplicate", 60):
                        logger.debug(f"[{source}] 最近已处理过的内容，跳过")
                    continue

                # 记录处理的消息
                daily_stats.add_processed_message()

                # 检查是否有等待中的命令已过期，如果过期则清除
                if pending_command and pending_command.is_expired():
                    if should_log_debug(f"{source}_expired", 30):
                        logger.debug(f"[{source}] 等待中的命令已过期，清除: {pending_command.command_type}")
                    pending_command = None

                # 情况1: 检查是否为只包含关键词的消息
                keyword_type = is_keyword_only_message(line)
                if keyword_type:
                    pending_command = PendingCommand(keyword_type, time.time())
                    if should_log_debug(f"{source}_keyword", 10):
                        logger.debug(f"[{source}] 检测到关键词，等待内容: {keyword_type}")
                    continue

                # 情况2: 检查是否有等待中的命令，且当前消息为纯内容
                if pending_command and is_content_message(line):
                    kind = pending_command.command_type
                    content = line.strip()

                    # 清除等待状态
                    pending_command = None

                    if should_log_debug(f"{source}_context", 5):
                        logger.debug(f"[{source}] 关联上下文: {kind} -> {content}")

                    # 去重检查
                    dedup_key = compute_dedup_hash(kind + "|" + content)
                    if is_duplicate_or_mark_seen(dedup_key, horizon_hours=DEDUP_HOURS):
                        if should_log_debug(f"{source}_duplicate_db", 60):
                            logger.debug(f"[{source}] 数据库重复内容，跳过: {content}")
                        continue

                    await write_to_obsidian(content, kind, msg_timestamp)
                    if should_log_debug(f"{source}_write", 5):
                        logger.debug(f"[{source}] 上下文关联并写入")
                    continue

                # 情况3: 传统的单条消息包含关键词和内容
                match = CMD_RE.match(line)
                if not match:
                    continue

                kind, content = normalize_matched_keyword(match.group(1)), match.group(2).strip()
                content = re.sub(prefix_pattern, "", content).strip()

                # 去重检查
                dedup_key = compute_dedup_hash(kind + "|" + content)
                if is_duplicate_or_mark_seen(dedup_key, horizon_hours=DEDUP_HOURS):
                    if should_log_debug(f"{source}_duplicate_db", 60):
                        logger.debug(f"[{source}] 数据库重复内容，跳过: {content}")
                    continue

                await write_to_obsidian(content, kind, msg_timestamp)
                if should_log_debug(f"{source}_write", 5):
                    logger.debug(f"[{source}] 传统模式命中并写入")

    except Exception as e:
        logger.error(f"处理文本时出错 [{source}]: {e}")

# ========== 页面抓取通道 ==========
async def poll_dom(page: Page) -> None:
    """DOM 轮询：扫描最近消息，增强检测能力"""
    try:
        # 多种选择器策略，提高捕获率
        selectors = [
            # 原有选择器
            f":is(div,li,article,section,p,span):has-text('{KEYWORD_NOTE}')",
            f":is(div,li,article,section,p,span):has-text('{KEYWORD_TASK}')",
            # 新增更广泛的选择器
            f"[class*='message']:has-text('{KEYWORD_NOTE}')",
            f"[class*='message']:has-text('{KEYWORD_TASK}')",
            f"[class*='chat']:has-text('{KEYWORD_NOTE}')",
            f"[class*='chat']:has-text('{KEYWORD_TASK}')",
            f"[class*='content']:has-text('{KEYWORD_NOTE}')",
            f"[class*='content']:has-text('{KEYWORD_TASK}')",
        ]

        all_texts = set()  # 用于去重

        for selector in selectors:
            try:
                nodes = page.locator(selector)
                count = await nodes.count()
                # 增加扫描范围：从最近10条增加到20条
                start = max(0, count - 20)

                for i in range(start, count):
                    try:
                        raw = await nodes.nth(i).inner_text()
                        if raw and raw not in all_texts:
                            all_texts.add(raw)
                            await handle_text("DOM", raw)
                    except Exception as e:
                        if should_log_debug("dom_extract_error", 60):
                            logger.debug(f"DOM 元素提取异常: {e}")
            except Exception as e:
                if should_log_debug("dom_selector_error", 60):
                    logger.debug(f"DOM 选择器异常 [{selector}]: {e}")

    except Exception as e:
        logger.error(f"DOM 轮询异常: {e}")


def build_mutation_observer_js() -> str:
    """构建真正实时的 MutationObserver JavaScript 代码"""
    kw_note = KEYWORD_NOTE.replace('\\', '\\\\').replace('/', '\\/')
    kw_task = KEYWORD_TASK.replace('\\', '\\\\').replace('/', '\\/')
    return f"""
(() => {{
  console.log('🚀 豆包实时监控已启动');

  const send = window.__emitMessage || (()=>{{}});
  const processed = new Set();
  let messageQueue = [];
  let isProcessing = false;

  // 实时处理消息队列
  const processQueue = async () => {{
    if (isProcessing || messageQueue.length === 0) return;
    isProcessing = true;

    while (messageQueue.length > 0) {{
      const text = messageQueue.shift();
      const hash = btoa(unescape(encodeURIComponent(text))).slice(0,20);

      if (!processed.has(hash)) {{
        processed.add(hash);
        console.log('📝 发现关键词消息:', text.slice(0, 100));
        send(text);
      }}
    }}

    isProcessing = false;
  }};

  const scanElement = (element) => {{
    if (!element || element.nodeType !== 1) return;

    const text = (element.innerText || element.textContent || '').trim();
    if (text && text.length > 0 && text.length < 4000) {{
      if (/{kw_note}|{kw_task}/.test(text)) {{
        messageQueue.push(text);
        processQueue();
      }}
    }}
  }};

  // 高频实时监控
  const observer = new MutationObserver((mutations) => {{
    mutations.forEach((mutation) => {{
      // 监控新增节点
      if (mutation.addedNodes) {{
        mutation.addedNodes.forEach((node) => {{
          if (node.nodeType === 1) {{
            scanElement(node);
            // 递归扫描所有子节点
            if (node.querySelectorAll) {{
              node.querySelectorAll('*').forEach(scanElement);
            }}
          }}
        }});
      }}

      // 监控文本内容变化
      if (mutation.type === 'characterData') {{
        const parent = mutation.target.parentElement;
        if (parent) scanElement(parent);
      }}

      // 监控属性变化（可能影响显示的文本）
      if (mutation.type === 'attributes' && mutation.target) {{
        scanElement(mutation.target);
      }}
    }});
  }});

  // 启动全面监控
  observer.observe(document.documentElement, {{
    childList: true,
    subtree: true,
    characterData: true,
    attributes: true,
    attributeFilter: ['class', 'style', 'data-*']
  }});

  // 初始全页面扫描
  document.querySelectorAll('*').forEach(scanElement);

  // 定期清理缓存
  setInterval(() => {{
    if (processed.size > 2000) {{
      const arr = Array.from(processed);
      processed.clear();
      arr.slice(-1000).forEach(h => processed.add(h));
      console.log('🧹 清理监控缓存');
    }}
  }}, 30000);

  // 监控页面焦点变化，确保不遗漏
  document.addEventListener('visibilitychange', () => {{
    if (!document.hidden) {{
      setTimeout(() => {{
        document.querySelectorAll('*').forEach(scanElement);
      }}, 1000);
    }}
  }});

  // 监控滚动事件，扫描新出现的内容
  let scrollTimeout;
  document.addEventListener('scroll', () => {{
    clearTimeout(scrollTimeout);
    scrollTimeout = setTimeout(() => {{
      const viewportElements = document.elementsFromPoint(
        window.innerWidth / 2,
        window.innerHeight / 2
      );
      viewportElements.forEach(scanElement);
    }}, 500);
  }}, {{ passive: true }});

  console.log('✅ 豆包实时监控配置完成');
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
    """向页面注入实时监控 MutationObserver"""
    try:
        await page.expose_function(
            "__emitMessage",
            lambda s: asyncio.create_task(handle_text("Observer", s))
        )
    except Exception:
        pass  # 已暴露过则忽略

    # 注入活跃状态标记
    await page.evaluate("window.__observerActive = true;")

    for frame in page.frames:
        try:
            await frame.evaluate(MUTATION_JS)
            await frame.evaluate("window.__observerActive = true;")
        except Exception as e:
            if should_log_debug("inject_frame_error", 60):
                logger.debug(f"[Frame {getattr(frame, 'url', 'unknown')}] evaluate 失败: {e}")

    logger.info("🚀 实时监控已注入页面")


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
NETWORK_URL_KEYWORDS = (
    # 原有关键词
    "samantha", "alice", "message", "chat", "conversation", "stream", "history",
    # 新增豆包相关关键词
    "doubao", "im", "chain", "single", "pull", "push", "sync", "api",
    # 通用聊天关键词
    "send", "receive", "reply", "response", "content", "text"
)


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

        # 临时调试：查看包含关键词的消息的完整数据结构
        texts = extract_texts_from_json(data)
        if texts and any(KEYWORD_NOTE in text or KEYWORD_TASK in text for text, _ in texts):
            if DEBUG:
                logger.debug(f"[Network] 包含关键词的消息数据结构: {json.dumps(data, ensure_ascii=False, indent=2)[:1000]}...")

        for text, timestamp in texts:
            await handle_text("Network", text)

        if DEBUG and texts:
            logger.debug(f"[Network] 命中 {len(texts)} 条, URL: {url}")
    except Exception as e:
        logger.debug(f"处理网络响应异常: {e}")


async def run_polling_loop(page: Page) -> None:
    """运行轻量级轮询循环，主要依赖实时监控"""
    logger.info(f"开始实时监听...（备用轮询间隔 {POLL_INTERVAL}s）")

    last_activity_time = time.time()
    consecutive_empty_polls = 0

    while True:
        try:
            # 轻量级备用扫描，主要依赖 MutationObserver
            # 只在必要时进行 DOM 扫描
            if consecutive_empty_polls > 20:  # 长时间无活动时才进行备用扫描
                await poll_dom(page)
                consecutive_empty_polls = 0

            # 网络监听保持活跃
            # brute_scrape 改为轻量级检查
            await lightweight_check(page)

            # 检查是否有新活动
            current_stats_total = daily_stats.notes_count + daily_stats.tasks_count
            if hasattr(run_polling_loop, '_last_total'):
                if current_stats_total > run_polling_loop._last_total:
                    last_activity_time = time.time()
                    consecutive_empty_polls = 0
                    logger.info(f"✅ 检测到新记录！总计: {current_stats_total}")
                else:
                    consecutive_empty_polls += 1
            else:
                run_polling_loop._last_total = current_stats_total

            run_polling_loop._last_total = current_stats_total

            # 智能轮询间隔：主要依赖实时监控，轮询间隔可以更长
            if settings.SMART_POLLING:
                time_since_activity = time.time() - last_activity_time
                if time_since_activity < 300:  # 5分钟内有活动
                    poll_interval = settings.FAST_POLL_INTERVAL * 2  # 实时监控下可以放宽
                elif consecutive_empty_polls > 10:
                    poll_interval = settings.SLOW_POLL_INTERVAL
                else:
                    poll_interval = POLL_INTERVAL
            else:
                poll_interval = POLL_INTERVAL

            if should_log_debug("polling_info", 300):  # 降低日志频率
                logger.debug(f"轮询间隔: {poll_interval}s, 空轮询次数: {consecutive_empty_polls}, 实时监控活跃")

        except Exception as e:
            if "has been closed" in str(e):
                logger.info("检测到页面关闭，退出。")
                break
            if should_log_debug("polling_error", 30):
                logger.debug(f"轮询异常: {e}")

        await asyncio.sleep(poll_interval)


async def lightweight_check(page: Page) -> None:
    """轻量级检查，确保页面活跃"""
    try:
        # 简单的页面活跃性检查
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        # 确保 MutationObserver 仍在运行
        is_observer_active = await page.evaluate("""
            () => {
                return window.__observerActive || false;
            }
        """)

        if not is_observer_active:
            logger.warning("⚠️ 实时监控可能失效，重新注入...")
            await inject_observer_to_page(page)

    except Exception as e:
        if should_log_debug("lightweight_check_error", 60):
            logger.debug(f"轻量级检查异常: {e}")


# ========== 菜单栏图标 ==========
def create_icon_image() -> Image.Image:
    """创建菜单栏图标"""
    # 创建一个简单的图标
    width = height = 64
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # 绘制一个简单的笔记本图标
    draw.rectangle([10, 10, 54, 54], fill=(70, 130, 180, 255), outline=(50, 100, 150, 255), width=2)
    draw.line([20, 20, 44, 20], fill=(255, 255, 255, 255), width=2)
    draw.line([20, 28, 44, 28], fill=(255, 255, 255, 255), width=2)
    draw.line([20, 36, 44, 36], fill=(255, 255, 255, 255), width=2)
    draw.line([20, 44, 44, 44], fill=(255, 255, 255, 255), width=2)

    return image


def create_menu():
    """创建菜单栏图标的右键菜单"""
    def show_stats():
        """显示统计信息"""
        stats = daily_stats.get_summary()
        last_time = ""
        if daily_stats.last_record_time:
            last_time = f"\n最后记录: {daily_stats.last_record_time.strftime('%H:%M:%S')}"

        send_notification("📊 今日统计", f"{stats}{last_time}")

    def quit_app(icon, item):
        """退出应用"""
        icon.stop()
        os._exit(0)

    return pystray.Menu(
        pystray.MenuItem("豆包语音笔记", lambda: None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("📊 查看统计", show_stats),
        pystray.MenuItem("🔄 重置统计", lambda: daily_stats.__init__()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("❌ 退出", quit_app)
    )


def start_system_tray():
    """启动系统托盘图标（macOS需要在主线程中运行）"""
    try:
        # 在 macOS 上，暂时禁用系统托盘以避免崩溃
        # 系统托盘需要在主线程中运行，但我们的主线程被 asyncio 占用
        logger.info("系统托盘图标已禁用（避免 macOS 崩溃）")
        logger.info("可以通过右键菜单栏图标查看统计（功能暂时不可用）")
        return None

        # 原始代码保留，待后续优化
        # icon = pystray.Icon(
        #     "doubao_voice_notes",
        #     create_icon_image(),
        #     "豆包语音笔记",
        #     create_menu()
        # )
        #
        # # 在单独的线程中运行图标
        # def run_icon():
        #     icon.run()
        #
        # icon_thread = threading.Thread(target=run_icon, daemon=True)
        # icon_thread.start()
        # logger.info("系统托盘图标已启动")
        #
        # return icon
    except Exception as e:
        logger.error(f"启动系统托盘图标失败: {e}")
        return None


# ========== 启动横幅 ==========
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

    # 启动系统托盘图标
    tray_icon = start_system_tray()

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