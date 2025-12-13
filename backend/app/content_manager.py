# backend/app/content_manager.py
# Main orchestrator for content generation - routes to specialized modules
import os
from typing import Dict, List, Optional
from datetime import datetime
from .models import (
    GeneratedContent, GenerateContentRequest,
    ContentStatus, FlashcardConfig, QuizConfig, AssessmentConfig,
    VideoConfig, AudioConfig, CompilerConfig
)

# Import shared utilities
from . import content_utils
from .content_utils import (
    generate_content_id, validate_custom_path, create_content_directory,
    get_rag_context_for_internal_mode, store_content, update_content_status
)

# Re-export functions for backward compatibility
from .content_utils import get_content, get_user_content

# Import specialized generators
from .educational_content import (
    generate_flashcard_content, generate_quiz_table, generate_assessment_table,
    _parse_markdown_table_to_rows, _write_flashcards_csv_xlsx,
    _write_quiz_csv_xlsx, _write_assessment_csv_xlsx
)
from .pdf_generator import generate_pdf_content_with_path
from .ppt_generator import generate_ppt_content_with_path
from .media_content import generate_video_content, generate_audio_content, generate_compiler_content


async def process_content_generation(request: GenerateContentRequest) -> GeneratedContent:
    """Process content generation with custom filename and path support."""
    content_id = generate_content_id()
    
    # Validate custom path if provided
    if request.customFilePath:
        try:
            validate_custom_path(request.customFilePath)
        except ValueError as e:
            raise Exception(f"Invalid file path: {str(e)}")
    
    # Get RAG metadata for internal mode only (to track which documents were used)
    # For external mode, don't include rag_metadata to avoid displaying "RAG not used"
    metadata_dict = {
        "docIds": request.docIds,
        "subjectName": request.subjectName,
        "topicName": request.topicName,
        "customFileName": request.customFileName,
        "customFilePath": request.customFilePath,
    }

    # Enforce docId requirement for PDF generation in internal mode
    if request.mode == "internal" and request.contentType == "pdf":
        if not request.docIds or len([d for d in request.docIds if str(d).strip()]) == 0:
            raise Exception("At least one docId is required for PDF generation in internal mode.")
    
    if request.mode == "internal":
        try:
            rag_result = get_rag_context_for_internal_mode(request, top_k=5)
            rag_metadata = rag_result.metadata
            print(f"[CONTENT] RAG metadata: {rag_metadata}")
            metadata_dict["rag_metadata"] = rag_metadata  # Only include for internal mode
        except Exception as e:
            print(f"[CONTENT] Error getting RAG metadata: {e}")
            metadata_dict["rag_metadata"] = {"error": str(e), "rag_used": False}
    
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
        metadata=metadata_dict
    )
    
    store_content(content)
    
    try:
        # Determine storage path
        if request.customFilePath:
            storage_path = request.customFilePath
            print(f"[CONTENT] Using custom path: {storage_path}")
        else:
            storage_path = f"./data/content/{request.userId}/{content_id}"
            print(f"[CONTENT] Using default path: {storage_path}")

        # Create-on-write helper so we don't leave empty dirs when validation fails
        def ensure_storage_dir() -> None:
            os.makedirs(storage_path, exist_ok=True)
        
        # Determine filename (base name without extension)
        if request.customFileName:
            base_filename = request.customFileName
        else:
            base_filename = f"content_{content_id[:8]}"
        
        print(f"[CONTENT] Base filename: {base_filename}")
        
        # Generate content based on type
        generated_content = ""
        actual_filename = ""
        
        if request.contentType == "flashcard" and request.contentConfig.get('flashcard'):
            flashcard_config_dict = request.contentConfig.get('flashcard')
            flashcard_config = FlashcardConfig(
                num_cards=flashcard_config_dict.get('num_cards', 5),
                difficulty=flashcard_config_dict.get('difficulty', 'medium')
            )
            generated_content = await generate_flashcard_content(request, flashcard_config)
            rows = _parse_markdown_table_to_rows(generated_content)
            # Create directory only after successful generation, just before writing
            ensure_storage_dir()
            xlsx_path = _write_flashcards_csv_xlsx(storage_path, rows, base_filename=base_filename)
            actual_filename = os.path.basename(xlsx_path)
            file_path = xlsx_path
        elif request.contentType == "quiz" and request.contentConfig.get('quiz'):
            quiz_config_dict = request.contentConfig.get('quiz')
            quiz_config = QuizConfig(
                num_questions=quiz_config_dict.get('num_questions', 5),
                difficulty=quiz_config_dict.get('difficulty', 'medium'),
                question_types=quiz_config_dict.get('question_types', ['multiple_choice'])
            )
            rows = await generate_quiz_table(request, quiz_config)
            # Create directory only after successful generation, just before writing
            ensure_storage_dir()
            xlsx_path = _write_quiz_csv_xlsx(storage_path, rows, base_filename=base_filename, quiz_config=quiz_config)
            actual_filename = os.path.basename(xlsx_path)
            file_path = xlsx_path
        elif request.contentType == "assessment" and request.contentConfig.get('assessment'):
            assessment_config_dict = request.contentConfig.get('assessment')
            assessment_config = AssessmentConfig(**assessment_config_dict)
            rows = await generate_assessment_table(request, assessment_config)
            
            # Create directory only after successful generation, just before writing
            ensure_storage_dir()
            # Pass subject and topic names and base_filename
            xlsx_path = _write_assessment_csv_xlsx(
                storage_path, 
                rows,
                subject_name=request.subjectName or "Subject",
                topic_name=request.topicName or "Topic",
                base_filename=base_filename,
                assessment_config=assessment_config
            )
            
            actual_filename = os.path.basename(xlsx_path)
            file_path = xlsx_path
        elif request.contentType == "video" and request.contentConfig.get('video'):
            video_config_dict = request.contentConfig.get('video')
            video_config = VideoConfig(**video_config_dict)
            generated_content = await generate_video_content(request, video_config, content_id, storage_path, base_filename=base_filename)
            actual_filename = os.path.basename(generated_content)
            file_path = generated_content
        elif request.contentType == "audio" and request.contentConfig.get('audio'):
            audio_config_dict = request.contentConfig.get('audio')
            audio_config = AudioConfig(**audio_config_dict)
            generated_content = await generate_audio_content(request, audio_config, content_id, storage_path, base_filename=base_filename)
            actual_filename = os.path.basename(generated_content)
            file_path = generated_content
        elif request.contentType == "compiler" and request.contentConfig.get('compiler'):
            compiler_config_dict = request.contentConfig.get('compiler')
            compiler_config = CompilerConfig(**compiler_config_dict)
            generated_content = await generate_compiler_content(request, compiler_config)
            # Create directory only after successful generation, just before writing
            ensure_storage_dir()
            actual_filename = f"{base_filename}.py"
            file_path = os.path.join(storage_path, actual_filename)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(generated_content)
        elif request.contentType == "pdf":
            actual_filename = f"{base_filename}.pdf"
            file_path = os.path.join(storage_path, actual_filename)
            await generate_pdf_content_with_path(request, content_id, storage_path, actual_filename)
        elif request.contentType == "ppt":
            actual_filename = f"{base_filename}.pptx"
            file_path = os.path.join(storage_path, actual_filename)
            await generate_ppt_content_with_path(request, content_id, storage_path, actual_filename)
        else:
            raise Exception(f"Unsupported content type: {request.contentType}")
        
        # Get absolute path
        absolute_path = os.path.abspath(file_path)
        storage_directory = os.path.abspath(storage_path)
        
        # Update content status
        update_content_status(content_id, "completed", file_path)
        
        # Update metadata with ACTUAL STORAGE INFO
        content.metadata.update({
            "actualFileName": actual_filename,
            "actualFilePath": absolute_path,
            "storageDirectory": storage_directory
        })
        
        print(f"[CONTENT] Generation completed successfully")
        print(f"[CONTENT] File: {actual_filename}")
        print(f"[CONTENT] Path: {absolute_path}")
        
        return content
        
    except Exception as e:
        print(f"[ERROR] Content generation failed: {str(e)}")
        update_content_status(content_id, "failed", error=str(e))
        
        # Clean up: Remove empty directory if it was created
        try:
            if os.path.exists(storage_path) and os.path.isdir(storage_path):
                # Check if directory is empty
                if not os.listdir(storage_path):
                    os.rmdir(storage_path)
                    print(f"[CONTENT] Removed empty directory: {storage_path}")
        except Exception as cleanup_error:
            print(f"[CONTENT] Warning: Could not clean up directory {storage_path}: {cleanup_error}")
        
        raise e


def get_all_content() -> List[GeneratedContent]:
    """Get all content (for debugging/admin purposes)."""
    return list(content_utils._content_storage.values())


def track_download(content_id: str, user_id: str, ip_address: str = None) -> None:
    """Track a download event for analytics."""
    if content_id not in content_utils._download_tracking:
        content_utils._download_tracking[content_id] = []
    
    content_utils._download_tracking[content_id].append({
        "timestamp": datetime.now().isoformat(),
        "userId": user_id,
        "ip": ip_address
    })


def get_download_stats(content_id: str) -> Dict:
    """Get download statistics for a content item."""
    downloads = content_utils._download_tracking.get(content_id, [])
    return {
        "total_downloads": len(downloads),
        "downloads": downloads,
        "last_downloaded": downloads[-1]["timestamp"] if downloads else None
    }


def clear_content() -> None:
    """Clear all content (for testing purposes)."""
    content_utils._content_storage.clear()
