# backend/app/pdf_generator.py
# PDF generation functions
import os
import re
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from .models import GenerateContentRequest
from . import deps
from .content_utils import (
    content_client, get_rag_context_for_internal_mode,
    validate_rag_context_for_internal_mode, extract_openai_response,
    clean_markdown_formatting
)


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
    
    print(f"[PDF] Generating EXACTLY {num_pages} pages for {target_audience} at {difficulty} level")
    
    words_per_page = 300
    total_words_needed = num_pages * words_per_page
    
    system_prompt = f"""You are a professional content writer. GENERATE EXACTLY {num_pages} PAGES of content.

STRICT REQUIREMENTS:
1. Write EXACTLY {total_words_needed} words (for {num_pages} pages at ~300 words/page)
2. Target Audience: {target_audience}
3. Difficulty: {difficulty}
4. Structure: Title page + Body sections + Conclusion
5. NO markdown formatting whatsoever
6. NO ** or other special characters
7. Write in clear, proper English sentences
8. Include detailed explanations and examples
9. Break into clear sections with newlines between them

FORMATTING RULES:
- Each section should be 300-400 words
- Use section titles (plain text, no **bold**)
- Separate sections with blank lines
- NO bullet points, NO markdown, NO special formatting
- Write as a professional document

WORD COUNT: {total_words_needed} words minimum"""
    
    if rag_context:
        system_prompt += f"""

IMPORTANT: You are in INTERNAL MODE. Use the provided context from uploaded documents below to create accurate content. Base your content ONLY on the information provided in the context blocks.

CONTEXT FROM UPLOADED DOCUMENTS:
{rag_context}

Instructions:
- Create content based on the information in the context above
- Ensure the content is factually accurate to the source material
- Use specific details and examples from the documents
- Expand on the concepts found in the context to reach the required word count
- If the context doesn't cover the topic fully, create content based on what is available"""

    user_prompt = f"""Create a {num_pages}-page document about: {request.prompt}

MUST REQUIREMENTS:
- Write EXACTLY {total_words_needed} words
- Create {num_pages} full pages of content
- Target audience: {target_audience}
- Difficulty: {difficulty}
- Include detailed explanations
- Include real-world examples
- Professional tone
- NO markdown, NO ** formatting, NO special characters
- Write in plain, clear English

START WRITING NOW - aim for {total_words_needed} words:"""

    try:
        print(f"[PDF] Calling OpenAI API (requesting {total_words_needed} words)...")
        response = content_client.chat.completions.create(
            model=deps.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=4000 + (num_pages * 500)
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
    
    pdf_path = os.path.join(storage_path, "document.pdf")
    
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=50,
        leftMargin=50,
        topMargin=50,
        bottomMargin=50
    )
    
    styles = getSampleStyleSheet()
    story = []
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1a1a4d'),
        spaceAfter=16,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )
    
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontSize=12,
        leading=16,
        spaceAfter=12,
        alignment=4
    )
    
    metadata_style = ParagraphStyle(
        'CustomMetadata',
        parent=styles['Normal'],
        fontSize=11,
        leading=14,
        spaceAfter=8,
        alignment=0,
        fontName='Helvetica'
    )
    
    # Add subject and topic fields if available
    if request.subjectName or request.topicName:
        if request.subjectName:
            story.append(Paragraph(f"<b>Subject:</b> {request.subjectName}", metadata_style))
        if request.topicName:
            story.append(Paragraph(f"<b>Topic:</b> {request.topicName}", metadata_style))
        story.append(Spacer(1, 0.15 * inch))
    
    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
    
    for para in paragraphs:
        if len(para) < 100 and len(para.split()) < 15 and para.isupper():
            story.append(Paragraph(para, heading_style))
            story.append(Spacer(1, 0.1 * inch))
        else:
            story.append(Paragraph(para, body_style))
            story.append(Spacer(1, 0.05 * inch))
    
    try:
        doc.build(story)
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
    
    print(f"[PDF] Generating EXACTLY {num_pages} pages for {target_audience} at {difficulty} level")
    print(f"[PDF] Custom filename: {filename}")
    
    words_per_page = 300
    total_words_needed = num_pages * words_per_page
    
    system_prompt = f"""You are a professional content writer. GENERATE EXACTLY {num_pages} PAGES of content.

STRICT REQUIREMENTS:
1. Write EXACTLY {total_words_needed} words (for {num_pages} pages at ~300 words/page)
2. Target Audience: {target_audience}
3. Difficulty: {difficulty}
4. Structure: Title page + Body sections + Conclusion
5. NO markdown formatting whatsoever
6. NO ** or other special characters
7. Write in clear, proper English sentences
8. Include detailed explanations and examples
9. Break into clear sections with newlines between them

FORMATTING RULES:
- Each section should be 300-400 words
- Use section titles (plain text, no **bold**)
- Separate sections with blank lines
- NO bullet points, NO markdown, NO special formatting
- Write as a professional document

WORD COUNT: {total_words_needed} words minimum"""
    
    if rag_context:
        system_prompt += f"""

IMPORTANT: You are in INTERNAL MODE. Use the provided context from uploaded documents below to create accurate content. Base your content ONLY on the information provided in the context blocks.

CONTEXT FROM UPLOADED DOCUMENTS:
{rag_context}

Instructions:
- Create content based on the information in the context above
- Ensure the content is factually accurate to the source material
- Use specific details and examples from the documents
- Expand on the concepts found in the context to reach the required word count
- If the context doesn't cover the topic fully, create content based on what is available"""

    user_prompt = f"""Create a {num_pages}-page document about: {request.prompt}

MUST REQUIREMENTS:
- Write EXACTLY {total_words_needed} words
- Create {num_pages} full pages of content
- Target audience: {target_audience}
- Difficulty: {difficulty}
- Include detailed explanations
- Include real-world examples
- Professional tone
- NO markdown, NO ** formatting, NO special characters
- Write in plain, clear English

START WRITING NOW - aim for {total_words_needed} words:"""

    try:
        print(f"[PDF] Calling OpenAI API (requesting {total_words_needed} words)...")
        response = content_client.chat.completions.create(
            model=deps.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=4000 + (num_pages * 500)
        )
        
        content = extract_openai_response(response)
        print(f"[PDF] Got {len(content)} characters, {len(content.split())} words")
        
    except Exception as e:
        print(f"[PDF] Error: {e}")
        raise
    
    content = clean_markdown_formatting(content)
    content = re.sub(r'\*\*', '', content)
    content = re.sub(r'__', '', content)
    
    pdf_path = os.path.join(storage_path, filename)
    
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=50,
        leftMargin=50,
        topMargin=50,
        bottomMargin=50
    )
    
    styles = getSampleStyleSheet()
    story = []
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1a1a4d'),
        spaceAfter=16,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )
    
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontSize=12,
        leading=16,
        spaceAfter=12,
        alignment=4
    )
    
    metadata_style = ParagraphStyle(
        'CustomMetadata',
        parent=styles['Normal'],
        fontSize=11,
        leading=14,
        spaceAfter=8,
        alignment=0,
        fontName='Helvetica'
    )
    
    # Add subject and topic fields if available
    if request.subjectName or request.topicName:
        if request.subjectName:
            story.append(Paragraph(f"<b>Subject:</b> {request.subjectName}", metadata_style))
        if request.topicName:
            story.append(Paragraph(f"<b>Topic:</b> {request.topicName}", metadata_style))
        story.append(Spacer(1, 0.15 * inch))
    
    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
    
    for para in paragraphs:
        if len(para) < 100 and len(para.split()) < 15 and para.isupper():
            story.append(Paragraph(para, heading_style))
            story.append(Spacer(1, 0.1 * inch))
        else:
            story.append(Paragraph(para, body_style))
            story.append(Spacer(1, 0.05 * inch))
    
    try:
        doc.build(story)
        print(f"[PDF] Generated: {pdf_path}")
        return pdf_path
    except Exception as e:
        print(f"[PDF] Error building: {e}")
        raise

