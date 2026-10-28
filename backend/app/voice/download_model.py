"""Explicit, one-time installation of the local speech model.

    python -m app.voice.download_model            # model from STT_MODEL (default "small")

Downloads the faster-whisper model (tiny ~75 MB, base ~145 MB, small ~460 MB,
medium ~1.5 GB) into `STT_MODEL_DIR` from Hugging Face. This is the only code
path that downloads a speech model; requests never do (ADR 0010).
"""

from __future__ import annotations

import sys

from app.core.config import get_settings


def main() -> int:
    settings = get_settings()
    from faster_whisper import download_model

    print(f"Downloading speech model '{settings.stt_model}' to {settings.stt_model_dir} ...")
    path = download_model(settings.stt_model, cache_dir=settings.stt_model_dir)
    print(f"Installed at {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
