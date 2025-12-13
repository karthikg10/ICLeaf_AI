# backend/app/pdf_generator.py
# PDF generation functions
import os
import re
import tempfile
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.enums import TA_LEFT
from PIL import Image, ImageDraw, ImageFont
from .models import GenerateContentRequest
from . import deps
from .content_utils import (
    content_client, get_rag_context_for_internal_mode,
    validate_rag_context_for_internal_mode, extract_openai_response,
    clean_markdown_formatting
)


def _add_watermark(canvas: Canvas, doc) -> None:
    """Draw a subtle ICLeaF watermark across the page background.
    The watermark is rendered as an image (not text) to make it unselectable."""
    canvas.saveState()
    width, height = doc.pagesize
    
    # Create watermark text as an image to make it unselectable
    text = "ICLeaF"
    font_size = 60
    
    # Create a transparent image with the watermark text
    # Use a larger size to ensure good quality
    img_width, img_height = 300, 100
    img = Image.new('RGBA', (img_width, img_height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    # Try to use a bold font, fallback to default if not available
    font = None
    try:
        # Try common system font paths
        font_paths = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/Windows/Fonts/arial.ttf",
        ]
        for path in font_paths:
            try:
                font = ImageFont.truetype(path, font_size)
                break
            except:
                continue
    except:
        pass
    
    if font is None:
        try:
            # Try to load default bold font
            font = ImageFont.load_default()
        except:
            font = None
    
    # Get text bounding box to center it
    if font:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    else:
        # Fallback: estimate size
        text_width = len(text) * font_size * 0.6
        text_height = font_size
    
    # Draw text in light gray (RGB: 224, 224, 224 which is 0.88 in 0-255 scale)
    text_x = (img_width - text_width) // 2
    text_y = (img_height - text_height) // 2
    draw.text((text_x, text_y), text, fill=(224, 224, 224, 180), font=font)  # 180 alpha for subtlety
    
    # Save image to a temporary file (ReportLab's drawImage needs a file path or PIL Image)
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
        img.save(tmp_file.name, format='PNG')
        tmp_path = tmp_file.name
    
    try:
        # Position and rotate the watermark
        canvas.translate(width / 2.0, height / 2.0)
        canvas.rotate(30)
        
        # Draw the image (centered, accounting for image size)
        # ReportLab's drawImage can accept a file path
        canvas.drawImage(tmp_path, -img_width // 2, -img_height // 2, 
                         width=img_width, height=img_height, mask='auto')
    finally:
        # Clean up temporary file
        try:
            os.unlink(tmp_path)
        except:
            pass
    
    canvas.restoreState()


def _add_header_footer(canvas: Canvas, doc, subject: str = "", topic: str = "") -> None:
    """Add header (subject/topic) and footer (page number)."""
    canvas.saveState()
    width, height = doc.pagesize

    header_text = " • ".join([v for v in [subject, topic] if v])
    canvas.setFont("Helvetica-Bold", 9)
    canvas.setFillColorRGB(0.15, 0.15, 0.2)
    if header_text:
        canvas.drawString(50, height - 25, header_text)

    canvas.setFont("Helvetica", 8)
    canvas.setFillColorRGB(0.2, 0.2, 0.2)
    canvas.drawRightString(width - 50, 20, f"Page {doc.page}")

    canvas.restoreState()


async def generate_pdf_content(request: GenerateContentRequest, content_id: str, storage_path: str) -> str:
    """Generate PDF with STRICT page count control."""
    if not content_client:
        raise Exception("OpenAI client not configured")
    
    # Get RAG context for internal mode
    rag_result = get_rag_context_for_internal_mode(request, top_k=5)
    validate_rag_context_for_internal_mode(rag_result, request)  # Validate context relevance
    rag_context = rag_result.context
    
    pdf_config = request.contentConfig.get('pdf', {})
    num_pages = int(pdf_config.get('num_pages', 5))
    target_audience = pdf_config.get('target_audience', 'general')
    include_images = pdf_config.get('include_images', True)
    difficulty = pdf_config.get('difficulty', 'medium')
    
    # Get words_per_page with validation (200-1000 range)
    words_per_page = int(pdf_config.get('words_per_page', 480))
    words_per_page = max(200, min(1000, words_per_page))  # Clamp between 200-1000
    
    total_words_needed = num_pages * words_per_page
    
    print(f"[PDF] Generating EXACTLY {num_pages} pages for {target_audience} at {difficulty} level")
    print(f"[PDF] Target: {total_words_needed} words ({words_per_page} words/page)")
    
    system_prompt = f"""You are a professional content writer. GENERATE EXACTLY {num_pages} PAGES of content.

STRICT REQUIREMENTS:
1. You MUST write EXACTLY {total_words_needed} words - this is MANDATORY and NOT optional
2. Target Audience: {target_audience}
3. Difficulty: {difficulty}
4. Structure: Introduction + Multiple detailed sections + Conclusion
5. NO markdown formatting (no #, no **, no __)
6. Write in clear, proper English sentences
7. Include extensive detailed explanations, examples, use cases, and elaborations
8. Break into clear sections with newlines between them
9. Continue writing even if you think you've covered the topic - add more examples and details

FORMATTING RULES FOR HEADINGS AND STRUCTURE:
- CRITICAL: You MUST include clear headings and subheadings to structure your content
- Main headings (H1): Write in ALL CAPS or Title Case, keep them short (5-15 words), put each on its own line
- Subheadings (H2): Write in Title Case, keep them short (3-12 words), put each on its own line
- Example heading format:
  INTRODUCTION
  (blank line)
  Main content paragraph here...
  
  KEY CONCEPTS
  (blank line)
  Main content paragraph here...
  
  Advanced Topics
  (blank line)
  Main content paragraph here...
- Each major section should be 300-500 words
- Separate sections with blank lines
- NO bullet points, NO markdown symbols (#, **, __), NO special formatting characters
- Write as a professional document with clear hierarchical structure
- Expand extensively on each concept to reach the word count

WORD COUNT: You MUST generate at least {total_words_needed} words. Do NOT stop until you reach this exact word count. Keep writing until you reach {total_words_needed} words.

IMPORTANT: Do NOT include word count information (like "Word Count: X words") in the generated content. Write only the actual document content."""
    
    if rag_context:
        system_prompt += f"""

IMPORTANT: You are in INTERNAL MODE. Use the provided context from uploaded documents below to create accurate content. Base your content ONLY on the information provided in the context blocks.

CONTEXT FROM UPLOADED DOCUMENTS:
{rag_context}

Instructions:
- Create content based on the information in the context above
- Ensure the content is factually accurate to the source material
- Use specific details and examples from the documents
- Expand extensively on the concepts found in the context to reach the required {total_words_needed} words
- Add multiple examples, use cases, practical applications, common mistakes, best practices
- If the context doesn't cover the topic fully, create content based on what is available and expand it
- CRITICAL: Continue writing until you reach {total_words_needed} words - do not stop early"""

    user_prompt = f"""Create a {num_pages}-page document about: {request.prompt}

CRITICAL REQUIREMENTS:
- You MUST write EXACTLY {total_words_needed} words - this is MANDATORY
- Create {num_pages} full pages of detailed content
- Target audience: {target_audience}
- Difficulty: {difficulty}
- Include extensive detailed explanations
- Include multiple real-world examples, use cases, and practical applications
- Add common mistakes, best practices, and troubleshooting tips
- Professional, educational tone
- NO markdown symbols (#, **, __), NO special formatting characters
- Write in plain, clear English paragraphs

STRUCTURE REQUIREMENTS:
- MUST include clear headings and subheadings to organize the content
- Use ALL CAPS or Title Case for main headings (one per major section)
- Use Title Case for subheadings (for subsections)
- Put each heading on its own line, followed by a blank line, then the content
- Example structure:
  INTRODUCTION
  [blank line]
  Content paragraph here...
  
  MAIN CONCEPTS
  [blank line]
  Content paragraph here...
  
  Advanced Applications
  [blank line]
  Content paragraph here...

IMPORTANT: Do NOT stop writing until you reach {total_words_needed} words. Continue adding content even if you think the topic is covered. Add more examples, explanations, and details until you reach the exact word count.

CRITICAL: Do NOT include any word count statements (like "Word Count: X words") in your output. Write only the document content itself.

START WRITING NOW - you must write {total_words_needed} words with clear headings and structure:"""

    try:
        print(f"[PDF] Calling OpenAI API (requesting {total_words_needed} words)...")
        response = content_client.chat.completions.create(
            model=deps.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=4000 + (total_words_needed // 2)  # Dynamic based on words needed
        )
        
        content = extract_openai_response(response)
        print(f"[PDF] Got {len(content)} characters, {len(content.split())} words")
        
    except Exception as e:
        print(f"[PDF] Error: {e}")
        raise
    
    content = clean_markdown_formatting(content)
    content = re.sub(r'\*\*', '', content)
    content = re.sub(r'__', '', content)
    content = re.sub(r'\*(?!\s)', '', content)
    # Remove word count mentions from content
    content = re.sub(r'(?i)word\s+count[:\s]*\d+\s+words?', '', content)
    content = re.sub(r'(?i)total\s+words?[:\s]*\d+', '', content)
    
    # Create storage path only after validation/generation succeeded to avoid empty dirs
    os.makedirs(storage_path, exist_ok=True)

    pdf_path = os.path.join(storage_path, "document.pdf")
    
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=60,    # ~0.83"
        rightMargin=60,
        topMargin=72,     # 1"
        bottomMargin=72,
    )
    
    styles = getSampleStyleSheet()
    story = []
    
    # Typography hierarchy: Title, H1, H2, Body
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=28,
        textColor=colors.HexColor("#1a1a4d"),
        spaceAfter=18,
    )
    
    h1_style = ParagraphStyle(
        "Heading1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#1a1a4d"),
        spaceBefore=12,
        spaceAfter=8,
    )
    
    h2_style = ParagraphStyle(
        "Heading2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=colors.HexColor("#333333"),
        spaceBefore=10,
        spaceAfter=6,
    )
    
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,       # ~1.35 line spacing
        spaceAfter=8,
        alignment=4,      # justified
    )
    
    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
    
    # Enhanced heading detection with hierarchy
    is_first_heading = True
    for para in paragraphs:
        word_count = len(para.split())
        char_count = len(para)
        
        # Detect Title (first heading, typically longer)
        if is_first_heading and char_count < 150 and word_count < 20 and (para.isupper() or para[0].isupper()):
            story.append(Paragraph(para, title_style))
            story.append(Spacer(1, 0.15 * inch))
            is_first_heading = False
        # Detect H1 (uppercase or title case, short, typically major sections)
        elif char_count < 100 and word_count < 15 and (para.isupper() or (para[0].isupper() and word_count < 10)):
            story.append(Paragraph(para, h1_style))
            story.append(Spacer(1, 0.1 * inch))
            is_first_heading = False
        # Detect H2 (shorter than body, title case, typically subsections)
        elif char_count < 80 and word_count < 12 and para[0].isupper() and not para.isupper():
            story.append(Paragraph(para, h2_style))
            story.append(Spacer(1, 0.08 * inch))
        # Body text
        else:
            story.append(Paragraph(para, body_style))
            story.append(Spacer(1, 0.05 * inch))
    
    try:
        doc.build(
            story,
            onFirstPage=lambda c, d: (_add_watermark(c, d), _add_header_footer(c, d, request.subjectName or "", request.topicName or "")),
            onLaterPages=lambda c, d: (_add_watermark(c, d), _add_header_footer(c, d, request.subjectName or "", request.topicName or "")),
        )
        print(f"[PDF] Generated {pdf_path}")
        return pdf_path
    except Exception as e:
        print(f"[PDF] Error building: {e}")
        raise


async def generate_pdf_content_with_path(
    request: GenerateContentRequest, 
    content_id: str, 
    storage_path: str,
    filename: str
) -> str:
    """Generate PDF with custom filename."""
    if not content_client:
        raise Exception("OpenAI client not configured")
    
    # Get RAG context for internal mode
    rag_result = get_rag_context_for_internal_mode(request, top_k=5)
    validate_rag_context_for_internal_mode(rag_result, request)  # Validate context relevance
    rag_context = rag_result.context
    
    pdf_config = request.contentConfig.get('pdf', {})
    num_pages = int(pdf_config.get('num_pages', 5))
    target_audience = pdf_config.get('target_audience', 'general')
    include_images = pdf_config.get('include_images', True)
    difficulty = pdf_config.get('difficulty', 'medium')
    
    # Get words_per_page with validation (200-1000 range)
    words_per_page = int(pdf_config.get('words_per_page', 480))
    words_per_page = max(200, min(1000, words_per_page))  # Clamp between 200-1000
    
    total_words_needed = num_pages * words_per_page
    
    print(f"[PDF] Generating EXACTLY {num_pages} pages for {target_audience} at {difficulty} level")
    print(f"[PDF] Custom filename: {filename}")
    print(f"[PDF] Target: {total_words_needed} words ({words_per_page} words/page)")
    
    system_prompt = f"""You are a professional content writer. GENERATE EXACTLY {num_pages} PAGES of content.

STRICT REQUIREMENTS:
1. You MUST write EXACTLY {total_words_needed} words - this is MANDATORY and NOT optional
2. Target Audience: {target_audience}
3. Difficulty: {difficulty}
4. Structure: Introduction + Multiple detailed sections + Conclusion
5. NO markdown formatting (no #, no **, no __)
6. Write in clear, proper English sentences
7. Include extensive detailed explanations, examples, use cases, and elaborations
8. Break into clear sections with newlines between them
9. Continue writing even if you think you've covered the topic - add more examples and details

FORMATTING RULES FOR HEADINGS AND STRUCTURE:
- CRITICAL: You MUST include clear headings and subheadings to structure your content
- Main headings (H1): Write in ALL CAPS or Title Case, keep them short (5-15 words), put each on its own line
- Subheadings (H2): Write in Title Case, keep them short (3-12 words), put each on its own line
- Example heading format:
  INTRODUCTION
  (blank line)
  Main content paragraph here...
  
  KEY CONCEPTS
  (blank line)
  Main content paragraph here...
  
  Advanced Topics
  (blank line)
  Main content paragraph here...
- Each major section should be 300-500 words
- Separate sections with blank lines
- NO bullet points, NO markdown symbols (#, **, __), NO special formatting characters
- Write as a professional document with clear hierarchical structure
- Expand extensively on each concept to reach the word count

WORD COUNT: You MUST generate at least {total_words_needed} words. Do NOT stop until you reach this exact word count. Keep writing until you reach {total_words_needed} words.

IMPORTANT: Do NOT include word count information (like "Word Count: X words") in the generated content. Write only the actual document content."""
    
    if rag_context:
        system_prompt += f"""

IMPORTANT: You are in INTERNAL MODE. Use the provided context from uploaded documents below to create accurate content. Base your content ONLY on the information provided in the context blocks.

CONTEXT FROM UPLOADED DOCUMENTS:
{rag_context}

Instructions:
- Create content based on the information in the context above
- Ensure the content is factually accurate to the source material
- Use specific details and examples from the documents
- Expand extensively on the concepts found in the context to reach the required {total_words_needed} words
- Add multiple examples, use cases, practical applications, common mistakes, best practices
- If the context doesn't cover the topic fully, create content based on what is available and expand it
- CRITICAL: Continue writing until you reach {total_words_needed} words - do not stop early"""

    user_prompt = f"""Create a {num_pages}-page document about: {request.prompt}

CRITICAL REQUIREMENTS:
- You MUST write EXACTLY {total_words_needed} words - this is MANDATORY
- Create {num_pages} full pages of detailed content
- Target audience: {target_audience}
- Difficulty: {difficulty}
- Include extensive detailed explanations
- Include multiple real-world examples, use cases, and practical applications
- Add common mistakes, best practices, and troubleshooting tips
- Professional, educational tone
- NO markdown symbols (#, **, __), NO special formatting characters
- Write in plain, clear English paragraphs

STRUCTURE REQUIREMENTS:
- MUST include clear headings and subheadings to organize the content
- Use ALL CAPS or Title Case for main headings (one per major section)
- Use Title Case for subheadings (for subsections)
- Put each heading on its own line, followed by a blank line, then the content
- Example structure:
  INTRODUCTION
  [blank line]
  Content paragraph here...
  
  MAIN CONCEPTS
  [blank line]
  Content paragraph here...
  
  Advanced Applications
  [blank line]
  Content paragraph here...

IMPORTANT: Do NOT stop writing until you reach {total_words_needed} words. Continue adding content even if you think the topic is covered. Add more examples, explanations, and details until you reach the exact word count.

CRITICAL: Do NOT include any word count statements (like "Word Count: X words") in your output. Write only the document content itself.

START WRITING NOW - you must write {total_words_needed} words with clear headings and structure:"""

    try:
        print(f"[PDF] Calling OpenAI API (requesting {total_words_needed} words)...")
        response = content_client.chat.completions.create(
            model=deps.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=4000 + (total_words_needed // 2)  # Dynamic based on words needed
        )
        
        content = extract_openai_response(response)
        print(f"[PDF] Got {len(content)} characters, {len(content.split())} words")
        
    except Exception as e:
        print(f"[PDF] Error: {e}")
        raise
    
    content = clean_markdown_formatting(content)
    content = re.sub(r'\*\*', '', content)
    content = re.sub(r'__', '', content)
    # Remove word count mentions from content
    content = re.sub(r'(?i)word\s+count[:\s]*\d+\s+words?', '', content)
    content = re.sub(r'(?i)total\s+words?[:\s]*\d+', '', content)
    
    # Create storage path only after validation/generation succeeded to avoid empty dirs
    os.makedirs(storage_path, exist_ok=True)

    pdf_path = os.path.join(storage_path, filename)
    
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=60,    # ~0.83"
        rightMargin=60,
        topMargin=72,     # 1"
        bottomMargin=72,
    )
    
    styles = getSampleStyleSheet()
    story = []
    
    # Typography hierarchy: Title, H1, H2, Body
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=28,
        textColor=colors.HexColor("#1a1a4d"),
        spaceAfter=18,
    )
    
    h1_style = ParagraphStyle(
        "Heading1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#1a1a4d"),
        spaceBefore=12,
        spaceAfter=8,
    )
    
    h2_style = ParagraphStyle(
        "Heading2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=colors.HexColor("#333333"),
        spaceBefore=10,
        spaceAfter=6,
    )
    
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,       # ~1.35 line spacing
        spaceAfter=8,
        alignment=4,      # justified
    )
    
    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
    
    # Enhanced heading detection with hierarchy
    is_first_heading = True
    for para in paragraphs:
        word_count = len(para.split())
        char_count = len(para)
        
        # Detect Title (first heading, typically longer)
        if is_first_heading and char_count < 150 and word_count < 20 and (para.isupper() or para[0].isupper()):
            story.append(Paragraph(para, title_style))
            story.append(Spacer(1, 0.15 * inch))
            is_first_heading = False
        # Detect H1 (uppercase or title case, short, typically major sections)
        elif char_count < 100 and word_count < 15 and (para.isupper() or (para[0].isupper() and word_count < 10)):
            story.append(Paragraph(para, h1_style))
            story.append(Spacer(1, 0.1 * inch))
            is_first_heading = False
        # Detect H2 (shorter than body, title case, typically subsections)
        elif char_count < 80 and word_count < 12 and para[0].isupper() and not para.isupper():
            story.append(Paragraph(para, h2_style))
            story.append(Spacer(1, 0.08 * inch))
        # Body text
        else:
            story.append(Paragraph(para, body_style))
            story.append(Spacer(1, 0.05 * inch))
    
    try:
        doc.build(
            story,
            onFirstPage=lambda c, d: (_add_watermark(c, d), _add_header_footer(c, d, request.subjectName or "", request.topicName or "")),
            onLaterPages=lambda c, d: (_add_watermark(c, d), _add_header_footer(c, d, request.subjectName or "", request.topicName or "")),
        )
        print(f"[PDF] Generated: {pdf_path}")
        return pdf_path
    except Exception as e:
        print(f"[PDF] Error building: {e}")
        raise

