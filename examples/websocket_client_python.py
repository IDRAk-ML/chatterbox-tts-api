#!/usr/bin/env python3
"""
Python WebSocket client for TRUE model-level streaming TTS.

This example demonstrates how to connect to the Chatterbox TTS WebSocket API
and receive TRUE model-level streaming audio in real-time.

Requirements:
    pip install websockets asyncio

Usage:
    python websocket_client_python.py

Features:
    - TRUE model-level streaming (not text chunking)
    - Real-time audio reception with <0.5s latency
    - Saves received audio to WAV file
    - Displays streaming metrics
"""

import asyncio
import json
import sys
import struct
from pathlib import Path
import websockets


class ChatterboxStreamingClient:
    """Client for Chatterbox TRUE streaming WebSocket API"""

    def __init__(self, base_url: str = "ws://localhost:4123"):
        """
        Initialize the streaming client.

        Args:
            base_url: Base WebSocket URL (default: ws://localhost:4123)
        """
        self.base_url = base_url
        self.ws_url = f"{base_url}/ws/stream/audio"
        self.websocket = None

    async def connect(self):
        """Connect to the WebSocket server"""
        print(f"Connecting to {self.ws_url}...")
        self.websocket = await websockets.connect(self.ws_url)

        # Wait for connection confirmation
        message = await self.websocket.recv()
        data = json.loads(message)

        if data.get("type") == "connected":
            connection_id = data.get("connection_id")
            print(f"✓ Connected! Connection ID: {connection_id}")
            return True
        else:
            print(f"✗ Unexpected connection message: {data}")
            return False

    async def disconnect(self):
        """Disconnect from the WebSocket server"""
        if self.websocket:
            await self.websocket.close()
            print("✓ Disconnected")

    async def stream_speech(
        self,
        text: str,
        output_file: str = "output_stream.wav",
        voice: str = "alloy",
        chunk_size: int = 25,
        temperature: float = 0.8,
        cfg_weight: float = 0.5,
        exaggeration: float = 0.5,
        include_metrics: bool = True,
        print_metrics: bool = True
    ):
        """
        Stream speech synthesis for the given text.

        Args:
            text: Text to synthesize
            output_file: Path to save the output WAV file
            voice: Voice name or alias from voice library
            chunk_size: Speech tokens per audio chunk (lower = faster, higher = smoother)
            temperature: Sampling temperature (0.05-5.0)
            cfg_weight: Classifier-free guidance weight (0.0-1.0)
            exaggeration: Emotion intensity (0.25-2.0)
            include_metrics: Include generation metrics in responses
            print_metrics: Print metrics to console during generation
        """

        if not self.websocket:
            raise RuntimeError("Not connected. Call connect() first.")

        # Prepare streaming request
        request = {
            "type": "stream_request",
            "data": {
                "input": text,
                "voice": voice,
                "chunk_size": chunk_size,
                "temperature": temperature,
                "cfg_weight": cfg_weight,
                "exaggeration": exaggeration,
                "output_format": "wav",
                "include_metrics": include_metrics,
                "print_metrics": print_metrics,
                "enable_fade_in": True,
                "fade_in_duration_ms": 20,
                "context_window": 50,
                "max_new_tokens": 4096,
                "enable_alignment_monitoring": True
            }
        }

        # Send request
        print(f"\n📝 Sending request:")
        print(f"   Text: {text[:100]}{'...' if len(text) > 100 else ''}")
        print(f"   Voice: {voice}")
        print(f"   Chunk size: {chunk_size} tokens")
        print(f"   Temperature: {temperature}")
        print()

        await self.websocket.send(json.dumps(request))

        # Receive response
        audio_data = bytearray()
        chunk_count = 0
        metrics_history = []

        print("🎧 Receiving audio stream...")

        try:
            while True:
                message = await self.websocket.recv()

                # Check if it's binary (audio data) or text (JSON message)
                if isinstance(message, bytes):
                    # Binary audio data
                    audio_data.extend(message)
                    chunk_count += 1

                    # Show progress indicator
                    if chunk_count == 1:
                        print("   ⚡ First audio chunk received!")
                    else:
                        print(f"   📦 Chunk #{chunk_count} received ({len(message)} bytes)", end='\r')

                else:
                    # Text message (JSON)
                    data = json.loads(message)
                    msg_type = data.get("type")

                    if msg_type == "info":
                        print(f"   ℹ️  {data.get('message')}")

                    elif msg_type == "metrics":
                        metrics = data.get("data", {})
                        metrics_history.append(metrics)

                        if include_metrics:
                            chunk_num = metrics.get("chunk", "?")
                            latency = metrics.get("latency_to_first_chunk")
                            rtf = metrics.get("rtf", 0)

                            if latency and chunk_num == 1:
                                print(f"   ⚡ Latency to first chunk: {latency:.3f}s")

                            print(f"   📊 Chunk {chunk_num}: RTF={rtf:.3f}", end='\r')

                    elif msg_type == "done":
                        total_chunks = data.get("total_chunks", chunk_count)
                        print(f"\n   ✓ Streaming complete! Total chunks: {total_chunks}")
                        break

                    elif msg_type == "error":
                        error = data.get("error")
                        print(f"\n   ✗ Error: {error}")
                        return False

        except Exception as e:
            print(f"\n✗ Error receiving stream: {e}")
            return False

        # Save audio to file
        if audio_data:
            output_path = Path(output_file)
            output_path.write_bytes(audio_data)

            audio_size_kb = len(audio_data) / 1024
            print(f"\n💾 Audio saved to: {output_file}")
            print(f"   Size: {audio_size_kb:.1f} KB")
            print(f"   Chunks: {chunk_count}")

            # Display metrics summary
            if metrics_history:
                first_metrics = metrics_history[0]
                last_metrics = metrics_history[-1]

                latency = first_metrics.get("latency_to_first_chunk", 0)
                total_time = last_metrics.get("elapsed_time", 0)
                audio_duration = last_metrics.get("audio_duration", 0)
                avg_rtf = sum(m.get("rtf", 0) for m in metrics_history) / len(metrics_history)

                print(f"\n📊 Metrics Summary:")
                print(f"   Latency to first chunk: {latency:.3f}s")
                print(f"   Total generation time: {total_time:.3f}s")
                print(f"   Audio duration: {audio_duration:.3f}s")
                print(f"   Average RTF: {avg_rtf:.3f} {'✓ (faster than real-time!)' if avg_rtf < 1.0 else ''}")
                print(f"   Chunks received: {len(metrics_history)}")

            return True

        return False


async def main():
    """Main example function"""

    # Example texts to try
    examples = [
        "Hello! This is a test of TRUE model-level streaming with Chatterbox TTS.",
        "The quick brown fox jumps over the lazy dog. This is an example of real-time speech synthesis.",
        "Welcome to the future of text-to-speech! With true streaming, you can hear audio as it's being generated, with incredibly low latency."
    ]

    # Create client
    client = ChatterboxStreamingClient(base_url="ws://localhost:4123")

    try:
        # Connect
        await client.connect()

        # Stream speech for the first example
        text = examples[0]

        success = await client.stream_speech(
            text=text,
            output_file="output_stream.wav",
            voice="alloy",
            chunk_size=25,  # Speech tokens per chunk (lower = faster response)
            temperature=0.8,
            cfg_weight=0.5,
            exaggeration=0.5,
            include_metrics=True,
            print_metrics=True
        )

        if success:
            print("\n✓ Example completed successfully!")
            print("\n💡 Try different texts:")
            for i, example_text in enumerate(examples[1:], 1):
                print(f"   {i}. {example_text[:60]}...")
        else:
            print("\n✗ Example failed")

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Disconnect
        await client.disconnect()


if __name__ == "__main__":
    print("=" * 70)
    print("Chatterbox TTS - TRUE Streaming WebSocket Client (Python)")
    print("=" * 70)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nGoodbye!")
