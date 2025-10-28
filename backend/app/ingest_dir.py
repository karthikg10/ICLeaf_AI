# backend/app/ingest_dir.py
import os, re
from typing import List, Tuple, Dict

def chunk_text(text: str, max_chars: int = 1200, overlap: int = 150) -> List[str]:
    if not text:
        return []
    text = re.sub(r"\s+", " ", text).strip()
    chunks, n, start = [], len(text), 0
    while start < n:
        end = min(start + max_chars, n)
        chunks.append(text[start:end])
        if end >= n:
            break
        start = max(0, end - overlap)
    return chunks

def _pretty_title_from_filename(path: str) -> str:
    base = os.path.basename(path)
    name, _ = os.path.splitext(base)
    return re.sub(r"[_\-]+", " ", name).strip()

def _read_pdf_with_pages(path: str) -> List[Tuple[int, str]]:
    """Return list of (page_no_1based, text). Falls back to OCR if page is empty (optional)."""
    import pypdf
    pages: List[Tuple[int, str]] = []
    pdf = pypdf.PdfReader(path)
    for i, pg in enumerate(pdf.pages):
        txt = pg.extract_text() or ""
        if not txt.strip():
            # --- Optional OCR fallback per page ---
            try:
                import pytesseract
                from pdf2image import convert_from_path
                from PIL import Image
                # Render a single page (faster than all pages)
                img_list = convert_from_path(path, first_page=i+1, last_page=i+1, dpi=200)
                ocr_txt = ""
                for img in img_list:
                    if not isinstance(img, Image.Image):
                        continue
                    ocr_txt += pytesseract.image_to_string(img) or ""
                txt = ocr_txt
            except Exception as e:
                print(f"[ingest] PDF page {i+1} empty and OCR unavailable for {path}: {e}")
        pages.append((i+1, txt))
    return pages

def _read_file_build_docs(path: str) -> List[Tuple[str, Dict]]:
    """Return docs as (chunk_text, meta) with meta including filename, title, page (if PDF)."""
    docs: List[Tuple[str, Dict]] = []
    ext = os.path.splitext(path)[1].lower()

    if ext in [".txt", ".md"]:
        text = open(path, "r", encoding="utf-8", errors="ignore").read()
        title = _pretty_title_from_filename(path)
        for i, ch in enumerate(chunk_text(text)):
            docs.append((ch, {"id": f"{title}-{i}", "filename": os.path.basename(path), "title": title}))
        return docs

    if ext == ".pdf":
        title = _pretty_title_from_filename(path)
        try:
            for page_no, page_txt in _read_pdf_with_pages(path):
                if not page_txt.strip():
                    continue
                for j, ch in enumerate(chunk_text(page_txt)):
                    docs.append((ch, {
                        "id": f"{title}-p{page_no}-{j}",
                        "filename": os.path.basename(path),
                        "title": title,
                        "page": page_no
                    }))
        except Exception as e:
            print(f"[ingest] ERROR reading PDF {path}: {e}")
        return docs

    if ext == ".docx":
        try:
            import docx
            d = docx.Document(path)
            text = "\n".join(p.text for p in d.paragraphs)
            title = _pretty_title_from_filename(path)
            for i, ch in enumerate(chunk_text(text)):
                docs.append((ch, {"id": f"{title}-{i}", "filename": os.path.basename(path), "title": title}))
        except Exception as e:
            print(f"[ingest] ERROR reading DOCX {path}: {e}")
        return docs

    if ext == ".pptx":
        try:
            from pptx import Presentation
            prs = Presentation(path)
            title = _pretty_title_from_filename(path)
            buffer = []
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        buffer.append(shape.text)
            text = "\n".join(buffer)
            for i, ch in enumerate(chunk_text(text)):
                docs.append((ch, {"id": f"{title}-{i}", "filename": os.path.basename(path), "title": title}))
        except Exception as e:
            print(f"[ingest] ERROR reading PPTX {path}: {e}")
        return docs

    # Unsupported
    return docs

def build_docs_for_dir(root_dir: str) -> List[Tuple[str, Dict]]:
    out: List[Tuple[str, Dict]] = []
    if not root_dir or not os.path.isdir(root_dir):
        print(f"[ingest] Directory not found: {root_dir}")
        return out

    print(f"[ingest] Scanning {root_dir} ...")
    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            path = os.path.join(dirpath, fn)
            ext = os.path.splitext(path)[1].lower()
            if ext not in [".txt", ".md", ".pdf", ".docx", ".pptx"]:
                print(f"[ingest] Skip unsupported: {path}")
                continue
            docs = _read_file_build_docs(path)
            if not docs:
                print(f"[ingest] Empty or unreadable: {path}")
                continue
            print(f"[ingest] OK {os.path.basename(path)}: +{len(docs)} chunks")
            out.extend(docs)
    return out

import app.rag_store_chromadb as rag

def ingest_dir(root_dir: str, subject_id: str = None, topic_id: str = None, uploaded_by: str = None) -> int:
    docs = build_docs_for_dir(root_dir)
    if docs:
        # Add metadata to each document if provided
        if subject_id or topic_id or uploaded_by:
            enhanced_docs = []
            for text, meta in docs:
                enhanced_meta = meta.copy()
                if subject_id:
                    enhanced_meta["subjectId"] = subject_id
                if topic_id:
                    enhanced_meta["topicId"] = topic_id
                if uploaded_by:
                    enhanced_meta["uploadedBy"] = uploaded_by
                enhanced_docs.append((text, enhanced_meta))
            docs = enhanced_docs
        
        rag.add_documents(docs)
    print(f"[ingest] Total chunks to add: {len(docs)}")
    return len(docs)
