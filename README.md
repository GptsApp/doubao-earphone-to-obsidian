# Doubao Earphone To Obsidian

用豆包耳机助手，把灵感直接说进 Obsidian。

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
git clone https://github.com/你的用户名/doubao-earphone-to-obsidian.git
cd doubao-earphone-to-obsidian

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

### 2. 启动并配置（自动引导）

```bash
# 直接运行程序
python main.py
```

**首次运行时，程序会自动引导你设置 Obsidian 仓库路径：**

```
==================================================
  豆包耳机助手 - Obsidian 同步工具
==================================================

使用方法：
  1. 说「豆包豆包，记笔记，<内容>」记录笔记
  2. 说「豆包豆包，记任务，<内容>」记录任务

查看结果：
  笔记保存位置: {OBSIDIAN_VAULT}/{NOTES_DIR}
  任务保存位置: {OBSIDIAN_VAULT}/{TASKS_DIR}

--------------------------------------------------
如果这个工具对你有帮助，欢迎关注开发者：
  @WeWill_Rocky  https://x.com/WeWill_Rocky
--------------------------------------------------

==================================================
  ⚠️  Obsidian 仓库路径未设置或不存在
==================================================

请选择设置方式：
  1. 输入 Obsidian 仓库的绝对路径
  2. 查找常见的 Obsidian 仓库位置
  3. 退出程序

请输入选项 (1/2/3):
```

#### 选项 1：手动输入路径

输入你的 Obsidian 仓库的完整路径，例如：

**macOS:**
```
/Users/zhoupeiyi/Documents/Obsidian/MyVault
```

**Windows:**
```
C:\Users\zhoupeiyi\Documents\Obsidian\MyVault
```

#### 选项 2：自动查找

程序会在常见位置搜索 Obsidian 仓库：

- `~/Documents/Obsidian/`
- `~/Dropbox/Obsidian/`
- `~/OneDrive/Obsidian/`
- `~/Library/Mobile Documents/iCloud~obsidian/`

找到后会自动显示所有可用的仓库。

#### 如何找到你的 Obsidian 仓库路径？

1. **在 Obsidian App 中查看**：
   - 打开 Obsidian
   - 点击左侧边栏的仓库图标
   - 选择 "关于"
   - 查看 "当前仓库" 路径

2. **在文件系统中查找**：
   - Obsidian 仓库的根目录下有一个 `.obsidian` 文件夹
   - 这是 Obsidian 仓库的标识

3. **常见位置**：
   - macOS: `~/Documents/Obsidian/仓库名/`
   - Windows: `C:\Users\用户名\Documents\Obsidian\仓库名\`
   - Linux: `~/Documents/Obsidian/仓库名/`

### 3. 配置豆包聊天 URL（可选）

编辑 `.env` 文件：

```bash
nano .env
```

修改 `CHAT_URL` 为你的豆包聊天页面 URL（登录后从浏览器地址栏复制）：

```bash
CHAT_URL=https://www.doubao.com/chat/624642496948226
```

### 4. 首次运行（登录）

```bash
python main.py
```

首次运行会打开浏览器，请登录你的豆包账号。登录成功后浏览器会自动关闭。

### 5. 启动服务

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
nohup python main.py > doubao-earphone-to-obsidian.log 2>&1 &

# 或使用 screen/tmux
screen -S doubao-earphone-to-obsidian
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
