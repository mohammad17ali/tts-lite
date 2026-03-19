#!/usr/bin/env python3
"""
FastAPI server for Kokoro Text-to-Speech service.
Exposes endpoints to generate speech from text and return .wav files.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn
import tempfile
import os
from pathlib import Path
import numpy as np
from kokoro import KPipeline
import soundfile as sf
import io


# Request/Response Models
class TTSRequest(BaseModel):
    """Request model for TTS generation"""
    text: str
    voice: str = "af_heart"
    lang_code: str = "a"


class TTSResponse(BaseModel):
    """Response model for TTS request status"""
    status: str
    message: str
    output_file: str = None


# Initialize FastAPI app
app = FastAPI(
    title="Kokoro TTS API",
    description="Text-to-Speech service using Kokoro-82M model",
    version="1.0.0"
)

# Global pipeline (cached)
pipeline_cache = {}


def get_pipeline(lang_code='a'):
    """Get or create a cached pipeline for the given language code"""
    if lang_code not in pipeline_cache:
        print(f"Initializing Kokoro TTS pipeline with language code: {lang_code}")
        pipeline_cache[lang_code] = KPipeline(lang_code=lang_code)
    return pipeline_cache[lang_code]


def generate_speech_bytes(text: str, voice: str = 'af_heart', lang_code: str = 'a') -> bytes:
    """
    Generate speech from text and return as bytes.
    
    Args:
        text: Text to convert to speech
        voice: Voice identifier
        lang_code: Language code
    
    Returns:
        Audio data as bytes
    """
    pipeline = get_pipeline(lang_code)
    
    print(f"Generating speech: {text[:50]}...")
    generator = pipeline(text, voice=voice)
    
    # Concatenate all audio chunks
    audio_chunks = []
    for i, (gs, ps, audio) in enumerate(generator):
        print(f"Processing audio chunk {i}")
        audio_chunks.append(audio)
    
    if not audio_chunks:
        raise ValueError("No audio chunks generated")
    
    combined_audio = np.concatenate(audio_chunks)
    
    # Write to bytes buffer
    buffer = io.BytesIO()
    sf.write(buffer, combined_audio, 24000, format='WAV')
    buffer.seek(0)
    
    return buffer.getvalue()


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Kokoro TTS API"
    }


@app.post("/tts/generate", response_class=FileResponse)
async def generate_tts(
    text: str = Query(..., description="Text to convert to speech"),
    voice: str = Query("af_heart", description="Voice identifier"),
    lang_code: str = Query("a", description="Language code")
):
    """
    Generate speech from text and return .wav file.
    
    Query Parameters:
    - text: Text to convert to speech (required)
    - voice: Voice identifier (default: af_heart)
    - lang_code: Language code (default: a)
    
    Returns:
        WAV audio file
    """
    try:
        if not text or len(text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Text cannot be empty")
        
        # Generate audio bytes
        audio_bytes = generate_speech_bytes(text, voice, lang_code)
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        
        return FileResponse(
            tmp_path,
            media_type="audio/wav",
            filename="output.wav",
            headers={"Content-Disposition": "attachment; filename=output.wav"}
        )
    
    except Exception as e:
        print(f"Error generating speech: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tts/generate-stream", response_class=StreamingResponse)
async def generate_tts_stream(
    text: str = Query(..., description="Text to convert to speech"),
    voice: str = Query("af_heart", description="Voice identifier"),
    lang_code: str = Query("a", description="Language code")
):
    """
    Generate speech from text and stream .wav file.
    
    Query Parameters:
    - text: Text to convert to speech (required)
    - voice: Voice identifier (default: af_heart)
    - lang_code: Language code (default: a)
    
    Returns:
        Streaming WAV audio
    """
    try:
        if not text or len(text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Text cannot be empty")
        
        # Generate audio bytes
        audio_bytes = generate_speech_bytes(text, voice, lang_code)
        
        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type="audio/wav",
            headers={"Content-Disposition": "attachment; filename=output.wav"}
        )
    
    except Exception as e:
        print(f"Error generating speech: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tts/generate")
async def generate_tts_json(request: TTSRequest):
    """
    Generate speech from JSON request body and save to file.
    
    Request body:
    {
        "text": "Your text here",
        "voice": "af_heart",
        "lang_code": "a"
    }
    
    Returns:
        JSON response with file path
    """
    try:
        if not request.text or len(request.text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Text cannot be empty")
        
        # Create output directory
        output_dir = Path("tts_outputs")
        output_dir.mkdir(exist_ok=True)
        
        # Generate unique filename
        import uuid
        filename = f"tts_{uuid.uuid4()}.wav"
        output_path = output_dir / filename
        
        # Generate audio
        pipeline = get_pipeline(request.lang_code)
        generator = pipeline(request.text, voice=request.voice)
        
        audio_chunks = []
        for i, (gs, ps, audio) in enumerate(generator):
            print(f"Processing audio chunk {i}")
            audio_chunks.append(audio)
        
        if not audio_chunks:
            raise ValueError("No audio chunks generated")
        
        combined_audio = np.concatenate(audio_chunks)
        sf.write(str(output_path), combined_audio, 24000)
        
        return {
            "status": "success",
            "message": "Speech generated successfully",
            "output_file": str(output_path),
            "file_name": filename
        }
    
    except Exception as e:
        print(f"Error generating speech: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """API documentation"""
    return {
        "message": "Kokoro TTS API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "generate_tts": "/tts/generate?text=...&voice=af_heart&lang_code=a",
            "generate_tts_stream": "/tts/generate-stream?text=...&voice=af_heart&lang_code=a",
            "generate_tts_json": "POST /tts/generate-json"
        },
        "docs": "/docs",
        "redoc": "/redoc"
    }


if __name__ == '__main__':
    # Run the server
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8800,
        reload=False,
        log_level="info"
    )
