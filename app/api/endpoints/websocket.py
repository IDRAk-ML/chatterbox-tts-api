"""
WebSocket endpoints for TRUE model-level streaming.

This module provides WebSocket-based streaming endpoints that enable real-time
bidirectional communication for TTS generation with true model-level streaming.
"""

import uuid
import json
import traceback
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse

from app.models import TrueStreamingRequest, WebSocketStreamingMessage
from app.core.websocket_manager import get_connection_manager
from app.core.true_streaming import generate_true_streaming_audio, create_wav_header
from app.core.tts_model import is_streaming_ready, get_streaming_model, get_streaming_initialization_error
from app.api.endpoints.speech import resolve_voice_path_and_language

router = APIRouter()


@router.get(
    "/ws/stream/status",
    summary="Check TRUE streaming availability",
    description="Check if TRUE model-level streaming is available and ready",
    responses={
        200: {"description": "Streaming status information"},
        503: {"description": "Streaming not available"}
    }
)
async def get_streaming_status():
    """Get the status of the streaming model"""

    if not is_streaming_ready():
        error = get_streaming_initialization_error()
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "available": False,
                "ready": False,
                "error": error or "Streaming model not initialized"
            }
        )

    model = get_streaming_model()

    return {
        "available": True,
        "ready": True,
        "sample_rate": model.sr if hasattr(model, 'sr') else 24000,
        "supported_formats": ["wav", "base64"],
        "description": "TRUE model-level streaming with KV-cache",
        "features": {
            "incremental_generation": True,
            "kv_cache": True,
            "alignment_monitoring": True,
            "low_latency": True,
            "real_time_factor": "< 1.0 (faster than real-time)"
        }
    }


@router.websocket("/ws/stream/audio")
async def websocket_stream_audio(websocket: WebSocket):
    """
    WebSocket endpoint for TRUE model-level streaming.

    Protocol:
    1. Client connects to WebSocket
    2. Server sends connection confirmation
    3. Client sends JSON message with type="stream_request" and TrueStreamingRequest data
    4. Server sends WAV header (binary)
    5. Server streams audio chunks (binary)
    6. Server sends final metrics message (JSON)
    7. Connection remains open for next request or closes

    Message Format (Client -> Server):
    {
        "type": "stream_request",
        "data": {
            "input": "Text to synthesize",
            "voice": "alloy",
            "chunk_size": 25,
            "temperature": 0.8,
            ... other TrueStreamingRequest fields
        }
    }

    OR:
    {
        "type": "ping"  // Keep-alive ping
    }

    OR:
    {
        "type": "cancel"  // Cancel current generation
    }

    Message Format (Server -> Client):
    - Binary: WAV header followed by audio chunks
    - JSON (info): {"type": "info", "message": "..."}
    - JSON (error): {"type": "error", "error": "..."}
    - JSON (metrics): {"type": "metrics", "data": {...}}
    - JSON (done): {"type": "done", "total_chunks": N}
    - JSON (pong): {"type": "pong"}
    """

    # Generate unique connection ID
    connection_id = str(uuid.uuid4())[:8]
    manager = get_connection_manager()

    # Accept connection
    await manager.connect(websocket, connection_id)

    # Send connection confirmation
    await manager.send_json(connection_id, {
        "type": "connected",
        "connection_id": connection_id,
        "message": "Connected to TRUE streaming WebSocket"
    })

    print(f"[{connection_id}] WebSocket connection established")

    try:
        # Main message loop
        while True:
            # Wait for message from client
            try:
                raw_message = await websocket.receive_text()
            except WebSocketDisconnect:
                print(f"[{connection_id}] Client disconnected")
                break

            # Parse message
            try:
                message_data = json.loads(raw_message)
                message = WebSocketStreamingMessage(**message_data)
            except json.JSONDecodeError:
                await manager.send_json(connection_id, {
                    "type": "error",
                    "error": "Invalid JSON format"
                })
                continue
            except Exception as e:
                await manager.send_json(connection_id, {
                    "type": "error",
                    "error": f"Invalid message format: {str(e)}"
                })
                continue

            # Handle different message types
            if message.type == "ping":
                # Respond to ping with pong
                await manager.send_json(connection_id, {"type": "pong"})
                continue

            elif message.type == "cancel":
                # TODO: Implement cancellation logic
                await manager.send_json(connection_id, {
                    "type": "info",
                    "message": "Cancellation requested (not yet implemented)"
                })
                continue

            elif message.type == "stream_request":
                # Validate streaming model is ready
                if not is_streaming_ready():
                    error = get_streaming_initialization_error()
                    await manager.send_json(connection_id, {
                        "type": "error",
                        "error": f"Streaming model not ready: {error or 'Not initialized'}"
                    })
                    continue

                # Validate request data
                if not message.data:
                    await manager.send_json(connection_id, {
                        "type": "error",
                        "error": "Missing 'data' field in stream_request message"
                    })
                    continue

                request = message.data

                # Resolve voice path
                try:
                    voice_path, voice_language = resolve_voice_path_and_language(request.voice)
                except Exception as e:
                    await manager.send_json(connection_id, {
                        "type": "error",
                        "error": f"Invalid voice: {str(e)}"
                    })
                    continue

                # Send processing started message
                await manager.send_json(connection_id, {
                    "type": "info",
                    "message": "Starting TRUE streaming generation...",
                    "text_length": len(request.input),
                    "voice": request.voice,
                    "parameters": {
                        "chunk_size": request.chunk_size,
                        "context_window": request.context_window,
                        "temperature": request.temperature,
                        "cfg_weight": request.cfg_weight
                    }
                })

                # Update connection state
                manager.update_connection_state(connection_id, "streaming")

                # Generate and stream audio
                try:
                    # Send WAV header if output format is WAV
                    if request.output_format == "wav":
                        model = get_streaming_model()
                        wav_header = create_wav_header(
                            sample_rate=model.sr,
                            channels=1,
                            bits_per_sample=16
                        )
                        await manager.send_bytes(connection_id, wav_header)

                    chunk_count = 0

                    # Stream audio chunks
                    async for audio_chunk, metrics in generate_true_streaming_audio(
                        request=request,
                        voice_sample_path=voice_path,
                        connection_id=connection_id
                    ):
                        chunk_count += 1

                        # Send audio chunk
                        await manager.send_bytes(connection_id, audio_chunk)

                        # Send metrics if requested
                        if request.include_metrics and metrics:
                            await manager.send_json(connection_id, {
                                "type": "metrics",
                                "data": metrics
                            })

                    # Send completion message
                    await manager.send_json(connection_id, {
                        "type": "done",
                        "total_chunks": chunk_count,
                        "message": "Streaming complete"
                    })

                    # Update connection state
                    manager.update_connection_state(connection_id, "idle")

                    print(f"[{connection_id}] ✓ Streaming completed successfully ({chunk_count} chunks)")

                except Exception as e:
                    error_trace = traceback.format_exc()
                    print(f"[{connection_id}] ✗ Error during streaming:")
                    print(error_trace)

                    await manager.send_json(connection_id, {
                        "type": "error",
                        "error": f"Streaming failed: {str(e)}"
                    })

                    manager.update_connection_state(connection_id, "error")

            else:
                # Unknown message type
                await manager.send_json(connection_id, {
                    "type": "error",
                    "error": f"Unknown message type: {message.type}"
                })

    except WebSocketDisconnect:
        print(f"[{connection_id}] Client disconnected normally")

    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"[{connection_id}] ✗ WebSocket error:")
        print(error_trace)

        try:
            await manager.send_json(connection_id, {
                "type": "error",
                "error": f"Internal error: {str(e)}"
            })
        except:
            pass  # Connection might already be closed

    finally:
        # Cleanup connection
        await manager.disconnect(connection_id)
        print(f"[{connection_id}] Connection closed")


@router.get(
    "/ws/stream/connections",
    summary="Get active WebSocket connections",
    description="Get information about active WebSocket streaming connections (for monitoring)"
)
async def get_active_connections():
    """Get information about active WebSocket connections"""
    manager = get_connection_manager()

    return {
        "total_connections": manager.get_connection_count(),
        "timestamp": __import__('time').time()
    }
