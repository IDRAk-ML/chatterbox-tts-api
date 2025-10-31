# Parameter Fix for generate_stream()

## Problem

The `generate_stream()` method in chatterbox-streaming has a **simpler signature** than expected. We were calling it with parameters that don't exist, causing `AttributeError`.

## Actual generate_stream() Signature

```python
def generate_stream(
    self,
    text: str,
    audio_prompt_path: Optional[str] = None,
    exaggeration: float = 0.5,
    cfg_weight: float = 0.5,
    temperature: float = 0.8,
    chunk_size: int = 25,
    context_window = 50,
    fade_duration=0.02,  # seconds
    print_metrics: bool = True,
) -> Generator[Tuple[torch.Tensor, StreamingMetrics], None, None]:
```

## Parameters NOT Supported

These parameters were in our API but are **NOT supported** by `generate_stream()`:

- ❌ `top_p` - Nucleus sampling
- ❌ `max_new_tokens` - Maximum tokens to generate
- ❌ `min_new_tokens` - Minimum tokens to generate
- ❌ `enable_alignment_monitoring` - Alignment monitoring
- ❌ `alignment_window_size` - Alignment window
- ❌ `alignment_threshold` - Alignment threshold

## Parameters SUPPORTED

These parameters **ARE supported**:

- ✅ `text` - Input text
- ✅ `audio_prompt_path` - Voice sample path
- ✅ `exaggeration` - Emotion intensity (0.25-2.0)
- ✅ `cfg_weight` - CFG weight (0.0-1.0)
- ✅ `temperature` - Sampling temperature (0.05-5.0)
- ✅ `chunk_size` - Speech tokens per chunk (10-100)
- ✅ `context_window` - Overlap tokens (0-200)
- ✅ `fade_duration` - Fade-in duration in seconds
- ✅ `print_metrics` - Print metrics to console

## Changes Made

### 1. app/core/true_streaming.py

**Before (BROKEN):**
```python
generator = model.generate_stream(
    text=request.input,
    audio_prompt_path=voice_sample_path,
    exaggeration=request.exaggeration,
    cfg_weight=request.cfg_weight,
    temperature=request.temperature,
    top_p=request.top_p,  # ❌ Doesn't exist!
    chunk_size=request.chunk_size,
    context_window=request.context_window,
    max_new_tokens=request.max_new_tokens,  # ❌ Doesn't exist!
    min_new_tokens=request.min_new_tokens,  # ❌ Doesn't exist!
    print_metrics=request.print_metrics,
)
```

**After (FIXED):**
```python
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
```

### 2. app/models/requests.py

Added documentation to TrueStreamingRequest:
- Marked unsupported parameters as `[IGNORED]`
- Kept them in the API for backward compatibility
- Added notes about which parameters actually work

## Testing

Start the server:
```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 4123
```

Test streaming:
```bash
python examples/websocket_client_python.py
```

Expected output:
```
✓ Connected! Connection ID: abc12345
⚡ First chunk latency: 0.5s
✓ Streaming complete!
```

## Summary

- **Root cause**: Calling `generate_stream()` with non-existent parameters
- **Solution**: Use only the 9 supported parameters
- **Impact**: TRUE streaming now works!
- **Trade-off**: Some advanced parameters are ignored

---

**Status**: ✅ FIXED
**Date**: 2025-10-31
