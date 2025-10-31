"""
Request models for API validation
"""

from typing import Optional
from pydantic import BaseModel, Field, validator


class TTSRequest(BaseModel):
    """Text-to-speech request model"""
    
    input: str = Field(..., description="The text to generate audio for", min_length=1, max_length=3000)
    voice: Optional[str] = Field("alloy", description="Voice to use (ignored - uses voice sample)")
    response_format: Optional[str] = Field("wav", description="Audio format (always returns WAV)")
    speed: Optional[float] = Field(1.0, description="Speed of speech (ignored)")
    stream_format: Optional[str] = Field("audio", description="Streaming format: 'audio' for raw audio stream, 'sse' for Server-Side Events")
    
    # Custom TTS parameters
    exaggeration: Optional[float] = Field(None, description="Emotion intensity", ge=0.25, le=2.0)
    cfg_weight: Optional[float] = Field(None, description="Pace control", ge=0.0, le=1.0)
    temperature: Optional[float] = Field(None, description="Sampling temperature", ge=0.05, le=5.0)
    
    # Streaming-specific parameters
    streaming_chunk_size: Optional[int] = Field(None, description="Characters per streaming chunk", ge=50, le=500)
    streaming_strategy: Optional[str] = Field(None, description="Chunking strategy for streaming")
    streaming_buffer_size: Optional[int] = Field(None, description="Number of chunks to buffer", ge=1, le=10)
    streaming_quality: Optional[str] = Field(None, description="Speed vs quality trade-off")
    
    @validator('input')
    def validate_input(cls, v):
        if not v or not v.strip():
            raise ValueError('Input text cannot be empty')
        return v.strip()
    
    @validator('stream_format')
    def validate_stream_format(cls, v):
        if v is not None:
            allowed_formats = ['audio', 'sse']
            if v not in allowed_formats:
                raise ValueError(f'stream_format must be one of: {", ".join(allowed_formats)}')
        return v
    
    @validator('streaming_strategy')
    def validate_streaming_strategy(cls, v):
        if v is not None:
            allowed_strategies = ['sentence', 'paragraph', 'fixed', 'word']
            if v not in allowed_strategies:
                raise ValueError(f'streaming_strategy must be one of: {", ".join(allowed_strategies)}')
        return v
    
    @validator('streaming_quality')
    def validate_streaming_quality(cls, v):
        if v is not None:
            allowed_qualities = ['fast', 'balanced', 'high']
            if v not in allowed_qualities:
                raise ValueError(f'streaming_quality must be one of: {", ".join(allowed_qualities)}')
        return v


class TrueStreamingRequest(BaseModel):
    """
    TRUE model-level streaming request model.

    This is different from the standard TTSRequest which does text-level chunking (fake streaming).
    This model enables REAL model-level streaming where speech tokens are generated incrementally
    using KV-cache, resulting in much lower latency to first audio chunk.

    NOTE: The chatterbox-streaming model has a simpler interface than expected.
    Some parameters below are accepted but IGNORED (kept for future compatibility):
    - top_p, max_new_tokens, min_new_tokens: NOT implemented in generate_stream()
    - alignment monitoring: NOT exposed in API (may be internal)
    - enable_fade_in: Fade is always applied, controlled by fade_in_duration_ms
    """

    # Core TTS parameters
    input: str = Field(..., description="The text to generate audio for", min_length=1, max_length=3000)
    voice: Optional[str] = Field("alloy", description="Voice name or alias from voice library")

    # Standard TTS parameters (✅ SUPPORTED)
    exaggeration: Optional[float] = Field(0.5, description="Emotion intensity (0.25-2.0)", ge=0.25, le=2.0)
    cfg_weight: Optional[float] = Field(0.5, description="Classifier-free guidance weight (0.0-1.0)", ge=0.0, le=1.0)
    temperature: Optional[float] = Field(0.8, description="Sampling temperature (0.05-5.0)", ge=0.05, le=5.0)

    # Advanced parameters (⚠️ ACCEPTED BUT IGNORED - for future compatibility)
    top_p: Optional[float] = Field(0.95, description="[IGNORED] Nucleus sampling threshold (not supported by generate_stream)", ge=0.0, le=1.0)
    max_new_tokens: Optional[int] = Field(4096, description="[IGNORED] Maximum speech tokens (not supported by generate_stream)", ge=100, le=10000)
    min_new_tokens: Optional[int] = Field(0, description="[IGNORED] Minimum speech tokens (not supported by generate_stream)", ge=0, le=1000)
    enable_alignment_monitoring: Optional[bool] = Field(True, description="[IGNORED] Alignment monitoring (not exposed in API)")
    alignment_window_size: Optional[int] = Field(50, description="[IGNORED] Alignment window size (not exposed in API)", ge=10, le=200)
    alignment_threshold: Optional[float] = Field(0.15, description="[IGNORED] Alignment threshold (not exposed in API)", ge=0.0, le=1.0)

    # TRUE STREAMING PARAMETERS (✅ SUPPORTED)
    chunk_size: Optional[int] = Field(25, description="Speech tokens per audio chunk (default: 25). Lower = faster response, higher = better continuity", ge=10, le=100)
    context_window: Optional[int] = Field(50, description="Overlap tokens for smooth transitions (default: 50)", ge=0, le=200)

    # Audio processing (✅ SUPPORTED)
    enable_fade_in: Optional[bool] = Field(True, description="Enable fade-in smoothing (controlled by fade_in_duration_ms)")
    fade_in_duration_ms: Optional[int] = Field(20, description="Fade-in duration in milliseconds (0=disable fade)", ge=0, le=100)

    # Output format
    output_format: Optional[str] = Field("wav", description="Audio format: 'wav' (raw PCM) or 'base64' (base64-encoded)")

    # Metrics and debugging
    include_metrics: Optional[bool] = Field(True, description="Include generation metrics (latency, RTF, token count)")
    print_metrics: Optional[bool] = Field(False, description="Print metrics to server console")

    @validator('input')
    def validate_input(cls, v):
        if not v or not v.strip():
            raise ValueError('Input text cannot be empty')
        return v.strip()

    @validator('output_format')
    def validate_output_format(cls, v):
        if v is not None:
            allowed_formats = ['wav', 'base64']
            if v not in allowed_formats:
                raise ValueError(f'output_format must be one of: {", ".join(allowed_formats)}')
        return v


class WebSocketStreamingMessage(BaseModel):
    """
    WebSocket message format for streaming requests.

    Clients send this JSON message over WebSocket to initiate streaming.
    """

    type: str = Field(..., description="Message type: 'stream_request', 'cancel', 'ping'")
    data: Optional[TrueStreamingRequest] = Field(None, description="Streaming request data (required for type='stream_request')")

    @validator('type')
    def validate_type(cls, v):
        allowed_types = ['stream_request', 'cancel', 'ping']
        if v not in allowed_types:
            raise ValueError(f'type must be one of: {", ".join(allowed_types)}')
        return v 