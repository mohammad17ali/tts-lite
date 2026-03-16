#!/usr/bin/env python3

from kokoro import KPipeline
import soundfile as sf
import torch
import sys
import os
from pathlib import Path
import numpy as np


def generate_speech(text, output_file='output.wav', voice='af_heart', lang_code='a'):
    print(f"Initializing Kokoro TTS pipeline with language code: {lang_code}")
    pipeline = KPipeline(lang_code=lang_code)
    
    print(f"Generating speech for text: {text[:50]}...")
    generator = pipeline(text, voice=voice)
    
    # Concatenate all audio chunks
    audio_chunks = []
    for i, (gs, ps, audio) in enumerate(generator):
        print(f"Processing audio chunk {i}: gs={gs}, ps={ps}")
        audio_chunks.append(audio)
    
    # Combine all chunks
    if audio_chunks:
        combined_audio = np.concatenate(audio_chunks)
    else:
        raise ValueError("No audio chunks generated")
    
    # Ensure output directory exists
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to file
    print(f"Writing audio to: {output_file}")
    sf.write(output_file, combined_audio, 24000)
    
    print(f"✓ Successfully generated: {output_file}")
    return output_file


def main():
    """Main entry point for the script."""
    # Example usage with default text
    print("Starting TTS generation...")

    text = '''
[Kokoro](/kˈOkəɹO/) is an open-weight TTS model with 82 million parameters. Despite its lightweight architecture, it delivers comparable quality to larger models while being significantly faster and more cost-efficient.
'''

    
    text_h = 'यह [Kokoro](/kˈOkəɹO/) एक छोटा सा TTS मॉडल है, जिसमें सिर्फ 82 मिलियन पैरामीटर्स हैं। इसके बावजूद, यह बड़े मॉडलों के बराबर क्वालिटी देता है और बहुत तेज़ी से तथा कम खर्च में काम करता है।'
    # Allow text from command line argument
    if len(sys.argv) > 1:
        text = ' '.join(sys.argv[1:])
    
    output_file = 'output_h2.wav'
    voice = 'af_heart'
    
    try:
        result = generate_speech(text_h, output_file, voice, lang_code='h')
        print(f"\nOutput file ready: {result}")
    except Exception as e:
        print(f"Error generating speech: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()