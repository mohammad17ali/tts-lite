"""
TTS-Lite Benchmarking Script

Sends requests to the TTS backend and records latency per query.
- Performs a single warm-up request (not recorded) to ensure the model
  for the target language is downloaded and loaded.
- Then performs two recorded passes for each query.
- Saves results to a CSV file inside the benchmarks/ directory.

Usage:
    python benchmark.py                  # default: english
    python benchmark.py --lang english
    python benchmark.py --lang hindi
"""

import argparse
import csv
import os
import time
from datetime import datetime

import requests

from queries import ENGLISH_QUERIES, HINDI_QUERIES

# --- Configuration ---
BASE_URL = os.environ.get("TTS_BASE_URL", "http://localhost:8800")
ENDPOINT = f"{BASE_URL}/tts/generate"

LANG_CONFIG = {
    "english": {
        "queries": ENGLISH_QUERIES,
        "voice": "af_heart",
        "lang_code": "a",
    },
    "hindi": {
        "queries": HINDI_QUERIES,
        "voice": "hf_alpha",
        "lang_code": "h",
    },
}

BENCHMARK_DIR = os.path.dirname(os.path.abspath(__file__))
NUM_RECORDED_PASSES = 2


def send_tts_request(text: str, voice: str, lang_code: str) -> dict:
    """Send a TTS generate request and return the response JSON and latency."""
    payload = {
        "text": text,
        "voice": voice,
        "lang_code": lang_code,
    }
    start = time.perf_counter()
    resp = requests.post(ENDPOINT, json=payload, timeout=300)
    elapsed = time.perf_counter() - start
    resp.raise_for_status()
    return resp.json(), elapsed


def run_benchmark(lang: str):
    cfg = LANG_CONFIG[lang]
    queries = cfg["queries"]
    voice = cfg["voice"]
    lang_code = cfg["lang_code"]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(BENCHMARK_DIR, f"benchmark_{lang}_{timestamp}.csv")

    # --- Health check ---
    print(f"Checking backend health at {BASE_URL}/health ...")
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=10)
        r.raise_for_status()
        print(f"Backend healthy: {r.json()}")
    except Exception as e:
        print(f"ERROR: Backend not reachable at {BASE_URL} — {e}")
        return

    # --- Warm-up (single request, not recorded) ---
    warmup_query = queries[0]
    print(f"\n=== Warm-up request (not recorded) ===")
    print(f"  Sending: {warmup_query[:60]}...")
    try:
        _, warmup_time = send_tts_request(warmup_query, voice, lang_code)
        print(f"  Done in {warmup_time:.3f}s")
    except Exception as e:
        print(f"  FAILED: {e}")
        print("  Continuing with benchmark anyway...")

    # --- Recorded passes ---
    # Collect per-query results across passes
    query_results = {}  # query_index -> {row data + pass latencies}
    for pass_num in range(1, NUM_RECORDED_PASSES + 1):
        print(f"\n=== Recorded pass {pass_num}/{NUM_RECORDED_PASSES} ({lang}) ===")
        for i, query in enumerate(queries, 1):
            print(f"  [{i}/{len(queries)}] {query[:60]}...")
            try:
                data, latency = send_tts_request(query, voice, lang_code)
                output_file = data.get("output_file", "")
                file_name = data.get("file_name", "")
                status = data.get("status", "")
                print(f"    {latency:.3f}s — {file_name}")

                if i not in query_results:
                    query_results[i] = {
                        "query_index": i,
                        "text": query,
                        "text_length": len(query),
                        "voice": voice,
                        "lang_code": lang_code,
                        "output_file": output_file,
                        "file_name": file_name,
                    }
                query_results[i][f"pass{pass_num}_latency_s"] = round(latency, 6)
            except Exception as e:
                print(f"    FAILED: {e}")
                if i not in query_results:
                    query_results[i] = {
                        "query_index": i,
                        "text": query,
                        "text_length": len(query),
                        "voice": voice,
                        "lang_code": lang_code,
                        "output_file": "",
                        "file_name": "",
                    }
                query_results[i][f"pass{pass_num}_latency_s"] = -1

    # Compute average and build final rows
    rows = []
    for i in sorted(query_results):
        row = query_results[i]
        pass_latencies = [
            row.get(f"pass{p}_latency_s", -1)
            for p in range(1, NUM_RECORDED_PASSES + 1)
        ]
        valid = [l for l in pass_latencies if l > 0]
        row["avg_latency_s"] = round(sum(valid) / len(valid), 6) if valid else -1
        rows.append(row)

    # --- Write CSV ---
    pass_cols = [f"pass{p}_latency_s" for p in range(1, NUM_RECORDED_PASSES + 1)]
    fieldnames = [
        "query_index", "text", "text_length",
        "voice", "lang_code",
    ] + pass_cols + [
        "avg_latency_s", "output_file", "file_name",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nBenchmark results saved to: {csv_path}")
    print(f"Total queries benchmarked: {len(rows)}")

    # --- Summary ---
    valid_avgs = [r["avg_latency_s"] for r in rows if r["avg_latency_s"] > 0]
    if valid_avgs:
        print(f"  Min avg latency:  {min(valid_avgs):.3f}s")
        print(f"  Max avg latency:  {max(valid_avgs):.3f}s")
        print(f"  Mean avg latency: {sum(valid_avgs) / len(valid_avgs):.3f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TTS-Lite Benchmarking")
    parser.add_argument(
        "--lang",
        choices=list(LANG_CONFIG.keys()),
        default="english",
        help="Language to benchmark (default: english)",
    )
    args = parser.parse_args()
    run_benchmark(args.lang)
