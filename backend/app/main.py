"""Punto de entrada de la API de srt-bilingual.

Expone la salud (`/health`), la gestión de carpetas (`/folders`), el explorador de
disco del selector (`/fs`), el escaneo (`/scan`), el árbol de la biblioteca
(`/library`) y la consulta de subtítulos (`/subtitles`). CORS habilitado para el
frontend de desarrollo (Vite).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import filesystem, folders, library, scan, subtitles

app = FastAPI(
    title="srt-bilingual API",
    version="0.1.0",
    description="API para gestionar y generar subtítulos bilingües.",
)

# Orígenes permitidos en desarrollo (servidor de Vite).
allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Comprobación de salud usada por el frontend y por monitorización."""
    return {"status": "ok"}


# Routers de dominio (sin prefijo `/api`: el proxy de Vite ya reescribe `/api/...`).
app.include_router(folders.router)
app.include_router(filesystem.router)
app.include_router(scan.router)
app.include_router(library.router)
app.include_router(subtitles.router)
