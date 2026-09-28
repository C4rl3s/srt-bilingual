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

    # --- Traducción (Fases 3 y 4) ---
    default_target_lang: str = "KO"
    # Proveedores en orden de preferencia, separados por comas (`azure,deepl`): se
    # usa el primero con cupo suficiente. Ver `services/translation/registry.py`.
    translation_providers: str | None = None
    # Forma de la Fase 3, un solo proveedor. Se sigue aceptando si no hay lista.
    translation_provider: str = "deepl"
    deepl_api_key: str | None = None
    azure_translator_key: str | None = None
    azure_translator_region: str | None = None
    # Azure no deja consultar el consumo: su cupo sale del registro de la app y este
    # es el límite contra el que se compara (el gratuito del plan F0).
    azure_translator_limite_mensual: int = 2_000_000
    # Carpeta alternativa para los bilingües. Vacía (lo normal): van junto al vídeo.
    # Red de seguridad por si un recurso de la biblioteca es de solo lectura.
    output_dir: str | None = None

    # --- Pistas incrustadas (Fase 5) ---
    # Ejecutables de ffmpeg. Por defecto, los del PATH; una ruta completa si no están.
    ffprobe_path: str = "ffprobe"
    ffmpeg_path: str = "ffmpeg"

    @property
    def proveedores(self) -> list[str]:
        """Nombres de los proveedores configurados, en orden de preferencia."""
        lista = self.translation_providers or self.translation_provider
        return [nombre.strip().lower() for nombre in lista.split(",") if nombre.strip()]


settings = Settings()
