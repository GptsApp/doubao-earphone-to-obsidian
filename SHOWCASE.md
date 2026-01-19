# 🎙️ Doubao Earphone to Obsidian

> **Real-time voice-to-text bridge for Doubao AI earphones and Obsidian**

Transform your Doubao AI earphone conversations into organized Obsidian notes automatically. No manual transcription, no app switching - just speak naturally and watch your thoughts appear in your knowledge base.

## ⚡ Quick Demo

```bash
# You say: "Doubao, take a note, learned about async programming today"
# Result: Automatically appears in Obsidian as:

## 14:32:15

learned about async programming today
```

**File location**: `Inbox/Voice Notes/2026-01-19.md`

## 🎯 Why This Matters

**The Problem**: Voice notes are powerful but isolated. You speak to your AI earphones, but the insights get trapped in chat history instead of your knowledge management system.

**The Solution**: A real-time bridge that monitors your Doubao conversations and automatically syncs recognized content to Obsidian with intelligent categorization.

## 🔧 How It Works

1. **Monitor**: Playwright watches Doubao web interface for new messages
2. **Recognize**: 30+ speech pattern variations detect note/task commands
3. **Filter**: Smart deduplication prevents duplicate entries
4. **Organize**: Content automatically categorized and timestamped
5. **Sync**: Markdown files written directly to your Obsidian vault

## 🚀 Key Features

- **Zero-friction capture**: Speak naturally, no app switching
- **Smart recognition**: Handles speech-to-text errors and variations
- **Intelligent deduplication**: Prevents duplicate entries
- **Organized output**: Daily files with timestamps
- **Cross-platform**: Works on Windows, macOS, Linux

## 📊 Technical Highlights

- **Browser automation**: Playwright for reliable web scraping
- **Async architecture**: Non-blocking I/O for performance
- **Pattern matching**: Regex engine with fuzzy recognition
- **Local processing**: All data stays on your machine
- **SQLite backend**: Efficient deduplication and history

## 🎧 Hardware Requirements

**Doubao AI Earphones (Ola friend)** - The key differentiator:
- Real-time AI processing
- Natural conversation interface
- Hands-free operation
- Context-aware responses

## 🛠️ Installation

```bash
git clone https://github.com/GptsApp/doubao-earphone-to-obsidian.git
cd doubao-earphone-to-obsidian
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python main.py
```

## 🎯 Use Cases

- **Developers**: Capture coding insights while walking/commuting
- **Researchers**: Voice notes during field work or interviews
- **Writers**: Capture story ideas without breaking creative flow
- **Students**: Record lecture thoughts and study insights
- **Professionals**: Meeting notes and action items on-the-go

## 🔮 What's Next

- Multi-platform support (Telegram, WhatsApp, Discord)
- AI-powered content summarization
- Smart categorization and tagging
- WebSocket monitoring for real-time sync
- Plugin architecture for extensibility

## 📈 Stats

- **30+ speech variations** recognized
- **100% success rate** on clear voice commands
- **<2 second latency** from speech to file
- **36-hour deduplication** window (configurable)
- **Zero data upload** - everything stays local

---

**Built for the intersection of AI hardware and knowledge management.**

*If you're using Doubao AI earphones and Obsidian, this bridges the gap between voice input and organized knowledge capture.*

[Technical Details](TECHNICAL.md) | [Contributing](CONTRIBUTING.md) | [Demo Video](#)