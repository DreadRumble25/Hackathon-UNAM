"""API de NFL Matchup Analytics.

Ejecuta: .venv/bin/uvicorn backend.main:app --reload
Los datos se calculan en memoria al arrancar (en segundo plano). Mientras tanto
/health responde de inmediato y /api/estado informa el progreso.
"""
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query

from backend.engine import engine


@asynccontextmanager
async def lifespan(_app: FastAPI):
    engine.start()
    yield


app = FastAPI(title="NFL Matchup Analytics", lifespan=lifespan)


def _ready():
    if engine.error:
        raise HTTPException(status_code=500, detail=f"Error al preparar los datos: {engine.error}")
    if not engine.ready:
        raise HTTPException(status_code=503, detail="Los datos se están preparando")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/estado")
def estado() -> dict:
    return engine.status()


@app.get("/api/filtros")
def filtros() -> dict:
    _ready()
    return engine.filtros()


@app.get("/api/resumen")
def resumen(
    equipo: Optional[str] = Query(None, max_length=3),
    grupo: str = Query("TODOS", pattern="^(TODOS|EDGE|IDL|OT|IOL)$"),
    semana: Optional[int] = Query(None, ge=1, le=30),
    partido: Optional[int] = Query(None, ge=0),
    min_snaps: int = Query(50, ge=1, le=400),
) -> dict:
    _ready()
    if equipo and equipo not in set(engine.games.homeTeamAbbr) | set(engine.games.visitorTeamAbbr):
        raise HTTPException(status_code=400, detail="Equipo no reconocido")
    return engine.resumen(team=equipo or None, grupo=grupo, week=semana, game=partido, min_snaps=min_snaps)


@app.get("/api/jugadores")
def jugadores() -> list:
    _ready()
    return engine.lista_jugadores()


@app.get("/api/jugador/{nfl_id}")
def jugador(nfl_id: int) -> dict:
    _ready()
    data = engine.jugador(nfl_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Jugador sin datos en el periodo analizado")
    return data


@app.get("/api/laboratorio")
def laboratorio() -> dict:
    _ready()
    return engine.lab
