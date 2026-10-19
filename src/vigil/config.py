"""Configuration management for VIGIL."""

import os
from dataclasses import dataclass
from pathlib import Path


def load_env_file(dotenv_path: Path | None = None) -> None:
    """Load key-value pairs from a .env file into os.environ if not already set."""
    if dotenv_path is None:
        dotenv_path = Path.cwd() / ".env"

    if not dotenv_path.is_file():
        return

    try:
        content = dotenv_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        # Ignore errors reading .env in restricted environments
        return


@dataclass(frozen=True)
class VigilConfig:
    """Runtime configuration for VIGIL models, storage, and orchestration."""

    llm_provider: str
    gemini_api_key: str | None
    gemini_model: str
    groq_api_key: str | None
    groq_reasoning_model: str
    groq_vision_model: str
    groq_audio_model: str
    ollama_base_url: str
    ollama_model: str
    openrouter_api_key: str | None
    openrouter_model: str
    storage_root: str
    log_level: str

    @classmethod
    def from_env(cls) -> "VigilConfig":
        """Build configuration from environment variables and .env file."""
        load_env_file()

        gemini_key = os.getenv("GEMINI_API_KEY")
        groq_key = os.getenv("GROQ_API_KEY")
        openrouter_key = os.getenv("OPENROUTER_API_KEY")

        # Determine default provider intelligently
        provider = os.getenv("VIGIL_LLM_PROVIDER")
        if not provider:
            if gemini_key:
                provider = "gemini"
            elif groq_key:
                provider = "groq"
            elif openrouter_key:
                provider = "openrouter"
            else:
                provider = "mock"

        return cls(
            llm_provider=provider.lower().strip(),
            gemini_api_key=gemini_key,
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            groq_api_key=groq_key,
            groq_reasoning_model=os.getenv(
                "GROQ_REASONING_MODEL", "llama-3.3-70b-versatile"
            ),
            groq_vision_model=os.getenv(
                "GROQ_VISION_MODEL", "llama-3.2-11b-vision-preview"
            ),
            groq_audio_model=os.getenv("GROQ_AUDIO_MODEL", "whisper-large-v3"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2-vision"),
            openrouter_api_key=openrouter_key,
            openrouter_model=os.getenv(
                "OPENROUTER_MODEL", "google/gemini-2.0-flash-exp:free"
            ),
            storage_root=os.getenv("VIGIL_STORAGE_ROOT", "./storage_data"),
            log_level=os.getenv("VIGIL_LOG_LEVEL", "INFO"),
        )


# Global default configuration instance
config = VigilConfig.from_env()
