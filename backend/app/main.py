"""Punto de entrada de la API de srt-bilingual.

Fase 0: solo expone un endpoint de salud (`/health`) y habilita CORS para que el
frontend de desarrollo (Vite, puerto 5173) pueda comunicarse con la API.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
