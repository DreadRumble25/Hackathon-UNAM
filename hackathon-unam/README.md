# NFL Matchup Analytics

Plataforma de análisis para entrenadores de la NFL que combina tres enfoques sobre los datos del NFL Big Data Bowl:

1. **Enfrentamientos** entre bloqueadores ofensivos y pass rushers (datos de PFF).
2. **Características físicas y de movimiento** de los jugadores (tracking de Next Gen Stats a 10 Hz).
3. **Modelado estadístico** que relaciona el físico, el contexto de la jugada y la generación de presión.

Proyecto para el Hackathon NFL Big Data Bowl, UNAM.

> **Estado:** en desarrollo. El backend (motor de datos, modelo y API) ya funciona. El dashboard está en construcción: el centro de control y el perfil de jugador ya están escritos, pero el laboratorio de explosividad y la navegación todavía no.

## Objetivo

Responder qué características físicas y de movimiento están asociadas con una mayor generación de presión sobre el quarterback, y convertir esa respuesta en información útil para un entrenador:

- quiénes generan más presión, y quiénes más de la que su perfil físico predice;
- qué bloqueadores tienen dificultades y contra qué perfil defensivo;
- cómo se compara un jugador con otros de su misma posición;
- en qué situaciones (down, play action, blitz, doble equipo) cambia el rendimiento.

## Hallazgo principal

**La explosividad inicial del defensor (`burst`, velocidad máxima durante el primer segundo después del snap) está asociada con más presión al QB.**

| Análisis | Resultado |
|---|---|
| Exploratorio (todos los snaps de pass rush, n = 36,259) | 7.5% de presión en el quintil más bajo de burst contra 17.9% en el más alto (2.4×) |
| Misma comparación con la población del modelo (EDGE e IDL, n = 33,540) | 7.3% contra 16.2% (2.2×) |
| Regresión logística, controlando peso, posición y contexto | OR 1.38 por +1 yd/s en EDGE y 1.54 en IDL (p < 0.001; IC95 robustos agrupados por jugador) |
| Efecto medido en desviaciones estándar de cada grupo | OR 1.37 (EDGE) y 1.39 (IDL): el efecto relativo es el mismo |
| Peso, una vez controlado el burst | Sin efecto propio (OR 0.99 por +10 lb en EDGE, p = 0.56) |

Probabilidad estimada de presión por jugada según el percentil de burst dentro del grupo (resto de variables en su promedio):

| Grupo | P10 | P50 | P90 |
|---|---:|---:|---:|
| EDGE | 7.9% | 11.6% | 16.2% |
| IDL | 5.8% | 9.0% | 12.5% |

El resultado se mantiene con distintos umbrales mínimos de snaps (de 1 a 200), al excluir a los rushers sin bloqueador asignado y al definir el grupo por la alineación real del jugador.

**Limitaciones:** es una asociación, no una relación causal. El burst también depende del plan de bloqueo y de los stunts, que no vienen en los datos. El modelo discrimina de forma modesta (AUC 0.61), así que sirve para comparar promedios, no para predecir una jugada individual. Los datos cubren solo jugadas de pase de las semanas 1 a 8 de la temporada 2021.

## Tecnologías

| Capa | Versión |
|---|---|
| Python / uv | 3.12.12 / 0.11.19 |
| Backend | FastAPI 0.115.14, Uvicorn 0.34.3, Pydantic 2.11.7 |
| Datos y estadística | pandas 2.2.3, NumPy 2.1.3 (la regresión logística, los errores robustos por clúster y el bootstrap están implementados con NumPy) |
| Frontend | React 18.3.1, Vite 5.4.21, TypeScript 5.7.3, Tailwind CSS 3.4.19, Recharts 3.10.1 |

## Estructura

```
hackathon-unam/
├── backend/
│   ├── main.py                # API FastAPI: /health y /api/...
│   ├── engine.py              # Motor: lee data/, procesa el tracking, ajusta el modelo, construye tablas en memoria
│   ├── exploracion.py         # Auditoría inicial de los datos
│   ├── analisis_matchups.py   # Viabilidad: enfrentamientos y métricas físicas
│   └── analisis_presion.py    # Regresión logística, bootstrap, validación y sensibilidad
├── dashboard/                 # React + Vite + Tailwind + Recharts
├── data/                      # Datasets (NO se versionan, ver abajo)
└── .hackathon/                # Herramientas del evento (setup, verificación, entrega)
```

## Datos (no se incluyen en el repositorio)

Los datasets ocupan alrededor de 825 MB y no se suben a GitHub (`data/` está en `.gitignore`). Para reproducir el proyecto:

1. Obtén el paquete de datos del evento, `nfl-big-data-bowl-regional-event-data-main`, que proporcionan los organizadores del hackathon. Tiene el mismo formato que los datos públicos del [NFL Big Data Bowl 2023 en Kaggle](https://www.kaggle.com/competitions/nfl-big-data-bowl-2023/data) (temporada 2021, semanas 1 a 8).
2. Descomprímelo dentro de `data/`. La aplicación busca `games.csv` en cualquier subcarpeta de `data/`, así que esta estructura funciona:

```
data/
└── nfl-big-data-bowl-regional-event-data-main/
    └── data/
        ├── games.csv
        ├── plays.csv
        ├── players.csv
        ├── pffScoutingData.csv
        └── tracking/
            ├── tracking_2021090900.csv
            └── ...  (122 archivos, uno por partido)
```

Los archivos son de solo lectura para el proyecto: nada se escribe en `data/`.

## Instalación y ejecución

Requisitos: Windows, macOS o Linux. El script del evento instala Python, uv y Node con las versiones fijas del stack.

```bash
# 1. Preparar el entorno (crea .venv e instala dependencias)
sh .hackathon/setup.sh          # Windows (PowerShell): .\.hackathon\setup.cmd

# 2. Verificar el entorno
sh .hackathon/setup.sh --check  # Windows: .\.hackathon\setup.cmd --check
```

Desarrollo, con el backend y el dashboard en terminales separadas:

```bash
# Backend en http://localhost:8000 (los datos se procesan al arrancar, unos 20-30 s)
.venv/bin/uvicorn backend.main:app --reload --port 8000
# Windows: .venv\Scripts\uvicorn backend.main:app --reload --port 8000

# Dashboard en http://localhost:5173 (Vite redirige /api al backend)
cd dashboard
npm run dev
```

Mientras se preparan los datos, `GET /health` responde de inmediato y `GET /api/estado` informa el progreso.

### Endpoints

| Ruta | Descripción |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `GET /api/estado` | Progreso de la preparación de datos |
| `GET /api/filtros` | Equipos, semanas, partidos y grupos de posición |
| `GET /api/resumen` | Centro de control: KPIs, comparación entre equipos, observaciones automáticas y hallazgo principal. Parámetros: `equipo`, `grupo`, `semana`, `partido`, `min_snaps` |
| `GET /api/jugadores` | Lista de jugadores con datos |
| `GET /api/jugador/{nflId}` | Perfil físico y de rendimiento con comparación por posición |
| `GET /api/laboratorio` | Resultados del laboratorio de explosividad (quintiles, deciles, curvas, efectos, robustez) |

### Reproducir los análisis estadísticos

```bash
.venv/bin/python backend/exploracion.py        > exploracion.txt
.venv/bin/python backend/analisis_matchups.py  > matchups.txt
.venv/bin/python backend/analisis_presion.py   > presion.txt
```

`analisis_presion.py` guarda una caché de la tabla rusher-jugada en el directorio temporal del sistema, no en el proyecto.

## Definiciones clave

- **Unidad de análisis:** rusher × jugada y bloqueador × jugada. Los frames del tracking nunca se tratan como observaciones independientes.
- **Presión:** hurry, hit o sack de PFF. En los datos son mutuamente excluyentes por jugador y jugada.
- **Tasa de presión:** jugadas con presión ÷ snaps con `pff_role = "Pass Rush"`.
- **Efectividad de bloqueo:** 1 − (bloqueos con presión permitida o `beatenByDefender`) ÷ snaps con `pff_role = "Pass Block"`.
- **Tasa esperada:** suma de las probabilidades del modelo logístico en las jugadas del jugador. Considera su burst, peso, grupo y el contexto de cada jugada.
- **Tasa ajustada:** shrinkage beta-binomial hacia la media del grupo, para no premiar muestras pequeñas.
- **EDGE:** DE y OLB. **IDL:** DT y NT. **OT:** tackles. **IOL:** guardias y centros.
