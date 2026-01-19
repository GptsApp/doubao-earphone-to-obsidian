#!/usr/bin/env python3
"""
GitHub Social Preview Image Generator
Creates a 1280x640px image for doubao-earphone-to-obsidian repository
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_social_preview():
    # Image dimensions (GitHub recommended: 1280x640)
    width, height = 1280, 640

    # Create image with gradient background
    img = Image.new('RGB', (width, height), '#1a1a2e')
    draw = ImageDraw.Draw(img)

    # Create gradient background
    for y in range(height):
        # Gradient from dark blue to purple
        r = int(26 + (y / height) * 30)  # 26 -> 56
        g = int(26 + (y / height) * 20)  # 26 -> 46
        b = int(46 + (y / height) * 40)  # 46 -> 86
        color = (r, g, b)
        draw.line([(0, y), (width, y)], fill=color)

    # Try to load fonts, fallback to default if not available
    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 72)
        subtitle_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 36)
        desc_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
    except:
        # Fallback fonts
        title_font = ImageFont.load_default()
        subtitle_font = ImageFont.load_default()
        desc_font = ImageFont.load_default()

    # Colors
    white = '#FFFFFF'
    accent = '#00D4FF'  # Bright cyan
    secondary = '#FFB800'  # Orange

    # Main title
    title = "🎙️ Doubao Earphone Assistant"
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    title_x = (width - title_width) // 2
    draw.text((title_x, 80), title, fill=white, font=title_font)

    # Subtitle
    subtitle = "Real-time Voice Assistant for AI Earphones & Obsidian"
    subtitle_bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
    subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
    subtitle_x = (width - subtitle_width) // 2
    draw.text((subtitle_x, 180), subtitle, fill=accent, font=subtitle_font)

    # Flow diagram elements
    flow_y = 280

    # Earphone icon (circle with headphone symbol)
    earphone_x = 200
    draw.ellipse([earphone_x-40, flow_y-40, earphone_x+40, flow_y+40],
                fill=accent, outline=white, width=3)
    draw.text((earphone_x-25, flow_y-15), "🎧", font=desc_font)

    # Arrow 1
    arrow1_start = earphone_x + 50
    arrow1_end = arrow1_start + 120
    draw.line([arrow1_start, flow_y, arrow1_end, flow_y], fill=white, width=4)
    draw.polygon([arrow1_end, flow_y, arrow1_end-15, flow_y-8, arrow1_end-15, flow_y+8],
                fill=white)

    # Voice processing icon
    voice_x = arrow1_end + 60
    draw.rectangle([voice_x-50, flow_y-40, voice_x+50, flow_y+40],
                  fill=secondary, outline=white, width=3)
    draw.text((voice_x-20, flow_y-15), "🧠", font=desc_font)

    # Arrow 2
    arrow2_start = voice_x + 60
    arrow2_end = arrow2_start + 120
    draw.line([arrow2_start, flow_y, arrow2_end, flow_y], fill=white, width=4)
    draw.polygon([arrow2_end, flow_y, arrow2_end-15, flow_y-8, arrow2_end-15, flow_y+8],
                fill=white)

    # Obsidian icon
    obsidian_x = arrow2_end + 60
    draw.ellipse([obsidian_x-40, flow_y-40, obsidian_x+40, flow_y+40],
                fill='#7C3AED', outline=white, width=3)
    draw.text((obsidian_x-25, flow_y-15), "📝", font=desc_font)

    # Labels under icons
    label_y = flow_y + 70
    draw.text((earphone_x-35, label_y), "Doubao\nEarphones",
             fill=white, font=desc_font, anchor="mm")
    draw.text((voice_x-25, label_y), "AI Voice\nProcessing",
             fill=white, font=desc_font, anchor="mm")
    draw.text((obsidian_x-25, label_y), "Obsidian\nNotes",
             fill=white, font=desc_font, anchor="mm")

    # Key features at bottom
    features_y = 480
    features = [
        "✨ 30+ Speech Variations",
        "⚡ Real-time Sync",
        "🚫 Smart Deduplication",
        "🌐 Cross-platform"
    ]

    feature_width = width // len(features)
    for i, feature in enumerate(features):
        feature_x = i * feature_width + feature_width // 2
        feature_bbox = draw.textbbox((0, 0), feature, font=desc_font)
        feature_text_width = feature_bbox[2] - feature_bbox[0]
        draw.text((feature_x - feature_text_width // 2, features_y),
                 feature, fill=white, font=desc_font)

    # GitHub info at bottom
    github_text = "github.com/GptsApp/doubao-earphone-to-obsidian"
    github_bbox = draw.textbbox((0, 0), github_text, font=desc_font)
    github_width = github_bbox[2] - github_bbox[0]
    github_x = (width - github_width) // 2
    draw.text((github_x, 570), github_text, fill=accent, font=desc_font)

    return img

if __name__ == "__main__":
    # Create the preview image
    preview_img = create_social_preview()

    # Save the image
    output_path = "social-preview.png"
    preview_img.save(output_path, "PNG", quality=95)
    print(f"✅ Social preview image created: {output_path}")
    print(f"📐 Dimensions: 1280x640px")
    print(f"🎨 Style: Icon flow diagram with gradient background")