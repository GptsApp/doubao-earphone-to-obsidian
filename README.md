# Doubao Voice Notes

用豆包语音助手，把灵感直接说进 Obsidian。

> "豆包豆包，记笔记，明天要买咖啡"
>
> 笔记自动出现在你的 Obsidian 里。

## 它能做什么

- 对豆包说"记笔记"，内容自动写入 Obsidian 笔记
- 对豆包说"记任务"，内容自动写入 Obsidian 任务清单
- 智能去重，同一句话不会重复记录
- 后台静默运行，不打扰你的工作

## 快速开始

### 1. 安装依赖

```bash
# 克隆项目
git clone https://github.com/你的用户名/doubao-voice-notes.git
cd doubao-voice-notes

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

### 2. 配置

```bash
# 复制配置模板
cp .env.example .env

# 编辑配置文件
nano .env  # 或用你喜欢的编辑器
```

必须配置的项目：
- `OBSIDIAN_VAULT`: 你的 Obsidian 仓库路径
- `CHAT_URL`: 豆包聊天页面 URL（登录后从浏览器复制）

### 3. 首次运行（登录）

```bash
python main.py
```

首次运行会打开浏览器，请登录你的豆包账号。登录成功后浏览器会自动关闭。

### 4. 启动服务

```bash
python main.py
```

登录后再次运行，服务会在后台静默监听（不显示浏览器窗口）。

## 使用方法

打开豆包 App 或网页，对它说：

| 说法 | 效果 |
|------|------|
| "豆包豆包，记笔记，今天天气真好" | 写入笔记文件 |
| "豆包豆包，记任务，明天开会" | 写入任务清单 |

笔记会保存到：`{OBSIDIAN_VAULT}/{NOTES_DIR}/2025-01-15.md`

任务会保存到：`{OBSIDIAN_VAULT}/{TASKS_DIR}/2025-01-15.md`

## 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `OBSIDIAN_VAULT` | Obsidian 仓库路径 | 必填 |
| `NOTES_DIR` | 笔记目录 | `Inbox/Voice Notes` |
| `TASKS_DIR` | 任务目录 | `Tasks` |
| `CHAT_URL` | 豆包聊天 URL | 必填 |
| `KEYWORD_NOTE` | 笔记触发词 | `记笔记` |
| `KEYWORD_TASK` | 任务触发词 | `记任务` |
| `POLL_INTERVAL` | 轮询间隔(秒) | `10` |
| `DEDUP_HOURS` | 去重时间窗口(小时) | `36` |
| `DEBUG` | 调试模式 | `0` |

## 常见问题

### Q: 登录后还是打开浏览器窗口？

删除 `storage_state.json` 文件重新登录：

```bash
rm storage_state.json
python main.py
```

### Q: 笔记没有写入？

1. 检查 `OBSIDIAN_VAULT` 路径是否正确
2. 确保说的是"记笔记"或"记任务"开头
3. 开启 `DEBUG=1` 查看详细日志

### Q: 如何后台运行？

```bash
# Linux/macOS
nohup python main.py > doubao.log 2>&1 &

# 或使用 screen/tmux
screen -S doubao
python main.py
# Ctrl+A, D 分离
```

## 技术原理

1. 使用 Playwright 在后台运行浏览器
2. 监听豆包网页的 DOM 变化和网络请求
3. 提取包含关键词的文本
4. 去重后写入 Obsidian 文件

## 开发者

[@WeWill_Rocky](https://x.com/WeWill_Rocky)

## 许可证

GPL-3.0 License
