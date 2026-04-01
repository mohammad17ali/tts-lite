# tts-lite
Lightweight TTS pipeline using Kokoro-82M model.

## Usage

### CLI Script
Generate speech from the command line:

```bash
# With default text
python main.py

# With custom text
python main.py "Your text here"
```

### FastAPI Server
Start the API server:

```bash
python api.py
```

The server will run on `http://localhost:8800`

#### API Endpoints

**1. Health Check**
```
GET /health
```

**2. Generate TTS (Query Parameters)**
```
GET /tts/generate?text=Hello&voice=af_heart&lang_code=a
```
Returns: WAV file download

**3. Generate TTS (Streaming)**
```
GET /tts/generate-stream?text=Hello&voice=af_heart&lang_code=a
```
Returns: Streaming WAV audio

**4. Generate TTS (JSON Request)**
```
POST /tts/generate-json
Content-Type: application/json

{
  "text": "Your text here",
  "voice": "af_heart",
  "lang_code": "a"
}
```
Returns: JSON with file path

#### Example Requests

Using curl:
```bash
# Get audio file
curl "http://localhost:8800/tts/generate?text=Hello+world" -o output.wav

# Using JSON
curl -X POST http://localhost:8800/tts/generate \
  -H "Content-Type: application/json" \
  -d '{"text": "This is the Kokoro model being hosted on Intel AIPC. Welcome to new possibilities.", "voice": "af_heart", "lang_code": "a"}'
```
Hindi
```bash

curl -X POST http://localhost:8800/tts/generate \
  -H "Content-Type: application/json" \
  -d '{"text": "यह Kokoro एक छोटा सा TTS (Text-to-Speech) मॉडल है, जिसमें केवल 82 मिलियन पैरामीटर्स हैं। इसके बावजूद, यह बड़े मॉडलों के बराबर क्वालिटी देता है, और बहुत तेज़ी से तथा कम खर्च में काम करता है।", "voice": "hf_alpha", "lang_code": "h"}'
```

Using Python:
```python
import requests

# Query parameter endpoint
response = requests.get(
    "http://localhost:8800/tts/generate",
    params={
        "text": "Hello world",
        "voice": "af_heart",
        "lang_code": "a"
    }
)

with open("output.wav", "wb") as f:
    f.write(response.content)
```

#### Interactive API Documentation
- Swagger UI: `http://localhost:8800/docs`
- ReDoc: `http://localhost:8800/redoc`

## Installation

```bash
uv pip install -r requirements.txt
```

## Parameters

- **text**: Text to convert to speech (required)
- **voice**: Voice identifier (default: `af_heart`)
- **lang_code**: Language code (default: `a`) 

## Benchmarking

A benchmarking script is provided in the `benchmarks/` directory to measure TTS latency.

### How it works
1. **Warm-up**: A single request is sent first (not recorded) to ensure the model for the target language is downloaded and loaded.
2. **Recorded passes**: Each query is then sent **twice** (two passes), and latency is recorded for every request.
3. **Results**: Saved as a timestamped CSV file in `benchmarks/` (e.g. `benchmark_english_20260401_120000.csv`).

The CSV records: `pass`, `query_index`, `text`, `text_length`, `voice`, `lang_code`, `latency_s`, `status`, `output_file`, `file_name`.

### Supported languages
- `english` (default) — voice: `af_heart`, lang_code: `a`
- `hindi` — voice: `hf_alpha`, lang_code: `h`

Queries for each language are defined in `benchmarks/queries.py`.

### Usage

```bash
# Benchmark English (default)
python benchmarks/benchmark.py

# Benchmark Hindi
python benchmarks/benchmark.py --lang hindi

# Benchmark English (explicit)
python benchmarks/benchmark.py --lang english
```

You can override the backend URL with the `TTS_BASE_URL` environment variable (default: `http://localhost:8800`).
