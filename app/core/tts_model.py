"""
TTS model initialization and management

NOTE: Using chatterbox-streaming package which includes BOTH:
- generate() for standard generation
- generate_stream() for TRUE model-level streaming

Multilingual support is NOT available (English only).
"""

import os
import asyncio
from enum import Enum
from typing import Optional, Dict, Any

# Chatterbox Streaming TTS (includes both generate() and generate_stream())
try:
    from chatterbox.tts import ChatterboxTTS
    STREAMING_AVAILABLE = True
except ImportError:
    STREAMING_AVAILABLE = False
    ChatterboxTTS = None
    print("ERROR: chatterbox-streaming package not found. TTS will not be available.")

from app.config import Config, detect_device

# Global model instance (used for BOTH standard and streaming)
_model = None
_device = None
_initialization_state = "not_started"
_initialization_error = None
_initialization_progress = ""
_is_multilingual = False  # Streaming package is English only
_supported_languages = {"en": "English"}  # English only


class InitializationState(Enum):
    NOT_STARTED = "not_started"
    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"


async def initialize_model():
    """
    Initialize the Chatterbox TTS model with streaming support.

    This model supports BOTH:
    - model.generate() for standard generation
    - model.generate_stream() for TRUE streaming
    """
    global _model, _device, _initialization_state, _initialization_error, _initialization_progress, _is_multilingual, _supported_languages

    if not STREAMING_AVAILABLE:
        _initialization_state = InitializationState.ERROR.value
        _initialization_error = "chatterbox-streaming package not installed"
        _initialization_progress = "Failed: streaming package not found"
        print("✗ Cannot initialize model: chatterbox-streaming package not installed")
        raise ImportError("chatterbox-streaming package not installed. Install it with: pip install git+https://github.com/davidbrowne17/chatterbox-streaming.git")

    try:
        _initialization_state = InitializationState.INITIALIZING.value
        _initialization_progress = "Validating configuration..."

        Config.validate()
        _device = detect_device()

        print(f"Initializing Chatterbox TTS model with streaming support...")
        print(f"Device: {_device}")
        print(f"Voice sample: {Config.VOICE_SAMPLE_PATH}")
        print(f"Model cache: {Config.MODEL_CACHE_DIR}")

        _initialization_progress = "Creating model cache directory..."
        os.makedirs(Config.MODEL_CACHE_DIR, exist_ok=True)

        _initialization_progress = "Checking voice sample..."
        if not os.path.exists(Config.VOICE_SAMPLE_PATH):
            raise FileNotFoundError(f"Voice sample not found: {Config.VOICE_SAMPLE_PATH}")

        _initialization_progress = "Configuring device compatibility..."
        if _device == 'cpu':
            import torch
            original_load = torch.load
            original_load_file = None

            try:
                import safetensors.torch
                original_load_file = safetensors.torch.load_file
            except ImportError:
                pass

            def force_cpu_torch_load(f, map_location=None, **kwargs):
                return original_load(f, map_location='cpu', **kwargs)

            def force_cpu_load_file(filename, device=None):
                return original_load_file(filename, device='cpu')

            torch.load = force_cpu_torch_load
            if original_load_file:
                safetensors.torch.load_file = force_cpu_load_file

        _initialization_progress = "Loading TTS model (this may take a while)..."
        loop = asyncio.get_event_loop()

        print(f"Loading Chatterbox Streaming TTS model...")
        _model = await loop.run_in_executor(
            None,
            lambda: ChatterboxTTS.from_pretrained(device=_device)
        )

        _is_multilingual = False
        _supported_languages = {"en": "English"}

        _initialization_state = InitializationState.READY.value
        _initialization_progress = "Model ready"
        _initialization_error = None
        print(f"✓ Model initialized successfully on {_device}")
        print(f"✓ Supports: generate() for standard TTS")
        print(f"✓ Supports: generate_stream() for TRUE streaming")
        print(f"✓ Language: English only (multilingual not available)")
        return _model

    except Exception as e:
        _initialization_state = InitializationState.ERROR.value
        _initialization_error = str(e)
        _initialization_progress = f"Failed: {str(e)}"
        print(f"✗ Failed to initialize model: {e}")
        raise e


async def initialize_streaming_model():
    """
    Legacy function for backward compatibility.

    The streaming model is the SAME as the standard model now,
    since chatterbox-streaming includes both generate() and generate_stream().
    """
    # Just ensure the main model is initialized
    if not is_ready():
        await initialize_model()
    return _model


def get_model():
    """Get the current model instance (supports both standard and streaming)"""
    return _model


def get_device():
    """Get the current device"""
    return _device


def get_initialization_state():
    """Get the current initialization state"""
    return _initialization_state


def get_initialization_progress():
    """Get the current initialization progress message"""
    return _initialization_progress


def get_initialization_error():
    """Get the initialization error if any"""
    return _initialization_error


def is_ready():
    """Check if the model is ready for use"""
    return _initialization_state == InitializationState.READY.value and _model is not None


def is_initializing():
    """Check if the model is currently initializing"""
    return _initialization_state == InitializationState.INITIALIZING.value


def is_multilingual():
    """Check if the loaded model supports multilingual generation"""
    return _is_multilingual


def get_supported_languages():
    """Get the dictionary of supported languages"""
    return _supported_languages.copy()


def supports_language(language_id: str):
    """Check if the model supports a specific language"""
    return language_id in _supported_languages


def get_model_info() -> Dict[str, Any]:
    """Get comprehensive model information"""
    return {
        "model_type": "streaming",
        "is_multilingual": _is_multilingual,
        "supported_languages": _supported_languages,
        "language_count": len(_supported_languages),
        "device": _device,
        "is_ready": is_ready(),
        "initialization_state": _initialization_state,
        "streaming_available": STREAMING_AVAILABLE,
        "streaming_ready": is_ready(),  # Same model, so same state
        "features": {
            "standard_generation": True,
            "true_streaming": True,
            "kv_cache": True,
            "alignment_monitoring": True
        }
    }


# Streaming model getters (for backward compatibility)
def get_streaming_model():
    """Get the streaming model instance (same as standard model)"""
    return _model


def is_streaming_available():
    """Check if streaming package is installed"""
    return STREAMING_AVAILABLE


def is_streaming_ready():
    """Check if the streaming model is ready for use (same as standard model)"""
    return is_ready()


def is_streaming_initializing():
    """Check if the streaming model is currently initializing (same as standard model)"""
    return is_initializing()


def get_streaming_initialization_state():
    """Get the streaming model initialization state (same as standard model)"""
    return _initialization_state


def get_streaming_initialization_progress():
    """Get the streaming model initialization progress message (same as standard model)"""
    return _initialization_progress


def get_streaming_initialization_error():
    """Get the streaming model initialization error if any (same as standard model)"""
    return _initialization_error
