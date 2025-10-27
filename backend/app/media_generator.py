"""
Media generation service for audio and video content.
Supports OpenAI TTS for audio and AI-generated video content.
"""
import os
import asyncio
from datetime import datetime
from typing import Optional
from openai import OpenAI
from . import deps

# Initialize OpenAI client
client = OpenAI(api_key=deps.OPENAI_API_KEY) if deps.OPENAI_API_KEY else None

async def generate_audio_file(
    text: str,
    output_path: str,
    voice: str = "alloy",
    model: str = "tts-1",
    format: str = "mp3"
) -> bool:
    """
    Generate an MP3 audio file from text using OpenAI TTS.
    
    Args:
        text: Text to convert to speech
        output_path: Path where to save the MP3 file
        voice: Voice to use (alloy, echo, fable, onyx, nova, shimmer)
        model: TTS model to use (tts-1, tts-1-hd)
        format: Audio format (mp3, opus, aac, flac)
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not client:
        print("OpenAI client not configured for TTS")
        return False
    
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Generate speech using OpenAI TTS
        response = client.audio.speech.create(
            model=model,
            voice=voice,
            input=text,
            response_format=format
        )
        
        # Save the audio file
        with open(output_path, 'wb') as f:
            for chunk in response.iter_bytes():
                f.write(chunk)
        
        print(f"Audio file generated: {output_path}")
        return True
        
    except Exception as e:
        print(f"Error generating audio: {e}")
        return False

async def generate_video_file(
    script: str,
    output_path: str,
    duration_seconds: int = 60,
    quality: str = "720p"
) -> bool:
    """
    Generate a video script file (fallback due to MoviePy issues).
    
    Args:
        script: Video script/content
        output_path: Path where to save the video file
        duration_seconds: Duration of the video
        quality: Video quality (480p, 720p, 1080p)
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # For now, create a detailed script file instead of actual video
        # This is a fallback due to MoviePy/ImageMagick issues
        script_content = f"""VIDEO SCRIPT
================

Title: AI Generated Video Content
Duration: {duration_seconds} seconds
Quality: {quality}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

CONTENT:
{script}

VIDEO STRUCTURE:
- Intro (5 seconds): Title slide with background
- Main Content ({duration_seconds-10} seconds): Key points with text overlay
- Outro (5 seconds): Summary and conclusion

TECHNICAL SPECIFICATIONS:
- Resolution: {quality}
- Frame Rate: 24 fps
- Codec: H.264
- Audio: Background music (optional)

NOTES:
This is a video script that can be used with video editing software
to create the actual video content. The script contains all the
necessary information for video production.

For actual video generation, MoviePy with proper ImageMagick
configuration is required.
"""
        
        # Save as text file
        script_path = output_path.replace('.mp4', '_video_script.txt')
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_content)
        
        print(f"Video script generated: {script_path}")
        return True
        
    except Exception as e:
        print(f"Error generating video script: {e}")
        return False

def get_available_voices() -> list:
    """Get list of available TTS voices."""
    return ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

def get_available_models() -> list:
    """Get list of available TTS models."""
    return ["tts-1", "tts-1-hd"]

def get_available_formats() -> list:
    """Get list of available audio formats."""
    return ["mp3", "opus", "aac", "flac"]

def get_available_qualities() -> list:
    """Get list of available video qualities."""
    return ["480p", "720p", "1080p"]
