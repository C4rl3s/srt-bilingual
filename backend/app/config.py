"""Configuración de la aplicación.

Lee las variables de entorno (vía `.env`) con pydantic-settings y las expone como
una instancia única `settings` importable desde el resto del backend.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Ajustes del backend cargados desde el entorno / fichero `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Base de datos ---
    database_url: str = "sqlite:///./srt_bilingual.db"

    # --- Traducción (Fase 3) ---
    default_target_lang: str = "KO"
    # Proveedor activo, por nombre (ver `services/translation/registry.py`).
    translation_provider: str = "deepl"
    deepl_api_key: str | None = None


settings = Settings()
