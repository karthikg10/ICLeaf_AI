# backend/app/content_manager.py
import os
import uuid
import json
import asyncio
import shutil
import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from pptx import Presentation
from pptx.util import Inches, Pt
import csv
import xlsxwriter
import re
from .models import (
    GeneratedContent, GenerateContentRequest,
    ContentType, ContentStatus, FlashcardConfig, QuizConfig,
    AssessmentConfig, VideoConfig, AudioConfig, CompilerConfig,
    PDFConfig, PPTConfig
)
from . import rag_store_chromadb as rag
from . import web_cloud as wc
from . import deps
from . import media_generator
from openai import OpenAI

# In-memory content storage (in production, use database)
_content_storage: Dict[str, GeneratedContent] = {}

# Download tracking (in production, use database)
_download_tracking: Dict[str, List[Dict]] = {}  # contentId -> [{"timestamp": ..., "userId": ..., "ip": ...}]

# Content generation client
content_client = OpenAI(api_key=deps.OPENAI_API_KEY) if deps.OPENAI_API_KEY else None

def generate_content_id() -> str:
    """Generate a unique content ID."""
    return str(uuid.uuid4())

def clean_markdown_formatting(text: str) -> str:
    """Remove markdown formatting from text."""
    # Remove headers (###, ##, #)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    
    # Remove bold formatting (**text** or __text__)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    
    # Remove italic formatting (*text* or _text_)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'_(.*?)_', r'\1', text)
    
    # Remove code blocks (```text```)
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    
    # Remove inline code (`text`)
    text = re.sub(r'`(.*?)`', r'\1', text)
    
    # Remove links [text](url)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    # Remove horizontal rules (---)
    text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)
    
    # Clean up extra whitespace
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    text = text.strip()
    
    return text

def get_content_storage_path(user_id: str, content_id: str) -> str:
    """Get the storage path for content."""
    return f"/data/content/{user_id}/{content_id}"

def create_content_directory(user_id: str, content_id: str) -> str:
    """Create directory for content storage."""
    base_path = f"./data/content/{user_id}/{content_id}"
    os.makedirs(base_path, exist_ok=True)
    return base_path

def store_content(content: GeneratedContent) -> None:
    """Store content in memory and optionally on disk."""
    _content_storage[content.contentId] = content

def get_content(content_id: str) -> Optional[GeneratedContent]:
    """Get content by ID."""
    return _content_storage.get(content_id)

def get_user_content(user_id: str, status: Optional[ContentStatus] = None) -> List[GeneratedContent]:
    """Get all content for a user, optionally filtered by status."""
    user_content = [c for c in _content_storage.values() if c.userId == user_id]
    if status:
        user_content = [c for c in user_content if c.status == status]
    return sorted(user_content, key=lambda x: x.createdAt, reverse=True)

def auto_download_media_to_user_folder(content_id: str, user_id: str, storage_path: str, content_type: str = "audio") -> bool:
    """Automatically download media file (MP3/MP4) to the user's content directory."""
    try:
        # API endpoint for downloading content
        api_url = f"http://127.0.0.1:8001/api/content/download/{content_id}"
        
        # Download the media file
        response = requests.get(api_url, stream=True)
        response.raise_for_status()
        
        # Determine file extension and filename based on content type
        if content_type == "audio":
            file_extension = "mp3"
            filename_prefix = "audio"
        elif content_type == "video":
            file_extension = "mp4"
            filename_prefix = "video"
        else:
            file_extension = "bin"  # fallback
            filename_prefix = "media"
        
        # Save to user's directory with a friendly filename
        media_filename = f"{filename_prefix}_{content_id[:8]}.{file_extension}"
        media_path = os.path.join(storage_path, media_filename)
        
        with open(media_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"[AUTO-DOWNLOAD] {content_type.upper()} saved to: {media_path}")
        
        # Create a download script for the user
        create_user_download_script(user_id, storage_path)
        
        return True
        
    except Exception as e:
        print(f"[AUTO-DOWNLOAD] Failed to download {content_type}: {e}")
        return False

def auto_download_mp3_to_user_folder(content_id: str, user_id: str, storage_path: str) -> bool:
    """Automatically download MP3 file to the user's content directory."""
    return auto_download_media_to_user_folder(content_id, user_id, storage_path, "audio")

def auto_download_mp4_to_user_folder(content_id: str, user_id: str, storage_path: str) -> bool:
    """Automatically download MP4 file to the user's content directory."""
    return auto_download_media_to_user_folder(content_id, user_id, storage_path, "video")

def create_user_download_script(user_id: str, storage_path: str) -> None:
    """Create a download script for the user to easily download their media files."""
    script_content = f"""#!/bin/bash
# ICLeaF AI Auto-Download Script for User: {user_id}
# Generated automatically when media content is created

echo "🎵 ICLeaF AI Media Downloader for User: {user_id}"
echo "=================================================="

# Create downloads directory
DOWNLOADS_DIR="$HOME/Downloads/ICLeaF_{user_id}"
mkdir -p "$DOWNLOADS_DIR"

echo "📁 Download directory: $DOWNLOADS_DIR"

# Function to download media files
download_media() {{
    local content_id="$1"
    local content_type="$2"
    local filename="$3"
    
    if [ -z "$filename" ]; then
        if [ "$content_type" = "audio" ]; then
            filename="audio_${{content_id:0:8}}.mp3"
        elif [ "$content_type" = "video" ]; then
            filename="video_${{content_id:0:8}}.mp4"
        else
            filename="media_${{content_id:0:8}}.bin"
        fi
    fi
    
    echo "📥 Downloading: $filename ($content_type)"
    
    curl -o "$DOWNLOADS_DIR/$filename" \\
         "http://127.0.0.1:8001/api/content/download/$content_id" \\
         --fail --silent --show-error
    
    if [ $? -eq 0 ]; then
        local file_size=$(ls -lh "$DOWNLOADS_DIR/$filename" | awk '{{print $5}}')
        echo "✅ Downloaded: $filename ($file_size)"
    else
        echo "❌ Failed to download: $filename"
    fi
}}

# Download all available media files for this user
echo "🔍 Fetching content list for user: {user_id}"

# Get content list and download media files
curl -s "http://127.0.0.1:8001/api/content/list?userId={user_id}" | \\
python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    for content in data.get('content', []):
        content_id = content.get('contentId', '')
        content_type = content.get('contentType', '')
        if content_id and content_type in ['audio', 'video']:
            print(f'${{content_id}}|${{content_type}}')
except:
    pass
" | \\
while IFS='|' read -r content_id content_type; do
    if [ -n "$content_id" ] && [ -n "$content_type" ]; then
        download_media "$content_id" "$content_type"
    fi
done

echo ""
echo "🎉 Download complete!"
echo "📁 Files saved to: $DOWNLOADS_DIR"
echo "🎧 You can now play your media files!"
echo ""
echo "📱 Playing your files:"
echo "  🎵 Audio: open *.mp3  # macOS"
echo "  🎬 Video: open *.mp4  # macOS"
echo "  🎵 Audio: vlc *.mp3   # Linux"
echo "  🎬 Video: vlc *.mp4   # Linux"
"""
    
    script_path = os.path.join(storage_path, "download_my_media.sh")
    with open(script_path, 'w') as f:
        f.write(script_content)
    
    # Make the script executable
    os.chmod(script_path, 0o755)
    
    # Create a README file for the user
    create_user_readme(user_id, storage_path)
    
    print(f"[AUTO-DOWNLOAD] Created download script: {script_path}")

def create_user_readme(user_id: str, storage_path: str) -> None:
    """Create a README file explaining the user's content folder."""
    readme_content = f"""# 🎵 ICLeaF AI Content Folder for User: {user_id}

This folder contains your AI-generated audio and video content.

## 📁 What's in this folder:

- **audio_*.mp3** - Your generated MP3 audio files
- **video_*.mp4** - Your generated MP4 video files
- **audio_script.txt** - Text scripts for audio content
- **video_script.txt** - Text scripts for video content
- **download_my_media.sh** - Script to download all your media files
- **README.md** - This file

## 🎧 How to use your media files:

### Method 1: Use the download script
```bash
./download_my_media.sh
```

### Method 2: Download manually
```bash
# Download a specific MP3
curl -o "my_audio.mp3" "http://127.0.0.1:8001/api/content/download/{content_id}"

# Download a specific MP4
curl -o "my_video.mp4" "http://127.0.0.1:8001/api/content/download/{content_id}"
```

### Method 3: Use the web interface
1. Go to http://localhost:5174/
2. Click on the "Content" tab
3. Find your content and click "Download"

## 📱 Playing your media files:

### macOS
```bash
open *.mp3  # Opens audio with QuickTime
open *.mp4  # Opens video with QuickTime
```

### Linux
```bash
vlc *.mp3  # Audio with VLC
vlc *.mp4  # Video with VLC
mplayer *.mp3  # Audio with mplayer
mplayer *.mp4  # Video with mplayer
```

### Windows
```cmd
start *.mp3  # Opens audio with default player
start *.mp4  # Opens video with default player
```

## 🎬 Video Content Notes:

- Video files are generated as MP4 format
- If video generation fails, you'll get a script file instead
- Video generation requires ImageMagick to be installed
- Check server logs for video generation errors

## 🔄 Getting new content:

1. Use the web interface at http://localhost:5174/
2. Go to the "Content" tab
3. Generate new audio/video content
4. Your files will automatically appear in this folder!

## 📞 Need help?

- Check the main ICLeaF AI documentation
- Look at the server logs for any errors
- Ensure the server is running on http://127.0.0.1:8001
- For video issues, check ImageMagick installation

---
Generated by ICLeaF AI System
"""
    
    readme_path = os.path.join(storage_path, "README.md")
    with open(readme_path, 'w') as f:
        f.write(readme_content)
    
    print(f"[AUTO-DOWNLOAD] Created README: {readme_path}")

def update_content_status(content_id: str, status: ContentStatus, file_path: str = None, error: str = None) -> None:
    """Update content status."""
    if content_id in _content_storage:
        content = _content_storage[content_id]
        content.status = status
        if file_path:
            content.filePath = file_path
            content.downloadUrl = f"/api/content/download/{content_id}"
        if error:
            content.error = error
        if status == "completed":
            content.completedAt = datetime.now()

async def generate_flashcard_content(request: GenerateContentRequest, config: FlashcardConfig) -> str:
    """Generate flashcard content in a clean table format."""
    print(f"[DEBUG] generate_flashcard_content called with config: {config}")
    print(f"[DEBUG] config type: {type(config)}")
    print(f"[DEBUG] config.front: {config.front}")
    
    if not content_client:
        raise Exception("OpenAI client not configured")
    
    system_prompt = f"""You are an educational content generator. Create flashcards in a clean table format with the following specifications:
- Create 5-8 flashcards based on the topic
- Each flashcard should have a KEY (term/concept) and Description (explanation)
- Format as a clean table with two columns: KEY and Description
- Difficulty: {config.difficulty}
- User role: {request.role}

Format the output as a clean table like this:
| KEY | Description |
|-----|-------------|
| Term 1 | Clear explanation of term 1 |
| Term 2 | Clear explanation of term 2 |
| Term 3 | Clear explanation of term 3 |

Make sure the table is well-structured and easy to read."""
    
    user_prompt = f"""Create flashcards based on: {request.prompt}
Front: {config.front}
Back: {config.back}
Difficulty: {config.difficulty}

Generate 5-8 flashcards in a clean table format with KEY and Description columns."""
    
    response = content_client.chat.completions.create(
        model=deps.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    
    return response.choices[0].message.content

def _parse_markdown_table_to_rows(table_text: str) -> List[Tuple[str, str]]:
    """Parse a markdown table with two columns (KEY, Description) into rows.

    The function tolerates leading/trailing spaces, header/separator lines,
    and extra columns by taking the first two.
    """
    rows: List[Tuple[str, str]] = []
    lines = [ln.strip() for ln in table_text.splitlines() if ln.strip()]
    for ln in lines:
        if '|' not in ln:
            continue
        # Skip markdown separator rows like: |-----|------|
        if set(ln.replace('|', '').replace(' ', '').replace(':', '')) <= {'-',}:
            continue
        parts = [p.strip() for p in ln.split('|')]
        # Typical markdown rows start and end with '|', remove empties created by split
        parts = [p for p in parts if p != '']
        if len(parts) < 2:
            continue
        # Skip a possible header row if it looks like headers
        if parts[0].lower() in ("key", "term") and parts[1].lower().startswith("description"):
            continue
        key_col, desc_col = parts[0], parts[1]
        if key_col and desc_col:
            rows.append((key_col, desc_col))
    return rows

def _write_flashcards_csv_xlsx(storage_path: str, rows: List[Tuple[str, str]]) -> Tuple[str, str]:
    """Write flashcards to CSV and XLSX files. Returns (csv_path, xlsx_path)."""
    csv_path = os.path.join(storage_path, "flashcards.csv")
    xlsx_path = os.path.join(storage_path, "flashcards.xlsx")

    # CSV
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["KEY", "Description"])
        for k, d in rows:
            writer.writerow([k, d])

    # XLSX
    workbook = xlsxwriter.Workbook(xlsx_path)
    worksheet = workbook.add_worksheet("Flashcards")
    header_fmt = workbook.add_format({"bold": True})
    worksheet.write(0, 0, "KEY", header_fmt)
    worksheet.write(0, 1, "Description", header_fmt)
    for idx, (k, d) in enumerate(rows, start=1):
        worksheet.write(idx, 0, k)
        worksheet.write(idx, 1, d)
    # Make columns a bit wider
    worksheet.set_column(0, 0, 28)
    worksheet.set_column(1, 1, 80)
    workbook.close()

    return csv_path, xlsx_path

async def generate_quiz_content(request: GenerateContentRequest, config: QuizConfig) -> str:
    """Generate quiz content in a structured table format."""
    if not content_client:
        raise Exception("OpenAI client not configured")
    
    system_prompt = f"""You are an educational quiz generator. Create a quiz in a structured table format with the following specifications:
- Number of questions: {config.num_questions}
- Difficulty: {config.difficulty}
- Question types: {', '.join(config.question_types)}
- User role: {request.role}

Format the output as a structured table with these columns:
| S.No. | QUESTION | CORRECT ANSWER | ANSWER DESC | ANSWER 1 | ANSWER 2 | ANSWER 3 | ANSWER 4 |

Where:
- S.No.: Serial number (1, 2, 3, etc.)
- QUESTION: The quiz question
- CORRECT ANSWER: The number (1, 2, 3, or 4) indicating which answer is correct
- ANSWER DESC: Brief explanation of why the correct answer is right
- ANSWER 1-4: Four multiple choice options

Make sure each question has exactly 4 answer choices and the correct answer number corresponds to one of them."""
    
    user_prompt = f"""Create a quiz based on: {request.prompt}
Number of questions: {config.num_questions}
Difficulty: {config.difficulty}
Question types: {', '.join(config.question_types)}

Generate the quiz in the exact table format specified above."""
    
    response = content_client.chat.completions.create(
        model=deps.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    
    return response.choices[0].message.content

async def generate_quiz_table(request: GenerateContentRequest, config: QuizConfig) -> List[Dict[str, str]]:
    """Generate quiz rows suitable for CSV/XLSX export.

    Schema columns (logical keys):
    s_no, question, correct_answer, answer_desc, answer_1, answer_2, answer_3, answer_4
    """
    if not content_client:
        raise Exception("OpenAI client not configured")

    keys = [
        "s_no","question","correct_answer","answer_desc","answer_1","answer_2","answer_3","answer_4"
    ]

    system_prompt = (
        "You generate quiz rows for CSV/XLSX export. Return ONLY JSON array (no markdown) "
        "with objects using EXACT keys: " + ",".join(keys) + ". "
        "'s_no' starts at 1 and increments. 'correct_answer' is 1-4. "
        f"Create exactly {config.num_questions} rows. Difficulty: {config.difficulty}."
    )

    user_prompt = (
        f"Create quiz rows for: {request.prompt}. Keep questions concise and unambiguous."
    )

    response = content_client.chat.completions.create(
        model=deps.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )

    txt = response.choices[0].message.content.strip()
    try:
        data = json.loads(txt)
        if not isinstance(data, list):
            raise ValueError("expected list")
    except Exception:
        data = []

    rows: List[Dict[str, str]] = []
    for row in data:
        norm = {k: str(row.get(k, "")) for k in keys}
        rows.append(norm)
    return rows

def _write_quiz_csv_xlsx(storage_path: str, rows: List[Dict[str, str]]) -> Tuple[str, str]:
    """Write quiz rows to CSV/XLSX with the specified headers order."""
    headers = [
        "S.No.", "QUESTION", "CORRECT ANSWER", "ANSWER DESC",
        "ANSWER 1", "ANSWER 2", "ANSWER 3", "ANSWER 4"
    ]
    key_map = {
        "S.No.": "s_no",
        "QUESTION": "question",
        "CORRECT ANSWER": "correct_answer",
        "ANSWER DESC": "answer_desc",
        "ANSWER 1": "answer_1",
        "ANSWER 2": "answer_2",
        "ANSWER 3": "answer_3",
        "ANSWER 4": "answer_4",
    }

    csv_path = os.path.join(storage_path, "quiz.csv")
    xlsx_path = os.path.join(storage_path, "quiz.xlsx")

    # CSV
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for r in rows:
            writer.writerow([r.get(key_map[h], "") for h in headers])

    # XLSX
    workbook = xlsxwriter.Workbook(xlsx_path)
    ws = workbook.add_worksheet("Quiz")
    header_fmt = workbook.add_format({"bold": True})
    for col, h in enumerate(headers):
        ws.write(0, col, h, header_fmt)
    for row_idx, r in enumerate(rows, start=1):
        for col, h in enumerate(headers):
            ws.write(row_idx, col, r.get(key_map[h], ""))
    ws.set_row(0, 18)
    ws.set_column(0, len(headers)-1, 22)
    workbook.close()

    return csv_path, xlsx_path

async def generate_assessment_content(request: GenerateContentRequest, config: AssessmentConfig) -> str:
    """Generate assessment content."""
    if not content_client:
        raise Exception("OpenAI client not configured")
    
    system_prompt = f"""You are an educational assessment generator. Create an assessment with the following specifications:
- Duration: {config.duration_minutes} minutes
- Difficulty: {config.difficulty}
- Question types: {', '.join(config.question_types)}
- Passing score: {config.passing_score}%
- User role: {request.role}"""
    
    user_prompt = f"""Create an assessment based on: {request.prompt}
Duration: {config.duration_minutes} minutes
Difficulty: {config.difficulty}
Question types: {', '.join(config.question_types)}
Passing score: {config.passing_score}%"""
    
    response = content_client.chat.completions.create(
        model=deps.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    
    return response.choices[0].message.content

async def generate_assessment_table(request: GenerateContentRequest, config: AssessmentConfig) -> List[Dict[str, str]]:
    """Generate assessment in a structured row schema suitable for XLSX/CSV.

    Schema columns:
    subject, topic, type, question, answer_description, levels, total_options,
    choice_answer_one, choice_answer_two, choice_answer_three, choice_answer_four,
    choice_answer_five, correct_answers, tag1, tag2, tag3
    """
    if not content_client:
        raise Exception("OpenAI client not configured")

    columns = [
        "subject","topic","type","question","answer_description","levels","total_options",
        "choice_answer_one","choice_answer_two","choice_answer_three","choice_answer_four","choice_answer_five",
        "correct_answers","tag1","tag2","tag3"
    ]

    system_prompt = (
        "You create assessment rows for export to CSV/XLSX. "
        "Return ONLY valid JSON array (no markdown) of objects with EXACTLY these keys: "
        + ",".join(columns) + ". "
        "The 'type' is one of: Choice, FillUp, Match. "
        "'levels' is one of: Easy, Medium, Difficult. "
        "'total_options' is 3-5 for Choice, 1 for FillUp/Match. "
        "For 'correct_answers', provide comma-separated indices like '1' or '1,3'. "
        "When type is FillUp, put the correct answer in choice_answer_one and set total_options to 1. "
        "When type is Match, put pairs in choice_answer_one..five like 'a=apple'. "
    )

    user_prompt = (
        f"Create 4 assessment rows for: {request.prompt}\n"
        f"Subject: {request.subjectName or ''}\n"
        f"Topic: {request.topicName or ''}\n"
        f"Duration: {config.duration_minutes} minutes. Difficulty: {config.difficulty}. "
        f"Question types: {', '.join(config.question_types)}. "
        "Use concise wording for questions and answers."
    )

    response = content_client.chat.completions.create(
        model=deps.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
    )

    txt = response.choices[0].message.content.strip()
    try:
        data = json.loads(txt)
        if not isinstance(data, list):
            raise ValueError("expected list")
    except Exception:
        # Fallback: return empty list to avoid crash
        data = []
    # Normalize rows to include all columns
    norm_rows: List[Dict[str, str]] = []
    for row in data:
        norm = {k: str(row.get(k, "")) for k in columns}
        norm_rows.append(norm)
    return norm_rows

def _write_assessment_csv_xlsx(storage_path: str, rows: List[Dict[str, str]]) -> Tuple[str, str]:
    """Write assessment rows to CSV and XLSX. Returns (csv_path, xlsx_path)."""
    headers = [
        "subject","topic","type","question","answer description","levels","total options",
        "Choice Answer One","Choice Answer Two","Choice Answer Three","Choice Answer Four","Choice Answer Five",
        "correct answers","TAG1","TAG2","TAG3"
    ]
    key_map = {
        "subject":"subject","topic":"topic","type":"type","question":"question",
        "answer description":"answer_description","levels":"levels","total options":"total_options",
        "Choice Answer One":"choice_answer_one","Choice Answer Two":"choice_answer_two",
        "Choice Answer Three":"choice_answer_three","Choice Answer Four":"choice_answer_four",
        "Choice Answer Five":"choice_answer_five","correct answers":"correct_answers",
        "TAG1":"tag1","TAG2":"tag2","TAG3":"tag3",
    }
    csv_path = os.path.join(storage_path, "assessment.csv")
    xlsx_path = os.path.join(storage_path, "assessment.xlsx")

    # CSV
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for r in rows:
            writer.writerow([r.get(key_map[h], "") for h in headers])

    # XLSX
    workbook = xlsxwriter.Workbook(xlsx_path)
    ws = workbook.add_worksheet("Assessment")
    header_fmt = workbook.add_format({"bold": True})
    for col, h in enumerate(headers):
        ws.write(0, col, h, header_fmt)
    for row_idx, r in enumerate(rows, start=1):
        for col, h in enumerate(headers):
            ws.write(row_idx, col, r.get(key_map[h], ""))
    ws.set_row(0, 18)
    ws.set_column(0, len(headers)-1, 18)
    workbook.close()

    return csv_path, xlsx_path

async def generate_video_content(request: GenerateContentRequest, config: VideoConfig, content_id: str, storage_path: str) -> str:
    """Generate actual video file using AI video generation.
    
    Args:
        request: Content generation request
        config: Video configuration
        content_id: Pre-generated content ID
        storage_path: Pre-created storage directory path
    """
    if not content_client:
        raise Exception("OpenAI client not configured")
    
    # First, generate the video script
    system_prompt = f"""You are a video content generator. Create engaging video content with the following specifications:
- Duration: {config.duration_seconds} seconds
- Quality: {config.quality}
- Include subtitles: {config.include_subtitles}
- User role: {request.role}
- Make it engaging and suitable for video consumption"""
    
    user_prompt = f"""Create video content based on: {request.prompt}
Duration: {config.duration_seconds} seconds
Quality: {config.quality}
Include subtitles: {config.include_subtitles}
Make it engaging and visually appealing for video viewing."""
    
    response = content_client.chat.completions.create(
        model=deps.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    
    script_content = response.choices[0].message.content
    
    # Generate the actual video file
    try:
        # Use the provided storage_path (folder already created in process_content_generation)
        # Create script file (faster than video generation)
        script_path = os.path.join(storage_path, "video_script.txt")
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(f"Video Script:\n\n{script_content}\n\n")
            f.write(f"Duration: {config.duration_seconds} seconds\n")
            f.write(f"Quality: {config.quality}\n")
            f.write(f"Subtitles: {config.include_subtitles}\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
        return script_path
            
    except Exception as e:
        # Fallback: save script as text file
        script_path = os.path.join(storage_path, "video_script.txt")
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(f"Error generating video: {str(e)}\n\nScript: {script_content}")
        return script_path

async def generate_audio_content(request: GenerateContentRequest, config: AudioConfig, content_id: str, storage_path: str) -> str:
    """Generate actual MP3 audio file using OpenAI TTS.
    
    Args:
        request: Content generation request
        config: Audio configuration
        content_id: Pre-generated content ID
        storage_path: Pre-created storage directory path
    """
    if not content_client:
        raise Exception("OpenAI client not configured")
    
    # First, generate the script content
    system_prompt = f"""You are an audio content generator. Create engaging audio content with the following specifications:
- Duration: {config.duration_seconds} seconds
- Quality: {config.quality}
- Format: {config.format}
- User role: {request.role}
- Make it engaging and suitable for audio consumption"""
    
    user_prompt = f"""Create audio content based on: {request.prompt}
Duration: {config.duration_seconds} seconds
Quality: {config.quality}
Format: {config.format}
Make it engaging and conversational for audio listening."""
    
    response = content_client.chat.completions.create(
        model=deps.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    
    script_content = response.choices[0].message.content
    
    # Generate the actual MP3 file using TTS
    try:
        # Use the provided storage_path (folder already created in process_content_generation)
        # Generate MP3 file
        audio_path = os.path.join(storage_path, f"audio.{config.format}")
        print(f"[DEBUG] Attempting TTS generation: {audio_path}")
        success = await media_generator.generate_audio_file(
            text=script_content,
            output_path=audio_path,
            voice="alloy",  # Default voice
            model="tts-1",
            format=config.format
        )
        
        print(f"[DEBUG] TTS success: {success}")
        if success:
            # Auto-download MP3 to user's folder
            print(f"[AUTO-DOWNLOAD] Attempting to download MP3 for user {request.userId}")
            download_success = auto_download_mp3_to_user_folder(content_id, request.userId, storage_path)
            if download_success:
                print(f"[AUTO-DOWNLOAD] MP3 successfully downloaded to user folder")
            
            # Return the audio file path for the content manager to use
            print(f"[DEBUG] Returning audio file path: {audio_path}")
            return audio_path
        else:
            # Fallback: save script as text file
            print(f"[DEBUG] TTS failed, falling back to script")
            script_path = os.path.join(storage_path, "audio_script.txt")
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(script_content)
            return script_path
            
    except Exception as e:
        # Fallback: save script as text file
        script_path = os.path.join(storage_path, "audio_script.txt")
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(f"Error generating audio: {str(e)}\n\nScript: {script_content}")
        return script_path

async def generate_compiler_content(request: GenerateContentRequest, config: CompilerConfig) -> str:
    """Generate compiler/code content."""
    if not content_client:
        raise Exception("OpenAI client not configured")
    
    system_prompt = f"""You are a code generator. Create code with the following specifications:
- Language: {config.language}
- Include tests: {config.include_tests}
- Difficulty: {config.difficulty}
- User role: {request.role}"""
    
    user_prompt = f"""Create code based on: {request.prompt}
Language: {config.language}
Include tests: {config.include_tests}
Difficulty: {config.difficulty}"""
    
    response = content_client.chat.completions.create(
        model=deps.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    
    return response.choices[0].message.content

async def generate_pdf_content(request: GenerateContentRequest, content_id: str, storage_path: str) -> str:
    """Generate PDF content and save to file.
    
    Args:
        request: Content generation request
        content_id: Pre-generated content ID (must match the one in process_content_generation)
        storage_path: Pre-created storage directory path
    """
    if not content_client:
        raise Exception("OpenAI client not configured")
    
    # Get PDF configuration
    pdf_config = request.contentConfig.get('pdf', {})
    num_pages = pdf_config.get('num_pages', 5)
    target_audience = pdf_config.get('target_audience', 'general')
    include_images = pdf_config.get('include_images', True)
    difficulty = pdf_config.get('difficulty', 'medium')
    
    print(f"[DEBUG] PDF Config: num_pages={num_pages}, target_audience={target_audience}, difficulty={difficulty}")
    print(f"[DEBUG] Using content_id: {content_id}, storage_path: {storage_path}")
    
    system_prompt = f"""You are a PDF content generator. Create structured content for a PDF document.
User role: {request.role}
Mode: {request.mode}
Target audience: {target_audience}
Difficulty level: {difficulty}
Include images: {include_images}"""
    
    user_prompt = f"""Create PDF content based on: {request.prompt}

CRITICAL REQUIREMENTS:
- You MUST create content that fills EXACTLY {num_pages} pages
- Target audience: {target_audience}
- Difficulty: {difficulty}
- Each page should have substantial content (approximately 500-800 words per page)
- Include detailed explanations, examples, and comprehensive information
- Structure content with clear sections and subsections
- Make sure the content is extensive enough to fill {num_pages} full pages
- Add more detail, examples, and explanations to reach the page count
- If the topic is too narrow, expand it with related concepts and applications"""
    
    response = content_client.chat.completions.create(
        model=deps.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    
    content = response.choices[0].message.content
    
    # Clean markdown formatting and remove unwanted artifacts
    content = clean_markdown_formatting(content)
    # Remove "Page X" or "Page X topic" patterns
    content = re.sub(r'Page\s+\d+\s*(topic|title|content)?\s*:?', '', content, flags=re.IGNORECASE)
    content = re.sub(r'^\d+\.\s*Page\s+\d+', '', content, flags=re.MULTILINE | re.IGNORECASE)
    
    # Use the provided storage_path (folder already created in process_content_generation)
    pdf_path = os.path.join(storage_path, "document.pdf")
    
    # Create PDF using ReportLab with proper formatting
    doc = SimpleDocTemplate(pdf_path, pagesize=A4, 
                           rightMargin=72, leftMargin=72,
                           topMargin=72, bottomMargin=72)
    styles = getSampleStyleSheet()
    story = []
    
    # Adjust font sizes based on target audience and difficulty
    if target_audience == 'students':
        base_font_size = 11
        heading_font_size = 16
    elif target_audience == 'teachers' or difficulty == 'advanced':
        base_font_size = 10
        heading_font_size = 15
    else:
        base_font_size = 12
        heading_font_size = 18
    
    # Title page style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=heading_font_size + 4,
        spaceAfter=30,
        alignment=1,  # Center alignment
        textColor=colors.HexColor('#333366')  # Dark blue
    )
    
    # Main title
    title_text = request.prompt[:50] + "..." if len(request.prompt) > 50 else request.prompt
    story.append(Spacer(1, 2*inch))
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 0.5*inch))
    
    # Subtitle with metadata
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=base_font_size,
        alignment=1,
        textColor=colors.HexColor('#666666')
    )
    story.append(Paragraph(f"Target Audience: {target_audience.title()} | Difficulty: {difficulty.title()}", subtitle_style))
    story.append(PageBreak())
    
    # Heading style
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=heading_font_size,
        spaceAfter=12,
        spaceBefore=20,
        leftIndent=0,
        textColor=colors.HexColor('#1a1a4d'),
        fontName='Helvetica-Bold'
    )
    
    # Content style
    content_style = ParagraphStyle(
        'CustomContent',
        parent=styles['Normal'],
        fontSize=base_font_size,
        spaceAfter=10,
        leftIndent=0,
        rightIndent=0,
        alignment=0,  # Left align
        leading=base_font_size + 2
    )
    
    # Parse content into structured sections
    # Split by double newlines, then clean and structure
    raw_sections = [s.strip() for s in content.split('\n\n') if s.strip()]
    
    # Remove empty sections and filter out artifacts
    sections = []
    for section in raw_sections:
        # Skip sections that are just page numbers or artifacts
        if re.match(r'^(Page\s+\d+|^\d+\.?\s*$)', section, re.IGNORECASE):
            continue
        # Skip very short sections that are likely artifacts
        if len(section) < 20:
            continue
        sections.append(section)
    
    # Distribute sections across target pages
    # Calculate content per page (aim for ~600-800 words per page)
    # Estimate: ~5 words per line, ~50 lines per page = ~250 words per page
    # But we want more content, so let's aim for better distribution
    if len(sections) < num_pages:
        # Not enough sections - we'll need to split existing sections
        # Or add more spacing/content to fill pages
        sections_per_page = 1
    else:
        sections_per_page = max(1, len(sections) // num_pages)
    
    pages_created = 1  # Start with 1 (title page already added)
    sections_added = 0
    
    for i, section in enumerate(sections):
        if pages_created >= num_pages and sections_added > 0:
            # We've reached the target page count
            break
        
        lines = [line.strip() for line in section.split('\n') if line.strip()]
        if not lines:
            continue
        
        # Determine if first line is a heading
        first_line = lines[0]
        is_heading = (
            len(first_line) < 100 and 
            (first_line.isupper() or 
             first_line.startswith('#') or
             not first_line.endswith('.') or
             len(first_line.split()) < 10)
        )
        
        if is_heading:
            # Add heading
            heading_text = first_line.replace('#', '').strip()
            # Remove common heading prefixes
            heading_text = re.sub(r'^(Section|Chapter|Part|Topic)\s+\d+[.:]?\s*', '', heading_text, flags=re.IGNORECASE)
            story.append(Paragraph(heading_text, heading_style))
            content_lines = lines[1:]
        else:
            content_lines = lines
        
        # Add content paragraphs
        current_paragraph = []
        for line in content_lines:
            # Skip bullet points for now (handle them as regular text)
            line_clean = line.lstrip('-•* ').strip()
            if line_clean:
                current_paragraph.append(line_clean)
        
        # Add paragraphs
        if current_paragraph:
            para_text = ' '.join(current_paragraph)
            # Replace multiple spaces with single space
            para_text = re.sub(r'\s+', ' ', para_text)
            if para_text:
                story.append(Paragraph(para_text, content_style))
                story.append(Spacer(1, 8))
                sections_added += 1
        
        # Add page break based on distribution to enforce page count
        # We want to distribute content evenly across pages
        if pages_created < num_pages:
            # Calculate if we should add a page break
            # Aim to distribute sections evenly
            if len(sections) > 0:
                sections_per_page_target = max(1, len(sections) / num_pages)
                if (i + 1) >= sections_per_page_target * (pages_created + 1) and (i + 1) < len(sections):
                    story.append(PageBreak())
                    pages_created += 1
    
    # If we haven't reached the target page count, add filler content
    # ReportLab will create pages as needed, but we want to ensure we hit the target
    if pages_created < num_pages:
        remaining_pages = num_pages - pages_created
        for page_num in range(remaining_pages):
            story.append(PageBreak())
            # Add a section header
            story.append(Paragraph(f"Additional Information", heading_style))
            story.append(Spacer(1, 0.3*inch))
            # Add some filler content with spacing to ensure it takes up a page
            for _ in range(15):  # Add enough content to fill a page
                story.append(Paragraph("This section provides additional details and information related to the topic.", content_style))
                story.append(Spacer(1, 0.2*inch))
            pages_created += 1
    
    # Build PDF
    doc.build(story)
    
    return pdf_path

async def generate_ppt_content(request: GenerateContentRequest, content_id: str, storage_path: str) -> str:
    """Generate PowerPoint content using simple python-pptx approach.
    
    Args:
        request: Content generation request
        content_id: Pre-generated content ID (must match the one in process_content_generation)
        storage_path: Pre-created storage directory path
    """
    if not content_client:
        raise Exception("OpenAI client not configured")
    
    # Get PPT configuration
    ppt_config = request.contentConfig.get('ppt', {})
    num_slides = ppt_config.get('num_slides', 10)
    target_audience = ppt_config.get('target_audience', 'general')
    include_animations = ppt_config.get('include_animations', True)
    difficulty = ppt_config.get('difficulty', 'medium')
    
    print(f"[DEBUG] PPT Config: num_slides={num_slides}, target_audience={target_audience}, difficulty={difficulty}")
    print(f"[DEBUG] Using content_id: {content_id}, storage_path: {storage_path}")
    
    system_prompt = f"""You are a PowerPoint content generator. Create comprehensive content for a presentation.
User role: {request.role}
Mode: {request.mode}
Target audience: {target_audience}
Difficulty level: {difficulty}
Include animations: {include_animations}

Create a comprehensive presentation with:
- Clear slide titles
- Detailed bullet points with explanations
- Introduction and conclusion slides
- Logical flow between topics
- Substantial content for each slide

Format each section as:
Title: [Slide Title]
Content: [Detailed bullet points with explanations]

Ensure each slide has meaningful content, not just titles."""
    
    user_prompt = f"""Create a concise PowerPoint presentation about: {request.prompt}

CRITICAL REQUIREMENTS:
- Create content for EXACTLY {num_slides} slides
- Target audience: {target_audience}
- Difficulty: {difficulty}
- Each slide should have SHORT, CONCISE bullet points (max 5 per slide)
- Keep bullet points under 80 characters each
- Focus on key points, not lengthy explanations
- Make content fit within slide boundaries

Structure the presentation with:
1. Title slide
2. Introduction slide with overview
3. Main content slides with SHORT bullet points
4. Examples slides with brief points
5. Summary slide

IMPORTANT: Keep all content SHORT and CONCISE to prevent overflow."""
    
    response = content_client.chat.completions.create(
        model=deps.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    
    content = response.choices[0].message.content
    
    # Clean markdown formatting
    content = clean_markdown_formatting(content)
    # Remove unwanted artifacts
    content = re.sub(r'Slide\s+\d+[.:]?\s*', '', content, flags=re.IGNORECASE)
    content = re.sub(r'^\d+\.\s*Slide\s+\d+', '', content, flags=re.MULTILINE | re.IGNORECASE)
    
    # Use the provided storage_path (folder already created in process_content_generation)
    ppt_path = os.path.join(storage_path, "presentation.pptx")
    
    # Create PowerPoint presentation
    prs = Presentation()
    
    # Set slide width and height (standard 16:9)
    prs.slide_width = Inches(10)
    prs.slide_height = Inches(7.5)
    
    # Title slide
    title_slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(title_slide_layout)
    title = slide.shapes.title
    subtitle = slide.placeholders[1] if len(slide.placeholders) > 1 else None
    
    # Set title - use prompt or first part of it
    title_text = request.prompt[:60] + "..." if len(request.prompt) > 60 else request.prompt
    title.text = title_text
    
    # Set subtitle with metadata
    if subtitle:
        subtitle.text = f"Target Audience: {target_audience.title()} | Difficulty: {difficulty.title()}\n{datetime.now().strftime('%Y-%m-%d')}"
    
    # Parse content into slides
    # Split content into sections
    raw_sections = [s.strip() for s in content.split('\n\n') if s.strip()]
    
    # Filter and clean sections
    sections = []
    for section in raw_sections:
        # Skip artifacts
        if re.match(r'^(Slide\s+\d+|^\d+\.?\s*$)', section, re.IGNORECASE):
            continue
        if len(section) < 15:
            continue
        sections.append(section)
    
    # Calculate slides per section to reach target
    # We already have 1 title slide, so we need (num_slides - 1) content slides
    target_content_slides = max(1, num_slides - 1)
    
    if len(sections) == 0:
        # No content - create placeholder slides
        sections = [request.prompt]
    
    # Distribute sections across slides
    if len(sections) <= target_content_slides:
        # Each section gets its own slide (or combine if needed)
        sections_per_slide = 1
    else:
        # Multiple sections per slide, or split sections
        sections_per_slide = max(1, len(sections) // target_content_slides)
    
    slide_count = 1  # Start at 1 (title slide already added)
    sections_processed = 0
    
    # Use content layout for content slides
    content_layout = prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0]
    
    for i, section in enumerate(sections):
        if slide_count >= num_slides:
            break
        
        lines = [line.strip() for line in section.split('\n') if line.strip()]
        if not lines:
            continue
        
        # Extract slide title (first line or first few words)
        slide_title = lines[0].strip()
        # Clean title
        slide_title = re.sub(r'^(Title|Slide|Section)\s*\d*[.:]?\s*', '', slide_title, flags=re.IGNORECASE)
        slide_title = slide_title.replace('Title:', '').replace('#', '').strip()
        if not slide_title:
            slide_title = f"Section {slide_count}"
        
        # Truncate title if too long
        if len(slide_title) > 60:
            slide_title = slide_title[:57] + "..."
        
        # Extract content (remaining lines)
        content_lines = lines[1:] if len(lines) > 1 else lines
        slide_content = '\n'.join(content_lines).strip()
        slide_content = slide_content.replace('Content:', '').strip()
        
        # Create slide
        slide = prs.slides.add_slide(content_layout)
        title_shape = slide.shapes.title
        content_placeholder = slide.placeholders[1] if len(slide.placeholders) > 1 else None
        
        # Set title
        title_shape.text = slide_title
        
        # Process content into bullet points
        if content_placeholder and slide_content:
            text_frame = content_placeholder.text_frame
            text_frame.clear()
            text_frame.word_wrap = True
            
            # Adjust bullet points based on difficulty and audience
            if target_audience == 'students' or difficulty == 'beginner':
                max_bullets = 4
                max_chars = 70
            elif difficulty == 'advanced':
                max_bullets = 6
                max_chars = 90
            else:
                max_bullets = 5
                max_chars = 80
            
            # Split content into bullet points
            bullet_lines = []
            seen_points = set()
            
            for line in slide_content.split('\n'):
                if len(bullet_lines) >= max_bullets:
                    break
                
                line = line.strip()
                if not line:
                    continue
                
                # Clean bullet markers
                line = re.sub(r'^[-•*]\s*', '', line)
                line = line.strip()
                
                if not line or len(line) < 10:
                    continue
                
                # Truncate if too long
                if len(line) > max_chars:
                    line = line[:max_chars-3] + "..."
                
                # Check for duplicates
                line_lower = line.lower()
                if line_lower not in seen_points:
                    seen_points.add(line_lower)
                    bullet_lines.append(line)
            
            # Add bullet points to slide
            if bullet_lines:
                for idx, bullet in enumerate(bullet_lines):
                    if idx == 0:
                        p = text_frame.paragraphs[0]
                    else:
                        p = text_frame.add_paragraph()
                    p.text = bullet
                    p.level = 0
                    p.font.size = Pt(14 if target_audience == 'students' else 12)
                    p.space_after = Pt(6)
            else:
                # No bullets - add as single paragraph
                p = text_frame.paragraphs[0]
                p.text = slide_content[:200] + "..." if len(slide_content) > 200 else slide_content
                p.font.size = Pt(12)
        
        slide_count += 1
        sections_processed += 1
        
        # Add slides to reach target if needed
        if (i + 1) % sections_per_slide == 0 and slide_count < num_slides and (i + 1) < len(sections):
            # Continue with next section
            continue
    
    # Fill remaining slides to reach target count
    while slide_count < num_slides:
        slide = prs.slides.add_slide(content_layout)
        title_shape = slide.shapes.title
        content_placeholder = slide.placeholders[1] if len(slide.placeholders) > 1 else None
        
        title_shape.text = f"Additional Content {slide_count}"
        if content_placeholder:
            text_frame = content_placeholder.text_frame
            text_frame.clear()
            p = text_frame.paragraphs[0]
            p.text = "Additional information and details..."
            p.font.size = Pt(12)
        
        slide_count += 1
    
    # Save presentation
    prs.save(ppt_path)
    
    print(f"[DEBUG] Created PPT with {len(prs.slides)} slides (target: {num_slides})")
    
    return ppt_path

async def generate_quiz_pdf_content(request: GenerateContentRequest, quiz_config: QuizConfig) -> str:
    """Generate quiz content as PDF in structured table format."""
    if not content_client:
        raise Exception("OpenAI client not configured")
    
    system_prompt = f"""You are an educational quiz generator. Create a quiz in a structured table format with the following specifications:
- Number of questions: {quiz_config.num_questions}
- Difficulty: {quiz_config.difficulty}
- Question types: {', '.join(quiz_config.question_types)}
- User role: {request.role}

Format the output as a structured table with these columns:
| S.No. | QUESTION | CORRECT ANSWER | ANSWER DESC | ANSWER 1 | ANSWER 2 | ANSWER 3 | ANSWER 4 |

Where:
- S.No.: Serial number (1, 2, 3, etc.)
- QUESTION: The quiz question
- CORRECT ANSWER: The number (1, 2, 3, or 4) indicating which answer is correct
- ANSWER DESC: Brief explanation of why the correct answer is right
- ANSWER 1-4: Four multiple choice options

Make sure each question has exactly 4 answer choices and the correct answer number corresponds to one of them."""
    
    user_prompt = f"""Create a quiz based on: {request.prompt}
Number of questions: {quiz_config.num_questions}
Difficulty: {quiz_config.difficulty}
Question types: {', '.join(quiz_config.question_types)}

Generate the quiz in the exact table format specified above."""
    
    response = content_client.chat.completions.create(
        model=deps.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    
    content = response.choices[0].message.content
    
    # Clean markdown formatting
    content = clean_markdown_formatting(content)
    
    # Create PDF file
    content_id = generate_content_id()
    storage_path = f"./data/content/{request.userId}/{content_id}"
    os.makedirs(storage_path, exist_ok=True)
    
    pdf_path = os.path.join(storage_path, "quiz.pdf")
    
    # Create PDF using ReportLab
    doc = SimpleDocTemplate(pdf_path, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle(
        'QuizTitle',
        parent=styles['Heading1'],
        fontSize=20,
        spaceAfter=30,
        alignment=1
    )
    story.append(Paragraph("ICLeafAI", title_style))
    story.append(Spacer(1, 20))
    
    # Content
    content_style = ParagraphStyle(
        'QuizContent',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=12,
        leftIndent=20
    )
    
    # Split content into paragraphs
    paragraphs = content.split('\n\n')
    for para in paragraphs:
        if para.strip():
            para_text = para.strip().replace('\n', '<br/>')
            story.append(Paragraph(para_text, content_style))
            story.append(Spacer(1, 12))
    
    # Add footer
    story.append(PageBreak())
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=10,
        alignment=1
    )
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", footer_style))
    story.append(Paragraph(f"User: {request.userId}", footer_style))
    
    doc.build(story)
    return pdf_path

async def generate_assessment_pdf_content(request: GenerateContentRequest, assessment_config: AssessmentConfig) -> str:
    """Generate assessment content as PDF."""
    if not content_client:
        raise Exception("OpenAI client not configured")
    
    system_prompt = f"""You are an assessment generator. Create a structured assessment for {assessment_config.duration_minutes} minutes.
User role: {request.role}
Mode: {request.mode}
Difficulty: {assessment_config.difficulty}"""
    
    user_prompt = f"""Create an assessment based on: {request.prompt}
Duration: {assessment_config.duration_minutes} minutes
Difficulty: {assessment_config.difficulty}
Question types: {', '.join(assessment_config.question_types)}
Passing score: {assessment_config.passing_score}%"""
    
    response = content_client.chat.completions.create(
        model=deps.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    
    content = response.choices[0].message.content
    
    # Clean markdown formatting
    content = clean_markdown_formatting(content)
    
    # Create PDF file
    content_id = generate_content_id()
    storage_path = f"./data/content/{request.userId}/{content_id}"
    os.makedirs(storage_path, exist_ok=True)
    
    pdf_path = os.path.join(storage_path, "assessment.pdf")
    
    # Create PDF using ReportLab
    doc = SimpleDocTemplate(pdf_path, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle(
        'AssessmentTitle',
        parent=styles['Heading1'],
        fontSize=20,
        spaceAfter=30,
        alignment=1
    )
    story.append(Paragraph("ICLeafAI", title_style))
    story.append(Spacer(1, 20))
    
    # Content
    content_style = ParagraphStyle(
        'AssessmentContent',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=12,
        leftIndent=20
    )
    
    # Split content into paragraphs
    paragraphs = content.split('\n\n')
    for para in paragraphs:
        if para.strip():
            para_text = para.strip().replace('\n', '<br/>')
            story.append(Paragraph(para_text, content_style))
            story.append(Spacer(1, 12))
    
    # Add footer
    story.append(PageBreak())
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=10,
        alignment=1
    )
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", footer_style))
    story.append(Paragraph(f"User: {request.userId}", footer_style))
    
    doc.build(story)
    return pdf_path

async def process_content_generation(request: GenerateContentRequest) -> GeneratedContent:
    """Process content generation based on type."""
    content_id = generate_content_id()
    
    # Create content object
    content = GeneratedContent(
        contentId=content_id,
        userId=request.userId,
        role=request.role,
        mode=request.mode,
        contentType=request.contentType,
        prompt=request.prompt,
        status="pending",
        contentConfig=request.contentConfig,
        metadata={
            "docIds": request.docIds,
            "subjectName": request.subjectName,
            "topicName": request.topicName
        }
    )
    
    # Store content
    store_content(content)
    
    try:
        # Create storage directory
        storage_path = create_content_directory(request.userId, content_id)
        
        # Generate content based on type
        generated_content = ""
        
        if request.contentType == "flashcard" and request.contentConfig.get('flashcard'):
            flashcard_config_dict = request.contentConfig.get('flashcard')
            print(f"[DEBUG] Flashcard config dict: {flashcard_config_dict}")
            # Create FlashcardConfig object manually
            flashcard_config = FlashcardConfig(
                front=flashcard_config_dict.get('front', ''),
                back=flashcard_config_dict.get('back', ''),
                difficulty=flashcard_config_dict.get('difficulty', 'medium')
            )
            print(f"[DEBUG] Flashcard config object: {flashcard_config}")
            generated_content = await generate_flashcard_content(request, flashcard_config)
        elif request.contentType == "quiz" and request.contentConfig.get('quiz'):
            quiz_config_dict = request.contentConfig.get('quiz')
            # Create QuizConfig object manually
            quiz_config = QuizConfig(
                num_questions=quiz_config_dict.get('num_questions', 5),
                difficulty=quiz_config_dict.get('difficulty', 'medium'),
                question_types=quiz_config_dict.get('question_types', ['multiple_choice'])
            )
            rows = await generate_quiz_table(request, quiz_config)
            csv_path, xlsx_path = _write_quiz_csv_xlsx(storage_path, rows)
            generated_content = xlsx_path
        elif request.contentType == "assessment" and request.contentConfig.get('assessment'):
            assessment_config_dict = request.contentConfig.get('assessment')
            assessment_config = AssessmentConfig(**assessment_config_dict)
            # Generate table-structured rows and export CSV/XLSX
            rows = await generate_assessment_table(request, assessment_config)
            csv_path, xlsx_path = _write_assessment_csv_xlsx(storage_path, rows)
            # Also create a PDF fallback if needed later; for now, prefer XLSX path
            generated_content = xlsx_path
        elif request.contentType == "video" and request.contentConfig.get('video'):
            video_config_dict = request.contentConfig.get('video')
            video_config = VideoConfig(**video_config_dict)
            generated_content = await generate_video_content(request, video_config, content_id, storage_path)
        elif request.contentType == "audio" and request.contentConfig.get('audio'):
            audio_config_dict = request.contentConfig.get('audio')
            audio_config = AudioConfig(**audio_config_dict)
            generated_content = await generate_audio_content(request, audio_config, content_id, storage_path)
        elif request.contentType == "compiler" and request.contentConfig.get('compiler'):
            compiler_config_dict = request.contentConfig.get('compiler')
            compiler_config = CompilerConfig(**compiler_config_dict)
            generated_content = await generate_compiler_content(request, compiler_config)
        elif request.contentType == "pdf":
            generated_content = await generate_pdf_content(request, content_id, storage_path)
        elif request.contentType == "ppt":
            generated_content = await generate_ppt_content(request, content_id, storage_path)
        else:
            raise Exception(f"Unsupported content type: {request.contentType}")
        
        # Handle different content types
        if request.contentType in ["video", "audio", "pdf", "ppt", "quiz", "assessment"]:
            # For media files and document files, the generated_content is the file path
            file_path = generated_content
            print(f"[DEBUG] Generated file path: {file_path}")
        else:
            # For other content types, save to file
            file_extension = {
                "flashcard": ".json",
                "compiler": ".py"
            }.get(request.contentType, ".txt")
            
            file_path = os.path.join(storage_path, f"content{file_extension}")
            
            if request.contentType in ["flashcard"]:
                # Parse markdown table to rows and write CSV/XLSX alongside JSON
                rows = _parse_markdown_table_to_rows(generated_content)
                csv_path, xlsx_path = _write_flashcards_csv_xlsx(storage_path, rows)

                content_data = {
                    "type": request.contentType,
                    "table_markdown": generated_content,
                    "rows": [{"KEY": k, "Description": d} for k, d in rows],
                    "csv_path": csv_path,
                    "xlsx_path": xlsx_path,
                    "config": request.contentConfig,
                    "metadata": content.metadata
                }
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(content_data, f, indent=2, default=str)
                # Prefer CSV as primary downloadable artifact
                file_path = csv_path
            else:
                # Save as text
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(generated_content)
        
        # Update content status
        update_content_status(content_id, "completed", file_path)
        
        return content
        
    except Exception as e:
        # Update content status with error
        update_content_status(content_id, "failed", error=str(e))
        raise e

def get_all_content() -> List[GeneratedContent]:
    """Get all content (for debugging/admin purposes)."""
    return list(_content_storage.values())

def track_download(content_id: str, user_id: str, ip_address: str = None) -> None:
    """Track a download event for analytics."""
    if content_id not in _download_tracking:
        _download_tracking[content_id] = []
    
    _download_tracking[content_id].append({
        "timestamp": datetime.now().isoformat(),
        "userId": user_id,
        "ip": ip_address
    })

def get_download_stats(content_id: str) -> Dict:
    """Get download statistics for a content item."""
    downloads = _download_tracking.get(content_id, [])
    return {
        "total_downloads": len(downloads),
        "downloads": downloads,
        "last_downloaded": downloads[-1]["timestamp"] if downloads else None
    }

def clear_content() -> None:
    """Clear all content (for testing purposes)."""
    global _content_storage
    _content_storage = {}
