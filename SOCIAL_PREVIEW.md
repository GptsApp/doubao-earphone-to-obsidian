# GitHub Social Preview Setup

## 📸 Social Preview Image

The `social-preview.png` file is designed for GitHub's social media preview feature.

### 🎨 Design Features

- **Dimensions**: 1280×640px (GitHub recommended)
- **Style**: Icon flow diagram with gradient background
- **Color Scheme**: Dark blue to purple gradient with cyan accents
- **Elements**:
  - 🎧 Doubao Earphones → 🧠 AI Processing → 📝 Obsidian Notes
  - Key features highlighted at bottom
  - Repository URL for easy access

### 📋 How to Use

1. Go to your GitHub repository settings
2. Navigate to "General" → "Social preview"
3. Click "Upload an image"
4. Upload the `social-preview.png` file
5. Save changes

### 🔄 Regenerating the Image

If you need to modify the preview image:

```bash
python create_social_preview.py
```

This will regenerate `social-preview.png` with any updates you make to the script.

### 📐 Technical Specs

- **Format**: PNG
- **Size**: ~57KB
- **Resolution**: 1280×640px
- **Color Profile**: RGB
- **Background**: Gradient (Dark blue #1a1a2e to purple)
- **Text**: White and cyan (#00D4FF)
- **Accents**: Orange (#FFB800) and purple (#7C3AED)

The image is optimized for social media sharing on platforms like Twitter, LinkedIn, and GitHub's own social preview system.