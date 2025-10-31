# TRUE Model-Level Streaming Documentation

## Overview

This Chatterbox TTS API now supports **TRUE model-level streaming** via WebSocket, enabling real-time text-to-speech generation with incredibly low latency (~0.5s to first audio chunk).

### What's the Difference?

| Feature | Standard "Streaming" (Fake) | TRUE Model Streaming |
|---------|---------------------------|---------------------|
| **Method** | Text chunking | Incremental token generation |
| **Latency** | Full generation time / num_chunks | ~0.5s to first chunk |
| **Technology** | Multiple `model.generate()` calls | Single `model.generate_stream()` with KV-cache |
| **RTF** | Variable | < 1.0 (faster than real-time) |
| **API** | HTTP/SSE | WebSocket |
| **Use Case** | Backward compatibility | Real-time applications |

## Architecture

### How TRUE Streaming Works

1. **Token-Level Generation**: Speech tokens are generated incrementally using the transformer's KV-cache
2. **Chunked Audio Synthesis**: Every N tokens (default: 25), audio is generated from the token buffer
3. **Context Window**: Overlapping tokens (default: 50) ensure smooth audio transitions between chunks
4. **Fade-In Smoothing**: 20ms linear fade-in prevents audio clicks/pops at chunk boundaries
5. **Alignment Monitoring**: Real-time detection of hallucinations and repetitions

### Key Components

- **Streaming Model**: `chatterbox-streaming` package with KV-cache support
- **WebSocket Manager**: Connection pooling and state management
- **True Streaming Service**: Async wrapper around `model.generate_stream()`
- **WebSocket Endpoint**: `/ws/stream/audio` for real-time bidirectional communication

## Installation

### 1. Install Dependencies

The streaming functionality requires the `chatterbox-streaming` package:

```bash
cd /root/chatterbox-tts-api
pip install -r requirements.txt
```

This will install:
- `chatterbox-streaming` - TRUE streaming model
- `websockets` - WebSocket support
- All existing dependencies

### 2. Start the Server

```bash
python main.py
```

The server will automatically:
1. Load the standard model (for existing endpoints)
2. Load the streaming model (for WebSocket endpoints)
3. Display initialization status in the console

### 3. Verify Streaming is Available

Check the streaming status endpoint:

```bash
curl http://localhost:8000/ws/stream/status
```

Expected response:
```json
{
  "available": true,
  "ready": true,
  "sample_rate": 24000,
  "supported_formats": ["wav", "base64"],
  "description": "TRUE model-level streaming with KV-cache",
  "features": {
    "incremental_generation": true,
    "kv_cache": true,
    "alignment_monitoring": true,
    "low_latency": true,
    "real_time_factor": "< 1.0 (faster than real-time)"
  }
}
```

## API Reference

### WebSocket Endpoint

**URL**: `ws://localhost:8000/ws/stream/audio`

#### Connection Flow

1. **Client connects** to WebSocket
2. **Server responds** with connection confirmation:
   ```json
   {
     "type": "connected",
     "connection_id": "abc12345",
     "message": "Connected to TRUE streaming WebSocket"
   }
   ```
3. **Client sends** streaming request
4. **Server streams** audio chunks (binary) + metrics (JSON)
5. **Server sends** completion message
6. **Connection remains open** for next request

#### Message Types

##### Client → Server

**1. Stream Request**
```json
{
  "type": "stream_request",
  "data": {
    "input": "Text to synthesize",
    "voice": "alloy",

    // TTS Parameters
    "exaggeration": 0.5,
    "cfg_weight": 0.5,
    "temperature": 0.8,
    "top_p": 0.95,

    // TRUE STREAMING Parameters
    "chunk_size": 25,
    "context_window": 50,
    "max_new_tokens": 4096,
    "min_new_tokens": 0,

    // Alignment Monitoring
    "enable_alignment_monitoring": true,
    "alignment_window_size": 50,
    "alignment_threshold": 0.15,

    // Audio Processing
    "enable_fade_in": true,
    "fade_in_duration_ms": 20,

    // Output
    "output_format": "wav",
    "include_metrics": true,
    "print_metrics": false
  }
}
```

**2. Ping (Keep-Alive)**
```json
{
  "type": "ping"
}
```

**3. Cancel (Future)**
```json
{
  "type": "cancel"
}
```

##### Server → Client

**1. Binary Audio Data**
- First message: WAV header (44 bytes)
- Subsequent messages: PCM audio chunks

**2. Info Message**
```json
{
  "type": "info",
  "message": "Starting TRUE streaming generation...",
  "text_length": 100,
  "voice": "alloy",
  "parameters": {
    "chunk_size": 25,
    "context_window": 50,
    "temperature": 0.8
  }
}
```

**3. Metrics Message**
```json
{
  "type": "metrics",
  "data": {
    "chunk": 1,
    "latency_to_first_chunk": 0.472,
    "elapsed_time": 0.5,
    "audio_duration": 1.2,
    "rtf": 0.42,
    "chunk_size_bytes": 38400,
    "sample_rate": 24000
  }
}
```

**4. Done Message**
```json
{
  "type": "done",
  "total_chunks": 6,
  "message": "Streaming complete"
}
```

**5. Error Message**
```json
{
  "type": "error",
  "error": "Error description"
}
```

**6. Pong (Response to Ping)**
```json
{
  "type": "pong"
}
```

## Client Examples

### Python Client

See `examples/websocket_client_python.py`:

```python
from websocket_client_python import ChatterboxStreamingClient

async def main():
    client = ChatterboxStreamingClient(base_url="ws://localhost:8000")

    await client.connect()

    await client.stream_speech(
        text="Hello! This is TRUE streaming.",
        output_file="output.wav",
        chunk_size=25,
        temperature=0.8
    )

    await client.disconnect()

asyncio.run(main())
```

Run it:
```bash
python examples/websocket_client_python.py
```

### JavaScript/HTML Client

See `examples/websocket_client_javascript.html`:

Open in browser:
```bash
# Serve the HTML file
python -m http.server 8080
# Then open: http://localhost:8080/examples/websocket_client_javascript.html
```

Or open directly in browser (file:// protocol).

## Streaming Parameters Explained

### Core TTS Parameters

- **`exaggeration`** (0.25-2.0, default: 0.5): Emotion intensity
- **`cfg_weight`** (0.0-1.0, default: 0.5): Classifier-free guidance weight (pace control)
- **`temperature`** (0.05-5.0, default: 0.8): Sampling randomness
- **`top_p`** (0.0-1.0, default: 0.95): Nucleus sampling threshold

### TRUE Streaming Parameters

- **`chunk_size`** (10-100, default: 25):
  - Speech tokens per audio chunk
  - Lower = faster first chunk, more chunks, potential quality trade-off
  - Higher = slower first chunk, fewer chunks, smoother audio
  - Recommended: 25-50

- **`context_window`** (0-200, default: 50):
  - Overlap tokens for smooth transitions
  - Prevents audio discontinuities between chunks
  - Higher = smoother but more computation
  - Recommended: 50

- **`max_new_tokens`** (100-10000, default: 4096):
  - Maximum speech tokens to generate
  - Limits generation length for safety

- **`min_new_tokens`** (0-1000, default: 0):
  - Minimum speech tokens to generate
  - Prevents premature stopping

### Alignment Monitoring

- **`enable_alignment_monitoring`** (bool, default: true):
  - Enable real-time hallucination detection
  - Monitors attention alignment patterns
  - Can force EOS if problems detected

- **`alignment_window_size`** (10-200, default: 50):
  - Window size for alignment analysis

- **`alignment_threshold`** (0.0-1.0, default: 0.15):
  - Threshold for detecting alignment issues
  - Lower = more sensitive to problems

### Audio Processing

- **`enable_fade_in`** (bool, default: true):
  - Apply linear fade-in to chunks
  - Prevents clicks/pops at boundaries

- **`fade_in_duration_ms`** (0-100, default: 20):
  - Fade-in duration in milliseconds

### Output Options

- **`output_format`** ("wav" | "base64", default: "wav"):
  - wav: Raw PCM binary data
  - base64: Base64-encoded audio

- **`include_metrics`** (bool, default: true):
  - Send metrics messages during streaming

- **`print_metrics`** (bool, default: false):
  - Print metrics to server console

## Performance Metrics

Typical performance (CPU/GPU varies):

```
Latency to first chunk:    ~0.5s
Total generation time:     ~3s (for 6s of audio)
Real-Time Factor (RTF):    ~0.5 (2x faster than real-time!)
Chunks:                    6 (for ~6s audio with chunk_size=25)
```

**RTF < 1.0 means FASTER THAN REAL-TIME**

### Optimization Tips

1. **Lower chunk_size** (15-20) for even faster first chunk
2. **Reduce context_window** (25-30) if smoothness isn't critical
3. **Use GPU** for significant speedup
4. **Batch multiple requests** using connection pooling

## Comparison: Standard vs TRUE Streaming

### Standard "Streaming" (Text Chunking)

```
Endpoint: POST /audio/speech?stream_format=sse
Method: Server-Sent Events (SSE)

Flow:
1. Split text into chunks: ["Hello world", "How are you"]
2. Generate chunk 1: model.generate("Hello world") → 2s
3. Send audio chunk 1
4. Generate chunk 2: model.generate("How are you") → 2s
5. Send audio chunk 2

Total time: 4s
Latency to first: 2s
```

### TRUE Streaming (Model-Level)

```
Endpoint: ws://localhost:8000/ws/stream/audio
Method: WebSocket

Flow:
1. Start generation: model.generate_stream("Hello world. How are you")
2. Generate tokens 1-25 → audio chunk 1 → send (0.5s)
3. Generate tokens 26-50 → audio chunk 2 → send (0.5s)
4. Generate tokens 51-75 → audio chunk 3 → send (0.5s)
5. Continue until done...

Total time: 3s
Latency to first: 0.5s
```

**Result**: TRUE streaming is 4x faster to first audio!

## Troubleshooting

### Streaming Model Not Available

**Error**: `"streaming_available": false`

**Solution**:
```bash
pip install git+https://github.com/davidbrowne17/chatterbox-streaming.git
```

### Connection Refused

**Error**: WebSocket connection failed

**Checklist**:
- Is the server running? `ps aux | grep main.py`
- Check port: `curl http://localhost:8000/health`
- Check firewall: `sudo ufw status`
- Try different URL: `ws://127.0.0.1:8000/ws/stream/audio`

### Streaming Model Not Ready

**Error**: `"Streaming model not ready"`

**Solution**: Wait for model to initialize. Check status:
```bash
curl http://localhost:8000/ws/stream/status
```

### Audio Quality Issues

**Symptoms**: Clicks, pops, discontinuities

**Solutions**:
1. Ensure `enable_fade_in: true`
2. Increase `fade_in_duration_ms` to 30-40
3. Increase `context_window` to 75-100
4. Use higher `chunk_size` (40-50)

### Performance Issues

**Symptoms**: Slow generation, high RTF

**Solutions**:
1. Use GPU if available
2. Reduce `chunk_size` (but may increase total chunks)
3. Lower `context_window`
4. Check system resources: `top` or `htop`

## Advanced Usage

### Custom Voice

```python
await client.stream_speech(
    text="Hello in custom voice!",
    voice="my_custom_voice",  # Must exist in voice library
    output_file="output.wav"
)
```

### High-Speed Mode (Lower Quality)

```python
await client.stream_speech(
    text="Fast speech!",
    chunk_size=15,  # Smaller chunks
    context_window=25,  # Less overlap
    temperature=0.5,  # Less randomness
    output_file="output.wav"
)
```

### High-Quality Mode (Slower)

```python
await client.stream_speech(
    text="High quality speech!",
    chunk_size=50,  # Larger chunks
    context_window=100,  # More overlap
    temperature=0.8,  # More natural
    enable_alignment_monitoring=True,
    output_file="output.wav"
)
```

### Monitoring Multiple Connections

```bash
# Get active connections
curl http://localhost:8000/ws/stream/connections
```

Response:
```json
{
  "total_connections": 3,
  "timestamp": 1699564823.123
}
```

## Architecture Details

### Dual-Mode Support

The API now supports BOTH standard and streaming models:

```python
# Standard model (existing endpoints)
from app.core.tts_model import get_model
model = get_model()  # ChatterboxTTS (multilingual)

# Streaming model (WebSocket endpoints)
from app.core.tts_model import get_streaming_model
streaming_model = get_streaming_model()  # ChatterboxStreamingTTS
```

### WebSocket Manager

Connection pooling and state management:

```python
from app.core.websocket_manager import get_connection_manager

manager = get_connection_manager()
await manager.connect(websocket, connection_id)
await manager.send_bytes(connection_id, audio_chunk)
await manager.send_json(connection_id, {"type": "metrics", ...})
await manager.disconnect(connection_id)
```

### Request/Response Models

Pydantic models for validation:

```python
from app.models import TrueStreamingRequest, WebSocketStreamingMessage

# Validate request
request = TrueStreamingRequest(
    input="Hello",
    chunk_size=25,
    temperature=0.8
)

# Parse WebSocket message
message = WebSocketStreamingMessage(
    type="stream_request",
    data=request
)
```

## Security Considerations

### Rate Limiting

TODO: Implement rate limiting per connection:
- Max requests per minute
- Max concurrent connections per IP
- Max audio duration per request

### Authentication

TODO: Add WebSocket authentication:
- API key in connection URL
- Token-based auth
- OAuth2 support

### Resource Limits

Current limits:
- Max text length: 3000 characters
- Max new tokens: 10000
- Connection timeout: 30 minutes (configurable)

## Future Enhancements

- [ ] Cancellation support (abort generation mid-stream)
- [ ] Multi-language streaming (when available)
- [ ] Real-time voice cloning (dynamic voice switching)
- [ ] Audio effects pipeline (reverb, EQ, compression)
- [ ] Streaming from SSE (alternative to WebSocket)
- [ ] gRPC streaming support
- [ ] Load balancing across multiple model instances

## References

- Chatterbox Streaming Repository: https://github.com/davidbrowne17/chatterbox-streaming
- FastAPI WebSockets: https://fastapi.tiangolo.com/advanced/websockets/
- WebSocket Protocol: https://tools.ietf.org/html/rfc6455

## Support

For issues, questions, or feature requests:
- Open an issue on GitHub
- Check server logs: `tail -f /var/log/chatterbox-tts.log`
- Enable debug mode: `export LOG_LEVEL=DEBUG`

---

**Last Updated**: 2025-10-30
**Version**: 1.0.0
