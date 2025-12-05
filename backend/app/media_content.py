# backend/app/media_content.py
# Media content generation: audio, video, compiler
import os
from datetime import datetime
from .models import GenerateContentRequest, VideoConfig, AudioConfig, CompilerConfig
from . import deps
from . import media_generator
from .content_utils import (
    content_client, get_rag_context_for_internal_mode,
    validate_rag_context_for_internal_mode, extract_openai_response
)


async def generate_video_content(request: GenerateContentRequest, config: VideoConfig, content_id: str, storage_path: str, base_filename: str = "video") -> str:
    """Generate video script file."""
    if not content_client:
        raise Exception("OpenAI client not configured")
    
    # Get RAG context for internal mode
    rag_result = get_rag_context_for_internal_mode(request, top_k=5)
    validate_rag_context_for_internal_mode(rag_result, request)  # Validate context relevance
    rag_context = rag_result.context
    
    # Generate the video script
    system_prompt = f"""You are a video content generator. Create engaging video content with the following specifications:
- Duration: {config.duration_seconds} seconds
- Quality: {config.quality}
- Include subtitles: {config.include_subtitles}
- User role: {request.role}
- Make it engaging and suitable for video consumption"""
    
    if rag_context:
        system_prompt += f"""

IMPORTANT: You are in INTERNAL MODE. Use the provided context from uploaded documents below to create accurate video content. Base your content ONLY on the information provided in the context blocks.

CONTEXT FROM UPLOADED DOCUMENTS:
{rag_context}

Instructions:
- Create video content based on the information in the context above
- Ensure the content is factually accurate to the source material
- Use specific details from the documents
- If the context doesn't cover the topic fully, create content based on what is available"""
    
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
    
    script_content = extract_openai_response(response)
    
    # Save script file
    try:
        script_path = os.path.join(storage_path, f"{base_filename}_script.txt")
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(f"Video Script:\n\n{script_content}\n\n")
            f.write(f"Duration: {config.duration_seconds} seconds\n")
            f.write(f"Quality: {config.quality}\n")
            f.write(f"Subtitles: {config.include_subtitles}\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
        return script_path
            
    except Exception as e:
        script_path = os.path.join(storage_path, f"{base_filename}_script.txt")
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(f"Error generating video: {str(e)}\n\nScript: {script_content}")
        return script_path


async def generate_audio_content(request: GenerateContentRequest, config: AudioConfig, content_id: str, storage_path: str, base_filename: str = "audio") -> str:
    """Generate audio script file and MP3 audio file."""
    if not content_client:
        raise Exception("OpenAI client not configured")
    
    # Get RAG context for internal mode
    rag_result = get_rag_context_for_internal_mode(request, top_k=5)
    validate_rag_context_for_internal_mode(rag_result, request)  # Validate context relevance
    rag_context = rag_result.context
    
    # Generate the script content
    # IMPORTANT: We need ONLY the spoken script text, no meta-commentary or disclaimers
    system_prompt = f"""You are a professional script writer for audio content. Your task is to write ONLY the spoken script text that will be converted to speech using text-to-speech technology.

CRITICAL RULES:
- Write ONLY the actual spoken words that will be read aloud
- NO meta-commentary, NO disclaimers, NO instructions about audio creation
- NO phrases like "I'm unable to create audio files" or "here's a script"
- Write as if you are the narrator/speaker directly addressing the audience
- The text you write will be directly converted to speech - write it naturally
- Duration target: approximately {config.duration_seconds} seconds when spoken
- Target audience: {request.role}
- Make it engaging, conversational, and suitable for audio listening"""
    
    if rag_context:
        system_prompt += f"""

IMPORTANT: You are in INTERNAL MODE. Use the provided context from uploaded documents below to create an accurate audio script. Base your content ONLY on the information provided in the context blocks.

CONTEXT FROM UPLOADED DOCUMENTS:
{rag_context}

Instructions:
- Create the audio script based on the information in the context above
- Ensure the content is factually accurate to the source material
- Use specific details from the documents
- If the context doesn't cover the topic fully, create content based on what is available"""
    
    user_prompt = f"""Write the spoken script for an audio recording about: {request.prompt}

Requirements:
- Write ONLY the spoken words (no meta-commentary)
- Target duration: {config.duration_seconds} seconds when spoken
- Write naturally as if speaking directly to the listener
- Be engaging and conversational
- Start immediately with the content (no introductions about scripts or audio files)

Begin the script now:"""
    
    response = content_client.chat.completions.create(
        model=deps.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    
    script_content = extract_openai_response(response)
    original_script = script_content  # Keep original for fallback
    
    # Clean up the script content - remove common meta-commentary patterns
    # Remove disclaimers and meta-text that shouldn't be spoken
    unwanted_patterns = [
        "I'm unable to create audio files",
        "I can provide you with a script",
        "here's a script",
        "here is a script",
        "script that you can use",
        "[Upbeat background music begins]",
        "[Background music",
        "**Narrator:**",
        "**Narrator**",
    ]
    
    # Remove lines that contain unwanted patterns
    lines = script_content.split('\n')
    cleaned_lines = []
    for line in lines:
        line_lower = line.lower().strip()
        # Skip lines that are just separators or contain unwanted patterns
        if any(pattern.lower() in line_lower for pattern in unwanted_patterns):
            continue
        # Skip markdown-style separators (---)
        if line.strip() == '---' or (line.strip().startswith('---') and len(line.strip()) <= 5):
            continue
        # Keep the line if it's actual content
        if line.strip():
            cleaned_lines.append(line)
    
    script_content = '\n'.join(cleaned_lines).strip()
    
    # If the script is empty after cleaning, use the original with minimal cleaning (fallback)
    if not script_content or len(script_content) < 50:
        print("[Audio] Warning: Script content was mostly meta-commentary, using original with minimal cleaning")
        # Try a gentler cleanup - just remove obvious markdown formatting
        script_content = original_script.replace('**', '').replace('---', '').strip()
    
    # Save script file
    try:
        script_path = os.path.join(storage_path, f"{base_filename}_script.txt")
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_content)
    except Exception as e:
        script_path = os.path.join(storage_path, f"{base_filename}_script.txt")
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(f"Error generating audio: {str(e)}\n\nScript: {script_content}")
    
    # Generate MP3 file using TTS
    try:
        # Map voice_type to OpenAI TTS voices
        # Female voices: alloy, nova, shimmer
        # Male voices: echo, fable, onyx
        voice_map = {
            "female": "nova",  # Default female voice
            "male": "onyx"     # Default male voice
        }
        voice = voice_map.get(config.voice_type, "alloy")
        
        # Map quality to TTS model
        # high -> tts-1-hd, medium/low -> tts-1
        model_map = {
            "high": "tts-1-hd",
            "medium": "tts-1",
            "low": "tts-1"
        }
        tts_model = model_map.get(config.quality.lower(), "tts-1")
        
        # Determine output format
        audio_format = config.format.lower() if config.format else "mp3"
        
        # Generate MP3 file path using base_filename
        audio_path = os.path.join(storage_path, f"{base_filename}.{audio_format}")
        
        # Generate the audio file using TTS
        success = await media_generator.generate_audio_file(
            text=script_content,
            output_path=audio_path,
            voice=voice,
            model=tts_model,
            format=audio_format
        )
        
        if success:
            print(f"[Audio] Successfully generated MP3 file: {audio_path}")
            return audio_path
        else:
            print(f"[Audio] Failed to generate MP3, returning script path instead")
            return script_path
            
    except Exception as e:
        print(f"[Audio] Error generating MP3 file: {e}")
        # Return script path as fallback
        return script_path


async def generate_compiler_content(request: GenerateContentRequest, config: CompilerConfig) -> str:
    """Generate compiler/code content."""
    if not content_client:
        raise Exception("OpenAI client not configured")
    
    # Get RAG context for internal mode
    rag_result = get_rag_context_for_internal_mode(request, top_k=5)
    validate_rag_context_for_internal_mode(rag_result, request)  # Validate context relevance
    rag_context = rag_result.context
    
    system_prompt = f"""You are a code generator. Create code with the following specifications:
- Language: {config.language}
- Include tests: {config.include_tests}
- Difficulty: {config.difficulty}
- User role: {request.role}"""
    
    if rag_context:
        system_prompt += f"""

IMPORTANT: You are in INTERNAL MODE. Use the provided context from uploaded documents below to create accurate code. Base your code ONLY on the information provided in the context blocks.

CONTEXT FROM UPLOADED DOCUMENTS:
{rag_context}

Instructions:
- Create code based on the information in the context above
- Follow coding patterns and examples from the documents
- Ensure the code aligns with the concepts explained in the source material
- If the context doesn't cover the topic fully, create code based on what is available"""
    
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
    
    return extract_openai_response(response)

