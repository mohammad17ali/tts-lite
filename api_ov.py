#!/usr/bin/env python3
"""
FastAPI server for Kokoro Text-to-Speech service — OpenVINO backend.
Mirrors api.py but replaces PyTorch inference with OpenVINO IR for
faster inference on AIPCs / Intel hardware.

Prerequisites:
    python convert_to_ov.py          # produces Kokoro-82M/openvino_model.xml
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn
import hashlib
import json
import os
import io
import gc
from dataclasses import dataclass
import torch
import numpy as np
import openvino as ov
import soundfile as sf
from datetime import datetime
from pathlib import Path
from kokoro import KPipeline


# ---------------------------------------------------------------------------
# OpenVINO model wrapper
# ---------------------------------------------------------------------------

class OVKokoroModel:
    """
    Drop-in replacement for the PyTorch Kokoro model inside KPipeline.
    Loads the OpenVINO IR produced by convert_to_ov.py and runs inference
    through the OpenVINO runtime.

    KPipeline calls: model(phonemes_str, ref_s, speed, return_output=True)
    which in the PyTorch KModel.forward() converts phonemes→input_ids via
    self.vocab, then delegates to forward_with_tokens(input_ids, ref_s, speed).
    The OV IR was exported from forward_with_tokens, so we replicate the
    phoneme→token conversion here and then run OV inference.
    """

    @dataclass
    class Output:
        audio: torch.FloatTensor
        pred_dur: object = None

    def __init__(self, model_dir: str = "Kokoro-82M", device: str = "CPU"):
        model_path = Path(model_dir) / "openvino_model.xml"
        config_path = Path(model_dir) / "config.json"
        if not model_path.exists():
            raise FileNotFoundError(
                f"OpenVINO model not found at {model_path}. "
                "Run `python convert_to_ov.py` first."
            )
        core = ov.Core()
        self.compiled_model = core.compile_model(str(model_path), device)
        self._audio_key = self.compiled_model.output(0)
        # pred_dur is the second output if it was exported
        self._has_pred_dur = len(self.compiled_model.outputs) > 1
        if self._has_pred_dur:
            self._pred_dur_key = self.compiled_model.output(1)

        # Load vocab from config.json (same mapping KModel uses)
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        self.vocab: dict = config["vocab"]
        self.context_length: int = config.get("plbert", {}).get("max_position_embeddings", 512)

        # Attribute that KPipeline may probe
        self.device = torch.device("cpu")

    def __call__(self, phonemes: str, ref_s, speed=1, return_output: bool = False):
        """
        Match KModel.forward() signature:
            model(phonemes, ref_s, speed, return_output=True)
        """
        # --- phonemes → input_ids (mirrors KModel.forward) ---
        input_ids = [i for i in (self.vocab.get(p) for p in phonemes) if i is not None]
        assert len(input_ids) + 2 <= self.context_length, (
            len(input_ids) + 2,
            self.context_length,
        )
        input_ids_np = np.array([[0] + input_ids + [0]], dtype=np.int64)

        # --- ref_s / speed to numpy ---
        if isinstance(ref_s, torch.Tensor):
            ref_s_np = ref_s.numpy()
        else:
            ref_s_np = np.asarray(ref_s)

        if isinstance(speed, torch.Tensor):
            speed_np = speed.numpy()
        elif isinstance(speed, (int, float)):
            speed_np = np.array([speed], dtype=np.float32)
        else:
            speed_np = np.asarray(speed, dtype=np.float32)

        # --- OV inference ---
        result = self.compiled_model({0: input_ids_np, 1: ref_s_np, 2: speed_np})
        audio = torch.from_numpy(result[self._audio_key]).squeeze().cpu()

        pred_dur = None
        if self._has_pred_dur:
            pred_dur = torch.from_numpy(result[self._pred_dur_key]).cpu()

        if return_output:
            return self.Output(audio=audio, pred_dur=pred_dur)
        return audio

    # no-ops expected by torch-style callers
    def eval(self):
        return self

    def to(self, *_args, **_kwargs):
        return self


# ---------------------------------------------------------------------------
# Request / Response models  (identical to api.py)
# ---------------------------------------------------------------------------

class TTSRequest(BaseModel):
    text: str
    voice: str = "af_heart"
    lang_code: str = "a"


class TTSResponse(BaseModel):
    status: str
    message: str
    output_file: str = None


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Kokoro TTS API (OpenVINO)",
    description="Text-to-Speech service using Kokoro-82M with OpenVINO backend",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8801"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Caches keyed by lang_code
pipeline_cache: dict[str, KPipeline] = {}
ov_model_cache: dict[str, OVKokoroModel] = {}

OV_MODEL_DIR = os.environ.get("OV_MODEL_DIR", "Kokoro-82M")
OV_DEVICE = os.environ.get("OV_DEVICE", "GPU")
print('-' * 60)
print(f"Using OpenVINO model from {OV_MODEL_DIR} on device {OV_DEVICE}")
print('-' * 60)

DB_PATH = Path("tts_db.json")


# ---------------------------------------------------------------------------
# DB helpers  (same as api.py)
# ---------------------------------------------------------------------------

def load_db() -> dict:
    if DB_PATH.exists():
        with open(DB_PATH, "r") as f:
            return json.load(f)
    return {"tasks": []}


def save_db(db: dict) -> None:
    with open(DB_PATH, "w") as f:
        json.dump(db, f, indent=2)


def add_task(text: str, voice: str, lang_code: str, file_name: str) -> dict:
    db = load_db()
    task_number = len(db["tasks"]) + 1
    task = {
        "task_number": task_number,
        "text": text,
        "voice": voice,
        "lang_code": lang_code,
        "file_name": file_name,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    db["tasks"].append(task)
    save_db(db)
    return task


def deterministic_filename(text: str, voice: str, lang_code: str) -> str:
    payload = f"{text}|{voice}|{lang_code}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"tts_{digest}.wav"


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------

def get_pipeline(lang_code: str = "a") -> KPipeline:
    """
    Return a KPipeline whose PyTorch model has been replaced by the
    OpenVINO compiled model.  Pipelines (and their OV models) are cached
    per lang_code.
    """
    if lang_code not in pipeline_cache:
        print(f"[OV] Initializing Kokoro pipeline (lang={lang_code}) …")
        pipe = KPipeline(lang_code=lang_code)

        # Swap the PyTorch model for the OV model
        ov_model = OVKokoroModel(model_dir=OV_MODEL_DIR, device=OV_DEVICE)
        # Free the original PyTorch model
        del pipe.model
        gc.collect()
        pipe.model = ov_model

        pipeline_cache[lang_code] = pipe
        ov_model_cache[lang_code] = ov_model
        print(f"[OV] Pipeline ready (device={OV_DEVICE})")

    return pipeline_cache[lang_code]


def generate_speech_bytes(text: str, voice: str = "af_heart", lang_code: str = "a") -> bytes:
    pipeline = get_pipeline(lang_code)

    print(f"[OV] Generating speech: {text[:50]}…")
    generator = pipeline(text, voice=voice)

    audio_chunks = []
    for i, (gs, ps, audio) in enumerate(generator):
        print(f"[OV] chunk {i}")
        audio_chunks.append(audio)

    if not audio_chunks:
        raise ValueError("No audio chunks generated")

    combined_audio = np.concatenate(audio_chunks)

    buffer = io.BytesIO()
    sf.write(buffer, combined_audio, 24000, format="WAV")
    buffer.seek(0)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Endpoints  (mirror api.py)
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "Kokoro TTS API (OpenVINO)"}


@app.post("/tts/generate-stream", response_class=StreamingResponse)
async def generate_tts_stream(
    text: str = Query(..., description="Text to convert to speech"),
    voice: str = Query("af_heart", description="Voice identifier"),
    lang_code: str = Query("a", description="Language code"),
):
    try:
        if not text or len(text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Text cannot be empty")

        audio_bytes = generate_speech_bytes(text, voice, lang_code)

        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type="audio/wav",
            headers={"Content-Disposition": "attachment; filename=output.wav"},
        )
    except Exception as e:
        print(f"[OV] Error generating speech: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tts/generate")
async def generate_tts_json(request: TTSRequest):
    try:
        if not request.text or len(request.text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Text cannot be empty")

        output_dir = Path("tts_outputs")
        output_dir.mkdir(exist_ok=True)

        filename = deterministic_filename(request.text, request.voice, request.lang_code)
        output_path = output_dir / filename

        pipeline = get_pipeline(request.lang_code)
        generator = pipeline(request.text, voice=request.voice)

        audio_chunks = []
        for i, (gs, ps, audio) in enumerate(generator):
            print(f"[OV] chunk {i}")
            audio_chunks.append(audio)

        if not audio_chunks:
            raise ValueError("No audio chunks generated")

        combined_audio = np.concatenate(audio_chunks)
        sf.write(str(output_path), combined_audio, 24000)

        task = add_task(request.text, request.voice, request.lang_code, filename)

        return {
            "status": "success",
            "message": "Speech generated successfully (OpenVINO)",
            "output_file": str(output_path),
            "file_name": filename,
            "task_number": task["task_number"],
        }
    except Exception as e:
        print(f"[OV] Error generating speech: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tts/tasks")
async def list_tasks():
    db = load_db()
    return {"tasks": db["tasks"]}


@app.get("/tts/files/{filename}")
async def get_tts_file(filename: str):
    if not filename.endswith(".wav") or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    file_path = Path("tts_outputs") / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path), media_type="audio/wav", filename=filename)


@app.get("/")
async def root():
    return {
        "message": "Kokoro TTS API (OpenVINO)",
        "version": "1.0.0",
        "backend": "OpenVINO",
        "device": OV_DEVICE,
        "endpoints": {
            "health": "/health",
            "generate_tts_stream": "/tts/generate-stream?text=...&voice=af_heart&lang_code=a",
            "generate_tts_json": "POST /tts/generate",
            "tasks": "/tts/tasks",
            "files": "/tts/files/{filename}",
        },
        "docs": "/docs",
    }


if __name__ == "__main__":
    uvicorn.run("api_ov:app", host="0.0.0.0", port=8800, reload=False, log_level="info")
