"""Configuración de la aplicación.

Lee las variables de entorno (vía `.env`) con pydantic-settings y las expone como
una instancia única `settings` importable desde el resto del backend.
"""

from functools import cached_property

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

    # --- Carpetas a escanear (las mismas compartidas en Plex) ---
    # Cadena con rutas separadas por ';' (formato documentado en .env.example).
    media_folders: str = ""

    # --- Traducción (se usa en Fase 3) ---
    default_target_lang: str = "KO"
    deepl_api_key: str | None = None

    @cached_property
    def carpetas(self) -> list[str]:
        """Lista de rutas a escanear, partiendo `media_folders` por ';'."""
        return [ruta.strip() for ruta in self.media_folders.split(";") if ruta.strip()]


settings = Settings()
