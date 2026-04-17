# energy-uy

**Pipeline de datos del sistema eléctrico uruguayo**
Herramienta para obtener datos públicos de ADME y UTE, analizarlos y producir visualizaciones interactivas y contenido para LinkedIn.

---

## Estado del proyecto — última sesión (15/04/2026)

> **Leé esto si retomás el proyecto luego de una pausa.**

### Qué está hecho

| Módulo | Estado |
|---|---|
| Conectores ADME (SCADA, precio spot, generación mensual) | Implementado |
| Conector UTE Bajadas | Implementado (deshabilitado por defecto) |
| Limpieza y procesamiento de datos | Implementado |
| Almacenamiento SQLite con upsert | Implementado |
| Análisis de indicadores | Implementado |
| Gráficos interactivos (Plotly, paleta AIC) | Implementado |
| Generación editorial y copy LinkedIn | Implementado |
| **Dashboard Streamlit** (interfaz visual completa) | **Implementado** |

### Cómo levantarlo

```bash
cd "ruta/a/energy-uy"
python -m streamlit run app.py
```

Abre el browser en `http://localhost:8501`. Seleccioná mes/año en el panel izquierdo y hacé clic en **Ejecutar pipeline**.

---

## ¿Para qué sirve esto?

Esta herramienta hace lo siguiente de forma automática:

1. **Descarga datos** del sistema eléctrico de Uruguay desde fuentes públicas (ADME y UTE)
2. **Los limpia y organiza** en una base de datos local SQLite
3. **Genera 4 gráficos interactivos** con paleta de colores AIC Economía & Finanzas
4. **Escribe un borrador** de post de LinkedIn con hallazgos clave del período

Todo desde un dashboard visual local que no requiere conexión a servidores externos.

---

## Antes de empezar — Paso de validación (solo UTE Bajadas)

> **Este paso solo es necesario si querés activar el conector UTE Bajadas.** Los conectores ADME funcionan directamente sin validación manual.

El conector de UTE Bajadas usa un formulario ASP.NET cuyos campos deben confirmarse con DevTools:

1. Entrá a [apps.ute.com.uy/SgePublico/Bajadas.aspx](https://apps.ute.com.uy/SgePublico/Bajadas.aspx)
2. Abrí DevTools (`F12`) → pestaña **Network**
3. Hacé una descarga de prueba y copiá los nombres de los campos del **Form Data**
4. Actualizá el `payload` en [src/connectors/ute_bajadas.py](src/connectors/ute_bajadas.py)

Para habilitarla, cambiá `UTE_BAJADAS_ENABLED=false` a `true` en `.env`.

---

## Índice

1. [Requisitos previos](#1-requisitos-previos)
2. [Instalación](#2-instalación)
3. [Configuración inicial](#3-configuración-inicial)
4. [Dashboard visual](#4-dashboard-visual)
5. [Uso por línea de comandos](#5-uso-por-línea-de-comandos)
6. [Qué produce](#6-qué-produce)
7. [Estructura de archivos](#7-estructura-de-archivos)
8. [Cómo funciona por dentro](#8-cómo-funciona-por-dentro)
9. [Fuentes de datos](#9-fuentes-de-datos)
10. [Solución de problemas](#10-solución-de-problemas)
11. [Glosario](#11-glosario)

---

## 1. Requisitos previos

### Python 3.11 o superior

```bash
python --version
```

Si no está instalado, descargalo desde [python.org](https://www.python.org/downloads/).

### uv (gestor de entornos)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## 2. Instalación

```bash
# 1. Crear entorno virtual
uv venv

# 2. Activar (Windows)
.venv\Scripts\activate

# 2. Activar (Mac/Linux)
source .venv/bin/activate

# 3. Instalar dependencias
uv pip install -e ".[dev]"

# 4. Verificar
python -m pytest tests/ -v
```

Si ves `PASSED` en los tests, todo está correctamente instalado.

---

## 3. Configuración inicial

```bash
cp .env.example .env
```

El `.env` ya viene preconfigurado. Variables principales:

```
DB_PATH=data/db/energy_uy.sqlite
OUTPUT_DIR=outputs
LOG_LEVEL=INFO
ADME_BASE_URL=https://adme.com.uy
UTE_BASE_URL=https://apps.ute.com.uy
HTTP_TIMEOUT=30
```

---

## 4. Dashboard visual

La forma principal de usar el proyecto es a través del dashboard Streamlit:

```bash
python -m streamlit run app.py
```

### Qué muestra el dashboard

**Sidebar (panel izquierdo)**
- Selector de mes y año de análisis
- Checkbox "Usar datos ya descargados" (omite la descarga)
- Botón **Ejecutar pipeline** con barra de progreso
- Indicador de última ejecución

**Cabecera**
- Título con gradiente navy AIC + badge del período analizado

**KPI cards (4 métricas)**
- Generación Renovable (% del total)
- Fuente Líder (fuente con mayor participación)
- Precio Spot Promedio (USD/MWh)
- Período analizado

**Tab "Generación" — 4 gráficos interactivos (Plotly)**
- Donut de composición de la matriz
- Área apilada del mix diario
- Barras renovable vs. no renovable
- Comparativa interanual

Todos los gráficos tienen hover con tooltips, zoom con scroll y leyenda clickeable para ocultar/mostrar fuentes.

**Tab "LinkedIn"**
- Borrador del post editable directamente
- Bullets de respaldo con datos numéricos

### Paleta de colores AIC en los gráficos

| Fuente | Color | Código |
|---|---|---|
| Hidráulica | Verde AIC | `#27AE60` |
| Eólica | Navy AIC | `#1D3461` |
| Solar | Ámbar | `#F0A500` |
| Biomasa | Verde oscuro | `#1E8449` |
| Térmica | Slate gris-azul | `#8896B0` |
| Importación | Navy medio | `#3A5A96` |

---

## 5. Uso por línea de comandos

Si preferís usar la herramienta sin el dashboard:

```bash
# Período específico
python scripts/run_pipeline.py --date-from 2024-01-01 --date-to 2024-01-31

# Usar datos ya descargados (no conecta a internet)
python scripts/run_pipeline.py --date-from 2024-01-01 --date-to 2024-01-31 --skip-fetch

# Solo una fuente
python scripts/run_pipeline.py --source adme_scada

# Carpeta de salida personalizada
python scripts/run_pipeline.py --date-from 2024-01-01 --date-to 2024-01-31 --output-dir ~/Desktop/enero-2024
```

### Referencia de parámetros

| Parámetro | Descripción | Ejemplo |
|---|---|---|
| `--date-from` | Fecha de inicio | `--date-from 2024-01-01` |
| `--date-to` | Fecha de fin | `--date-to 2024-01-31` |
| `--source` | Fuente a descargar | `--source adme_scada` |
| `--skip-fetch` | Usar datos de la DB local | `--skip-fetch` |
| `--output-dir` | Carpeta de destino | `--output-dir ~/Desktop/output` |

---

## 6. Qué produce

### Dashboard (uso interactivo)
Todo se muestra en el browser en tiempo real. El borrador de LinkedIn se puede editar directamente en la interfaz.

### Archivos exportados (uso por CLI)

**Gráficos** (`outputs/charts/`)

| Archivo | Descripción |
|---|---|
| `mix_generacion_area` | Área apilada del mix diario |
| `mix_generacion_donut` | Donut de participación por fuente |
| `renovables_barras` | Barras renovable vs. no renovable |
| `comparativa_interanual` | Comparación con el año anterior |

Dos versiones por gráfico: `_hires.png` (300 dpi) y `_web.png` (150 dpi).

**Reporte editorial** (`outputs/reports/reporte_linkedin.txt`)
- Título sugerido para LinkedIn
- 3–5 bullets con hallazgos clave
- Párrafo de contexto e interpretación
- Copy completo listo para publicar

**Base de datos** (`data/db/energy_uy.sqlite`)
- Histórico acumulativo de todos los períodos analizados

---

## 7. Estructura de archivos

```
energy-uy/
│
├── app.py                        ← Dashboard Streamlit (punto de entrada principal)
│
├── src/
│   ├── dashboard/                ← Componentes de la interfaz visual
│   │   ├── styles.py             ← CSS e identidad visual AIC
│   │   ├── pipeline_runner.py    ← Orquestador para el dashboard
│   │   └── components/
│   │       ├── kpi_cards.py      ← Tarjetas de métricas
│   │       ├── charts_tab.py     ← Tab de gráficos interactivos
│   │       └── linkedin_panel.py ← Tab de copy LinkedIn
│   │
│   ├── connectors/               ← Descarga de datos (ADME, UTE)
│   ├── processing/               ← Limpieza y transformación
│   ├── storage/                  ← Base de datos SQLite
│   ├── analysis/                 ← Cálculo de indicadores
│   ├── visualization/
│   │   ├── charts.py             ← Gráficos Plotly con paleta AIC
│   │   └── style.py              ← Definiciones de estilo
│   └── editorial/                ← Generación de contenido LinkedIn
│
├── scripts/
│   └── run_pipeline.py           ← CLI alternativo al dashboard
│
├── tests/                        ← Tests automáticos
├── data/db/energy_uy.sqlite      ← Base de datos histórica
├── outputs/                      ← Gráficos y reportes exportados
├── .streamlit/config.toml        ← Tema Streamlit (colores AIC)
├── config.py                     ← Configuración del proyecto
├── .env                          ← Variables de entorno
└── pyproject.toml                ← Dependencias
```

---

## 8. Cómo funciona por dentro

Cuando ejecutás el pipeline (desde el dashboard o la CLI), el sistema hace 6 pasos:

**A — Adquisición**
Se conecta a ADME y UTE y descarga los datos del período. Si una fuente falla, registra el error y continúa con las demás.

**B — Limpieza**
Normaliza fechas, traduce nombres de fuentes al vocabulario interno (`"Eólica"` → `"wind"`), elimina duplicados y clasifica fuentes como renovable/no renovable.

**C — Almacenamiento**
Guarda los datos en SQLite con estrategia upsert (no duplica datos si ya existen).

**D — Análisis**
Calcula mix de generación, participación renovable, fuente líder, precio promedio y comparación interanual.

**E — Visualización**
Genera los 4 gráficos Plotly con paleta AIC.

**F — Editorial**
Convierte los indicadores en texto: bullets de hallazgos, frase de contexto y copy completo para LinkedIn.

```
ADME ──────┐
           ├──► A. Descarga ──► B. Limpieza ──► C. Base de datos
UTE ───────┘                                          │
                                                      ▼
                                              D. Análisis ──► E. Gráficos
                                                          └──► F. Copy LinkedIn
```

---

## 9. Fuentes de datos

### ADME — Administración del Mercado Eléctrico
- **Datos abiertos**: [adme.com.uy/datosabiertos.html](https://adme.com.uy/datosabiertos.html)
- Generación horaria por parque y planta, intercambios con Argentina y Brasil
- Formato ODS/XLSX
- Sustento legal: Ley 19.355, Decreto 54/2017

### UTE — Usinas y Transmisiones Eléctricas
- **Portal**: [apps.ute.com.uy/SgePublico/Bajadas.aspx](https://apps.ute.com.uy/SgePublico/Bajadas.aspx)
- Series históricas diarias de producción, demanda e intercambios
- Formato XLSX — deshabilitado por defecto (requiere validación de formulario)

### MIEM — Ministerio de Industria, Energía y Minería
- **Series estadísticas**: [miem.gub.uy](https://www.miem.gub.uy/energia/series-estadisticas-de-energia-electrica)
- **Balance Energético**: [ben.miem.gub.uy](https://ben.miem.gub.uy) — 59 años de historia energética

---

## 10. Solución de problemas

### "streamlit no se reconoce"
```bash
python -m streamlit run app.py
```

### "No module named X"
```bash
.venv\Scripts\activate        # Windows
uv pip install -e ".[dev]"
```

### "No hay datos para el período"
1. Revisá los mensajes de error en la consola
2. Verificá que el período tenga datos disponibles en ADME
3. Corré sin "Usar datos ya descargados"

### "La página devuelve HTML en lugar del archivo"
La estructura del formulario de ADME o UTE cambió. Revisá la página manualmente con DevTools para identificar el cambio en los parámetros.

### Ver historial de descargas

```bash
python -c "
import sys; sys.path.insert(0, '.')
import config
from sqlalchemy import text
from src.storage.database import get_engine
engine = get_engine(config.DB_PATH)
with engine.connect() as conn:
    rows = conn.execute(text('SELECT run_at, source_name, status, records_inserted FROM ingestion_log ORDER BY run_at DESC LIMIT 10')).fetchall()
    for r in rows: print(r)
"
```

---

## 11. Glosario

| Término | Significado |
|---|---|
| **MW** | Megawatt — unidad de potencia en un instante dado |
| **MWh** | Megawatt-hora — energía acumulada en el tiempo |
| **GWh** | Gigawatt-hora — 1.000 MWh, usado para totales mensuales |
| **Mix de generación** | Porcentaje que aportó cada fuente en el período |
| **Fuentes renovables** | Eólica, solar, hidráulica y biomasa |
| **Fuentes no renovables** | Generación térmica (gas, fuel oil) |
| **SCADA** | Sistema de supervisión que registra el sistema eléctrico en tiempo real |
| **Precio spot** | Precio del mercado mayorista de electricidad hora a hora |
| **ADME** | Administración del Mercado Eléctrico de Uruguay |
| **UTE** | Administración Nacional de Usinas y Transmisiones Eléctricas |
| **Pipeline** | Cadena automatizada: descargar → limpiar → guardar → analizar → graficar → reportar |
| **Upsert** | Insertar un dato si no existe; ignorarlo si ya estaba (evita duplicados) |
| **SQLite** | Base de datos guardada en un único archivo, sin servidor |
| **DataFrame** | Tabla de datos en memoria (como Excel, pero en Python) |
| **Streamlit** | Framework de Python para crear dashboards web locales |
| **Plotly** | Librería de gráficos interactivos (hover, zoom, leyenda clickeable) |

---

## Créditos

Los datos son de acceso público, publicados por ADME y UTE en cumplimiento de la normativa de datos abiertos (Ley 19.355, Decreto 54/2017).

Este proyecto es una herramienta independiente de análisis y no tiene afiliación oficial con ADME, UTE ni el MIEM.

Desarrollado para **AIC Economía & Finanzas**.
