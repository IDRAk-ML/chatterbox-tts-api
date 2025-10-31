"""
TRUE model-level streaming service for Chatterbox TTS.

This module provides an async wrapper around the streaming model's generate_stream() method,
enabling real incremental token generation with KV-cache for low-latency streaming.

Key differences from fake streaming:
- Uses model.generate_stream() instead of chunking text
- Generates speech tokens incrementally with KV-cache
- Yields audio as tokens are generated (not after full generation)
- Much lower latency to first audio chunk (~0.5s vs full generation time)
"""

import asyncio
import time
import base64
import struct
import io
from typing import AsyncGenerator, Dict, Any, Optional, Tuple
import torch
import torchaudio as ta
import numpy as np

from app.core.tts_model import get_streaming_model, is_streaming_ready
from app.models import TrueStreamingRequest


def create_wav_header(sample_rate: int, channels: int, bits_per_sample: int, data_size: int = 0xFFFFFFFF) -> bytes:
    """Creates a WAV header for streaming."""
    header = io.BytesIO()
    header.write(b'RIFF')
    chunk_size = 36 + data_size if data_size != 0xFFFFFFFF else 0x7FFFFFFF - 36
    header.write(struct.pack('<I', chunk_size))
    header.write(b'WAVE')
    header.write(b'fmt ')
    header.write(struct.pack('<I', 16))  # Subchunk1Size for PCM
    header.write(struct.pack('<H', 1))   # AudioFormat (1 for PCM)
    header.write(struct.pack('<H', channels))
    header.write(struct.pack('<I', sample_rate))
    byte_rate = sample_rate * channels * (bits_per_sample // 8)
    header.write(struct.pack('<I', byte_rate))
    block_align = channels * (bits_per_sample // 8)
    header.write(struct.pack('<H', block_align))
    header.write(struct.pack('<H', bits_per_sample))
    header.write(b'data')
    header.write(struct.pack('<I', data_size))
    return header.getvalue()


async def generate_true_streaming_audio(
    request: TrueStreamingRequest,
    voice_sample_path: str,
    connection_id: Optional[str] = None
) -> AsyncGenerator[Tuple[bytes, Optional[Dict[str, Any]]], None]:
    """
    Generate audio using TRUE model-level streaming.

    This function wraps the synchronous model.generate_stream() in an async context,
    allowing it to be used with async/await and WebSocket connections.

    Args:
        request: TrueStreamingRequest with all streaming parameters
        voice_sample_path: Path to the voice sample audio file
        connection_id: Optional connection ID for logging

    Yields:
        Tuple of (audio_bytes, metrics_dict)
        - audio_bytes: Raw PCM audio data or base64-encoded depending on request.output_format
        - metrics_dict: Optional dict with generation metrics (if request.include_metrics=True)

    Raises:
        RuntimeError: If streaming model is not ready
        Exception: Any errors during generation
    """

    # Validate streaming model is ready
    if not is_streaming_ready():
        raise RuntimeError("Streaming model is not initialized. Please wait for model to load or check initialization errors.")

    model = get_streaming_model()

    # Track timing metrics
    start_time = time.time()
    first_chunk_time = None
    chunk_count = 0
    total_tokens = 0

    try:
        print(f"[{connection_id or 'stream'}] Starting TRUE streaming generation")
        print(f"[{connection_id or 'stream'}] Text: {request.input[:100]}...")
        print(f"[{connection_id or 'stream'}] Parameters: chunk_size={request.chunk_size}, context_window={request.context_window}, temperature={request.temperature}")

        # Run the synchronous generator in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()

        # Create the generator function to run in executor
        def run_streaming_generator():
            """Run the synchronous streaming generator"""
            try:
                # Call the streaming model's generate_stream method
                # Note: generate_stream has a simpler signature than generate()
                # Only these parameters are supported:
                #   text, audio_prompt_path, exaggeration, cfg_weight, temperature,
                #   chunk_size, context_window, fade_duration, print_metrics
                generator = model.generate_stream(
                    text=request.input,
                    audio_prompt_path=voice_sample_path,
                    exaggeration=request.exaggeration,
                    cfg_weight=request.cfg_weight,
                    temperature=request.temperature,
                    chunk_size=request.chunk_size,
                    context_window=request.context_window,
                    fade_duration=request.fade_in_duration_ms / 1000.0,  # Convert ms to seconds
                    print_metrics=request.print_metrics,
                )

                # Collect all chunks from the generator
                chunks = []
                for audio_chunk, metrics in generator:
                    chunks.append((audio_chunk, metrics))

                return chunks

            except Exception as e:
                print(f"[{connection_id or 'stream'}] Error in streaming generator: {e}")
                raise

        # Run the generator in a thread pool
        chunks = await loop.run_in_executor(None, run_streaming_generator)

        # Process and yield each chunk
        for audio_chunk, metrics in chunks:
            chunk_count += 1

            if first_chunk_time is None:
                first_chunk_time = time.time()
                latency_to_first = first_chunk_time - start_time
                print(f"[{connection_id or 'stream'}] ⚡ First chunk latency: {latency_to_first:.3f}s")

            # Convert tensor to PCM bytes
            audio_tensor = torch.clamp(audio_chunk, -1.0, 1.0)
            audio_int = (audio_tensor * 32767).to(torch.int16)
            pcm_data = audio_int.cpu().numpy().tobytes()

            # Apply fade-in if enabled
            if request.enable_fade_in and chunk_count > 1:
                # Calculate fade-in samples
                sample_rate = model.sr
                fade_samples = int(request.fade_in_duration_ms * sample_rate / 1000)

                if len(pcm_data) >= fade_samples * 2:  # 2 bytes per sample
                    # Convert to numpy array for fade processing
                    audio_array = np.frombuffer(pcm_data, dtype=np.int16).copy()
                    fade_curve = np.linspace(0.0, 1.0, fade_samples)
                    audio_array[:fade_samples] = (audio_array[:fade_samples] * fade_curve).astype(np.int16)
                    pcm_data = audio_array.tobytes()

            # Encode based on output format
            if request.output_format == "base64":
                output_data = base64.b64encode(pcm_data)
            else:
                output_data = pcm_data

            # Build metrics if requested
            metrics_dict = None
            if request.include_metrics:
                current_time = time.time()
                elapsed_time = current_time - start_time

                # Calculate audio duration
                sample_rate = model.sr
                audio_duration = len(audio_chunk[0]) / sample_rate

                # Calculate RTF (Real-Time Factor)
                rtf = elapsed_time / audio_duration if audio_duration > 0 else 0

                metrics_dict = {
                    "chunk": chunk_count,
                    "latency_to_first_chunk": latency_to_first - start_time if first_chunk_time else None,
                    "elapsed_time": elapsed_time,
                    "audio_duration": audio_duration,
                    "rtf": rtf,
                    "chunk_size_bytes": len(output_data),
                    "sample_rate": sample_rate,
                }

                # Add model metrics if available
                if metrics:
                    # Convert StreamingMetrics object to dict
                    if hasattr(metrics, '__dict__'):
                        metrics_dict.update(vars(metrics))
                    elif isinstance(metrics, dict):
                        metrics_dict.update(metrics)

            # Yield the chunk
            yield output_data, metrics_dict

            # Cleanup tensors
            del audio_chunk, audio_tensor, audio_int
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        # Final metrics
        end_time = time.time()
        total_time = end_time - start_time

        if request.print_metrics:
            print(f"[{connection_id or 'stream'}] ✓ Streaming complete!")
            print(f"[{connection_id or 'stream'}] Total chunks: {chunk_count}")
            print(f"[{connection_id or 'stream'}] Total time: {total_time:.3f}s")
            print(f"[{connection_id or 'stream'}] Avg time per chunk: {total_time/chunk_count if chunk_count > 0 else 0:.3f}s")

    except Exception as e:
        print(f"[{connection_id or 'stream'}] ✗ Error during streaming: {e}")
        raise


async def generate_true_streaming_wav(
    request: TrueStreamingRequest,
    voice_sample_path: str,
    connection_id: Optional[str] = None
) -> AsyncGenerator[bytes, None]:
    """
    Generate complete WAV stream (header + audio chunks).

    This is a convenience wrapper around generate_true_streaming_audio that
    yields a WAV header first, then audio chunks.

    Args:
        request: TrueStreamingRequest with all streaming parameters
        voice_sample_path: Path to the voice sample audio file
        connection_id: Optional connection ID for logging

    Yields:
        bytes: WAV header first, then PCM audio chunks
    """

    # Get the streaming model to determine sample rate
    model = get_streaming_model()

    # Yield WAV header first
    wav_header = create_wav_header(
        sample_rate=model.sr,
        channels=1,
        bits_per_sample=16
    )
    yield wav_header

    # Yield audio chunks
    async for audio_chunk, metrics in generate_true_streaming_audio(
        request=request,
        voice_sample_path=voice_sample_path,
        connection_id=connection_id
    ):
        yield audio_chunk
