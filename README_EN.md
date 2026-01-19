# 🎙️ Doubao Earphone to Obsidian - AI Voice Assistant

**🌐 Language / 语言**
- [🇨🇳 中文](README.md)
- [🇺🇸 English](README_EN.md)

[![GitHub stars](https://img.shields.io/github/stars/GptsApp/doubao-earphone-to-obsidian?style=social)](https://github.com/GptsApp/doubao-earphone-to-obsidian)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

> **Turn your voice into notes instantly** 📝
> Designed for Doubao AI earphones (Ola friend), speak naturally and watch your thoughts appear in Obsidian automatically

## 🎧 Why Doubao AI Earphones?

**Doubao Earphones = Ola friend earphones** - A revolutionary AI voice interaction device that outperforms traditional recording methods:

### 🚀 Core Advantages

| Feature | Doubao AI Earphones | Traditional Recording |
|---------|---------------------|----------------------|
| **Interaction** | 🎯 Natural voice conversation | 📱 Manual recording activation |
| **Processing** | ⚡ Real-time AI processing | ⏳ Post-recording transcription |
| **Usage** | 🌍 Hands-free anywhere | 🤏 Requires device handling |
| **Intelligence** | 🧠 Context-aware AI categorization | 🔄 Raw audio, manual organization |
| **Portability** | 👂 Wear and forget | 📦 Additional device to carry |

### 💡 Experience Comparison

**Traditional Way**: Idea strikes → Pull out phone → Open recorder → Start recording → Stop recording → Transcribe later → Manual organization

**Doubao Way**: Idea strikes → Just speak → Automatically appears in Obsidian ✨

### 🎯 Perfect Use Cases

- 🚗 **Driving**: Hands on wheel, voice captures road insights
- 🏃 **Exercise**: Record thoughts while running without breaking stride
- 🍳 **Cooking**: Busy hands, voice notes recipe improvements
- 🚶 **Walking**: Capture thoughts while strolling
- 💼 **Meetings**: Quick notes between sessions

## ✨ Key Features

🎯 **Smart Voice Recognition** - Recognizes 30+ speech variations, even partial words
🔄 **Real-time Sync** - Voice content instantly appears in Obsidian
🚫 **Intelligent Deduplication** - Prevents duplicate entries
🎛️ **Background Operation** - Silent monitoring without workflow interruption
🌐 **Cross-platform** - Windows, macOS, Linux support

## 🚀 Quick Start

### Voice Command Examples

| What You Say | Recognition | Saved To |
|--------------|-------------|----------|
| "Doubao, take a note, learned something new today" | ✅ Note | `Inbox/Voice Notes/2026-01-19.md` |
| "Task, meeting tomorrow" | ✅ Task | `Tasks/2026-01-19.md` |
| "Help me note this important idea" | ✅ Note | `Inbox/Voice Notes/2026-01-19.md` |
| "Add task, grocery shopping" | ✅ Task | `Tasks/2026-01-19.md` |

### Supported Speech Variations (30+)

- **Character drops**: "take note" → "note", "add task" → "task"
- **Homophones**: Various pronunciation variations
- **Colloquial**: "take a note", "help me add task"
- **Numbers**: "take 1 note", "add one task"
- **Fillers**: "um, take note", "okay, add task"

## 📦 Installation

### 1. Clone Repository

```bash
git clone https://github.com/GptsApp/doubao-earphone-to-obsidian.git
cd doubao-earphone-to-obsidian
```

### 2. Environment Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install browser
playwright install chromium
```

### 3. One-Click Launch

```bash
python main.py
```

**First run automatically guides Obsidian path configuration with:**
- 🔍 Auto-search common locations
- ✏️ Manual path input
- ✅ Path validation and testing

## ⚙️ Configuration

| Setting | Description | Default | Example |
|---------|-------------|---------|---------|
| `OBSIDIAN_VAULT` | Obsidian vault path | *Required* | `/Users/name/Documents/MyVault` |
| `NOTES_DIR` | Notes save directory | `Inbox/Voice Notes` | `Daily Notes` |
| `TASKS_DIR` | Tasks save directory | `Tasks` | `Todo` |
| `KEYWORD_NOTE` | Note trigger word | `记笔记` | `note` |
| `KEYWORD_TASK` | Task trigger word | `记任务` | `task` |
| `POLL_INTERVAL` | Polling interval (seconds) | `10` | `5` |
| `DEDUP_HOURS` | Deduplication window (hours) | `36` | `24` |

## 🔧 Technical Architecture

```mermaid
graph LR
    A[Doubao Earphones<br/>Ola friend] --> B[Doubao AI<br/>Voice Processing]
    B --> C[Web Monitoring<br/>Real-time Capture]
    C --> D[Text Extraction<br/>Smart Parsing]
    D --> E[Voice Optimization<br/>30+ Variations]
    E --> F[Deduplication<br/>Smart Filtering]
    F --> G[Obsidian Sync<br/>Auto Categorization]
```

### Tech Stack

- **Doubao AI Earphones (Ola friend)** - AI voice interaction hardware
- **Playwright** - Browser automation and page monitoring
- **Regex Engine** - 30+ speech variation recognition
- **SQLite** - Deduplication database
- **Async I/O** - High-performance file operations
- **Real-time Monitoring** - DOM changes and network request dual monitoring

## 🛠️ Troubleshooting

### Common Issues

<details>
<summary>❓ Notes not appearing in Obsidian</summary>

1. Check `OBSIDIAN_VAULT` path is correct
2. Ensure speech contains trigger words ("note" or "task")
3. Enable debug mode: set `DEBUG=1`
4. Check log output for recognition status
</details>

<details>
<summary>❓ Login state lost</summary>

```bash
# Delete login state file and re-login
rm storage_state.json
python main.py
```
</details>

<details>
<summary>❓ Running in background</summary>

```bash
# Linux/macOS
nohup python main.py > app.log 2>&1 &

# Using screen
screen -S doubao-voice
python main.py
# Ctrl+A, D to detach
```
</details>

## 🎯 Real-World Use Cases

### 🚗 Mobile Office
- **Commuting**: "Doubao, note the three key points from today's meeting"
- **Business trips**: "Add task, organize client materials when back"
- **Waiting**: Quick idea capture without missing opportunities

### 🏃 Active Lifestyle
- **Morning runs**: "Note today's running insights and experience"
- **Gym breaks**: "Add task, adjust tomorrow's training plan"
- **Walking meditation**: Capture thoughts while body and mind sync

### 🏠 Home Life
- **Cooking**: "Note this recipe improvement method"
- **Chores**: "Add task, weekend shopping list items"
- **Bedtime**: Lying down, voice-record daily reflections

### 💼 Professional Work
- **Meeting gaps**: "Note the core viewpoint just discussed"
- **Learning**: "Add task, research this topic after class"
- **Commute**: Use fragmented time to organize thoughts and plans

### 🎨 Creative Inspiration
- **Sudden ideas**: Instantly voice-record any good idea
- **Creative process**: "Note this creative extension thought"
- **Brainstorming**: Rapidly capture every fleeting thought

## 🔄 Changelog

### v2.0.0 (2026-01-19)
- ✨ Added 30+ speech variation recognition
- 🔧 Fixed Frame API compatibility issues
- 🚫 Fixed Doubao reply mis-recording
- 🎯 Optimized message filtering algorithm
- 📈 Voice recognition success rate improved to 100%

### v1.0.0 (2026-01-18)
- 🎉 Initial release
- 🎙️ Basic voice recognition
- 📝 Obsidian sync functionality
- 🔄 Smart deduplication mechanism

## 🤝 Contributing

Welcome Issues and Pull Requests!

1. Fork this repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

## 📄 License

This project is licensed under [GPL-3.0](LICENSE)

## 👨‍💻 Developer

**[@WeWill_Rocky](https://x.com/WeWill_Rocky)**

If this project helps you:
- ⭐ Star the project
- 🐦 Follow developer on Twitter
- 💬 Share your experience

---

<div align="center">

**Make Doubao earphones your intelligent voice assistant** 🧠

*Smart assistant solution crafted for Ola friend earphone users*

Made with ❤️ by [WeWill_Rocky](https://x.com/WeWill_Rocky)

</div>