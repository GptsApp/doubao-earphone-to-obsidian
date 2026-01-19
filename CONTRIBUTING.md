# Contributing to Doubao Earphone to Obsidian

Thank you for your interest in contributing to Doubao Earphone to Obsidian! This document provides guidelines for contributing to the project.

## 🚀 Quick Start for Contributors

### Development Setup

1. **Fork and Clone**
   ```bash
   git clone https://github.com/YOUR_USERNAME/doubao-earphone-to-obsidian.git
   cd doubao-earphone-to-obsidian
   ```

2. **Environment Setup**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   playwright install chromium
   ```

3. **Configuration**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

## 🎯 Areas for Contribution

### High Priority
- **Multi-language Support**: Add support for other AI voice assistants
- **Cross-platform GUI**: Native desktop applications
- **Plugin System**: Extensible architecture for different note-taking apps
- **Voice Processing**: Improve speech recognition accuracy

### Medium Priority
- **Documentation**: API docs, tutorials, video guides
- **Testing**: Unit tests, integration tests, CI/CD
- **Performance**: Optimize memory usage and response time
- **Security**: Audit and improve data handling

### Low Priority
- **Themes**: UI customization options
- **Analytics**: Usage statistics and insights
- **Integrations**: Support for more note-taking apps

## 🔧 Technical Architecture

### Core Components

```
main.py              # Main application entry point
├── Settings         # Configuration management (Pydantic)
├── VoiceMonitor     # Web scraping and voice detection
├── ObsidianWriter   # File writing and organization
├── DeduplicationDB  # SQLite-based duplicate prevention
└── SystemTray       # Desktop integration
```

### Key Technologies
- **Playwright**: Browser automation for web scraping
- **Pydantic**: Configuration validation and settings management
- **SQLite**: Local database for deduplication
- **AsyncIO**: Asynchronous operations for performance
- **PyStray**: System tray integration

## 📝 Code Style

### Python Guidelines
- Follow PEP 8 style guide
- Use type hints for all functions
- Add docstrings for public methods
- Keep functions under 50 lines when possible

### Example Code Style
```python
async def process_voice_message(self, message: str) -> bool:
    """
    Process a voice message and determine if it should be saved.

    Args:
        message: The voice message text to process

    Returns:
        True if message was processed and saved, False otherwise
    """
    if not self._is_valid_message(message):
        return False

    # Process the message...
    return True
```

## 🧪 Testing

### Running Tests
```bash
# Run all tests
python -m pytest

# Run with coverage
python -m pytest --cov=main

# Run specific test file
python -m pytest tests/test_voice_recognition.py
```

### Writing Tests
- Place tests in the `tests/` directory
- Use descriptive test names: `test_voice_recognition_handles_partial_words`
- Mock external dependencies (web requests, file system)
- Test both success and failure cases

## 🐛 Bug Reports

### Before Submitting
1. Check existing issues for duplicates
2. Test with the latest version
3. Gather system information

### Bug Report Template
```markdown
**Environment:**
- OS: [e.g., macOS 13.0, Windows 11, Ubuntu 22.04]
- Python version: [e.g., 3.9.7]
- Doubao Earphone to Obsidian version: [e.g., v2.0.0]

**Steps to Reproduce:**
1. Go to '...'
2. Click on '....'
3. Scroll down to '....'
4. See error

**Expected Behavior:**
A clear description of what you expected to happen.

**Actual Behavior:**
A clear description of what actually happened.

**Logs:**
```
Paste relevant log output here
```

**Additional Context:**
Add any other context about the problem here.
```

## ✨ Feature Requests

### Before Submitting
1. Check if the feature already exists
2. Search existing feature requests
3. Consider if it fits the project scope

### Feature Request Template
```markdown
**Problem Statement:**
A clear description of the problem this feature would solve.

**Proposed Solution:**
A detailed description of what you want to happen.

**Alternatives Considered:**
A description of any alternative solutions you've considered.

**Additional Context:**
Add any other context or screenshots about the feature request.
```

## 🔄 Pull Request Process

### Before Submitting
1. Create a feature branch: `git checkout -b feature/amazing-feature`
2. Make your changes with clear, atomic commits
3. Add tests for new functionality
4. Update documentation if needed
5. Ensure all tests pass

### PR Guidelines
- **Title**: Use a clear, descriptive title
- **Description**: Explain what changes you made and why
- **Testing**: Describe how you tested your changes
- **Breaking Changes**: Clearly mark any breaking changes

### PR Template
```markdown
## Description
Brief description of changes made.

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Testing
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
- [ ] I have tested this change manually

## Checklist
- [ ] My code follows the style guidelines of this project
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
```

## 📚 Documentation

### Types of Documentation
- **README**: Project overview and quick start
- **API Docs**: Function and class documentation
- **Tutorials**: Step-by-step guides
- **Architecture**: Technical design documents

### Documentation Standards
- Use clear, concise language
- Include code examples
- Keep documentation up-to-date with code changes
- Use proper markdown formatting

## 🏷️ Release Process

### Version Numbering
We follow [Semantic Versioning](https://semver.org/):
- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Release Checklist
1. Update version numbers
2. Update CHANGELOG.md
3. Create release notes
4. Tag the release
5. Update documentation

## 🤝 Community Guidelines

### Code of Conduct
- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow
- Maintain a professional tone

### Communication Channels
- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: General questions and ideas
- **Twitter**: [@WeWill_Rocky](https://x.com/WeWill_Rocky) for updates

## 🎉 Recognition

Contributors will be recognized in:
- README.md contributors section
- Release notes
- Project documentation

Thank you for contributing to Doubao Earphone to Obsidian! 🚀