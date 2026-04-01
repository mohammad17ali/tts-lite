# TTS-Lite on Windows (OpenVINO — CPU / GPU / NPU)

## Prerequisites

- Windows 11 (22H2+)
- Python 3.11 or 3.12 — download from https://www.python.org/downloads/
- Git — https://git-scm.com/download/win
- Latest **Intel GPU driver** — https://www.intel.com/content/www/us/en/download/785597/intel-arc-iris-xe-graphics-windows.html
- Latest **Intel NPU driver** (Core Ultra only) — https://www.intel.com/content/www/us/en/download/794734/intel-npu-driver-windows.html

## 1. Clone / Copy the Repo

```powershell
# If cloning from git:
git clone <your-repo-url> tts-lite
cd tts-lite

# Or copy from WSL:
# From Windows Explorer, navigate to \\wsl$\Ubuntu\home\alimohammad\tts-lite
# and copy the folder to a Windows-native path, e.g. C:\Projects\tts-lite
```

## 2. Create a Virtual Environment & Install Dependencies

```powershell
python -m venv .venv
.venv\Scripts\activate

pip install --upgrade pip
pip install -r requirements.txt
# requests is needed for benchmarking
pip install requests
```

## 3. Verify Available Devices

```powershell
python -c "import openvino as ov; core = ov.Core(); print('Devices:', core.get_available_devices())"
```

Expected output on a Core Ultra AIPC:
```
Devices: ['CPU', 'GPU.0', 'GPU.1', 'NPU']
```

- `GPU.0` = Intel iGPU (Iris Xe / Arc)
- `GPU.1` = dGPU if present
- `NPU` = Intel NPU (Core Ultra)

> If `GPU` doesn't appear, update the Intel GPU driver.
> If `NPU` doesn't appear, update the Intel NPU driver.

## 4. Convert Model to OpenVINO IR (One-Time)

```powershell
python convert_to_ov.py
```

This creates `Kokoro-82M/openvino_model.xml` + `.bin`. Only needs to run once.

## 5. Start the API Server

### CPU (baseline)

```powershell
python api_ov.py
```

### GPU (iGPU accelerated)

```powershell
set OV_DEVICE=GPU
python api_ov.py
```

### AUTO (let OpenVINO pick the best device)

```powershell
set OV_DEVICE=AUTO
python api_ov.py
```

### AUTO with explicit priority

```powershell
set OV_DEVICE=AUTO:GPU,CPU
python api_ov.py
```

> **NPU note:** The current model uses dynamic input shapes (`[1, 2..]`).
> NPU only supports static shapes, so `NPU` alone will fail.
> `AUTO` will skip NPU and fall back to GPU/CPU automatically.

The server runs at **http://localhost:8800**. Verify with:

```powershell
curl http://localhost:8800/health
```

## 6. Test a Request

```powershell
curl -X POST http://localhost:8800/tts/generate ^
  -H "Content-Type: application/json" ^
  -d "{\"text\": \"Hello, this is a test of text to speech.\", \"voice\": \"af_heart\", \"lang_code\": \"a\"}"
```

## 7. Run Benchmarks

With the server running in another terminal:

```powershell
cd benchmarks

# English
python benchmark.py --lang english

# Hindi
python benchmark.py --lang hindi
```

Results are saved as CSV files in the `benchmarks/` directory.

### Benchmark Across Devices

To compare CPU vs GPU, run the benchmark for each device setting:

```powershell
# Terminal 1 — start server with CPU
set OV_DEVICE=CPU
python api_ov.py

# Terminal 2 — benchmark
cd benchmarks
python benchmark.py --lang english
# note the CSV filename, then stop the server (Ctrl+C)

# Terminal 1 — restart with GPU
set OV_DEVICE=GPU
python api_ov.py

# Terminal 2 — benchmark again
python benchmark.py --lang english
```

## 8. PyTorch Baseline (for comparison)

To benchmark the original PyTorch inference (no OpenVINO):

```powershell
python api.py
```

Then run the benchmarks against it (same port 8800).

## Environment Variables

| Variable       | Default      | Description                                          |
|----------------|--------------|------------------------------------------------------|
| `OV_DEVICE`    | `CPU`        | OpenVINO device: `CPU`, `GPU`, `AUTO`, `AUTO:GPU,CPU`|
| `OV_MODEL_DIR` | `Kokoro-82M` | Path to the converted OpenVINO IR directory          |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `GPU` not in available devices | Update Intel GPU driver to latest version |
| `NPU` not in available devices | Update Intel NPU driver; requires Core Ultra CPU |
| `libOpenCL.so.1` error | You're in WSL2 — run natively on Windows instead |
| NPU inference fails | Model uses dynamic shapes; NPU needs static shapes. Use `AUTO` or `GPU` |
| Slow first request | Expected — model compiles on first call. Subsequent requests are fast. Use `ov::cache_dir` for persistent caching (set `OV_CACHE_DIR` env var if implemented) |
