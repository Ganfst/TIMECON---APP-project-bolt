# Timecon App — Radio Timer Pro

Temporizador de bloques para cabina de radio (Control Master). Es una ventana flotante, sin bordes y siempre visible, que indica en qué bloque de la hora se está (programa, promos, cierre, corte comercial), cuánto falta para el siguiente cambio, la fecha y dos relojes con zonas horarias distintas.

Está escrito en Python con Tkinter y se distribuye como un ejecutable de Windows generado con PyInstaller.

---

## Características

- **Ventana flotante "always on top"** sin barra de título. Se mueve arrastrándola y se redimensiona desde la esquina inferior derecha (icono `⇲`).
- **Bloques por minuto de la hora.** Cada bloque tiene minuto de inicio, minuto de fin, color de fondo, color de texto y nombre. El fondo de toda la ventana cambia al color del bloque activo.
- **Programación por hora del día.** Cada hora (00 a 23) puede tener su propio horario de bloques. Las horas sin programación propia usan el horario "Por Defecto". Esto permite mezclar horas con estructura clásica de 55 minutos y horas con programas cortos.
- **Huecos permitidos.** No es obligatorio cubrir los 60 minutos. Los minutos sin bloque se muestran como `SIN PROGRAMACIÓN` hasta el siguiente bloque definido.
- **Alerta de parpadeo** configurable N segundos antes de cada cambio de bloque (fondo ámbar, texto negro).
- **Modo Pánico** (tecla `P`): resalta la ventana en rojo un instante para llamar la atención del operador.
- **Modo compacto**: oculta todo menos el temporizador central.
- **Pantalla completa multi-monitor**: detecta el monitor físico o virtual (por ejemplo SpaceDesk) donde está la ventana y la expande a ese monitor exacto usando la API de Windows (`EnumDisplayMonitors`).
- **Relojes duales**: hora local de la zona principal y hora de una zona secundaria (UTC, GMT u otra ciudad).
- **Historial en CSV** de cada entrada a un bloque, con visor integrado y opción de purgar.
- **Configuración persistente en JSON**, editable desde un panel visual con selector de zonas horarias con autocompletado y selector de color (doble clic en el campo de color).

---

## Requisitos

- Windows 10/11 (la detección de monitores y la transparencia de ventana usan APIs de Windows).
- Python 3.13 (el entorno virtual del proyecto usa 3.13.13).
- Dependencias:
  - `pytz` — zonas horarias.
  - `pyinstaller` — solo para generar el ejecutable.
  - `screeninfo` — opcional. Se usa como respaldo si la API de Windows no devuelve monitores.

Tkinter viene incluido con la instalación estándar de Python.

---

## Ejecutar desde el código fuente

```powershell
# Crear y activar el entorno virtual (solo la primera vez)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Instalar dependencias
pip install pytz pyinstaller

# Ejecutar la app
python main.py
```

---

## Generar el ejecutable

El proyecto incluye `main.spec`, ya configurado para un ejecutable de un solo archivo, sin consola, comprimido con UPX y con el icono `wolp.ico`.

```powershell
pyinstaller main.spec
```

El resultado queda en `dist/main.exe`. Los archivos intermedios se generan en `build/`.

Si se prefiere sin el archivo `.spec`:

```powershell
pyinstaller --onefile --noconsole --icon=wolp.ico main.py
```

---

## Uso

### Atajos de teclado

Los atajos funcionan cuando la ventana del temporizador tiene el foco.

| Tecla | Acción |
|-------|--------|
| `S` | Abrir / cerrar el panel de configuración |
| `M` | Alternar modo compacto / expandido |
| `F` | Alternar pantalla completa en el monitor actual |
| `P` | Modo Pánico (resaltar en rojo) |
| `L` | Abrir el visor de historial (logs) |
| `Q` | Guardar posición, tamaño y configuración, y cerrar |

### Botones de la barra superior

A la izquierda aparece el nombre de la emisora y, en el lado derecho, los controles:

| Icono | Acción |
|-------|--------|
| `⊡` / `⊞` | Modo compacto / expandido |
| `⛶` | Pantalla completa |
| `⚠` | Modo Pánico |
| `☰` | Historial |
| `⚙` | Configuración |
| `×` | Cerrar de forma segura |

### Panel de configuración

Se abre con `S` o el botón `⚙`. Tiene tres secciones:

1. **Configuración general**: nombre de la emisora, zona horaria principal y secundaria (con autocompletado), opacidad, parpadeo de alerta y segundos de anticipación, activar o desactivar el log.
2. **Dimensiones por defecto**: ancho de ventana, alto en modo expandido y alto en modo compacto.
3. **Programación horaria**: un desplegable permite elegir "Por Defecto (Todas las Horas)" o una hora concreta (`00:00` a `23:00`). Para cada una se editan filas de bloques (minuto inicio, minuto fin, color fondo, color texto, nombre). Botones disponibles:
   - **Copiar Por Defecto Aquí**: parte del horario por defecto para la hora seleccionada.
   - **Quitar Personalización de esta Hora**: la hora vuelve a usar el horario por defecto.
   - **+ Añadir Bloque / Programa a esta Hora**: agrega una fila nueva.
   - `×` al final de cada fila: elimina ese bloque.

Reglas de validación al guardar: los minutos deben estar entre 0 y 60, el inicio debe ser menor que el fin, y las zonas horarias deben ser válidas. Si dos bloques se solapan, gana el que tenga el menor minuto de inicio.

---

## Archivos de datos

Ambos se crean junto al script en la primera ejecución.

### `radio_timer_config.json`

Configuración completa de la app. Ejemplo resumido:

```json
{
  "station_name": "Radio Luz 93.7 fm - Timer",
  "timezone": "America/Santo_Domingo",
  "secondary_tz": "America/Santo_Domingo",
  "compact_height": 70,
  "expanded_height": 848,
  "window_width": 1381,
  "window_x": 349,
  "window_y": 98,
  "opacity": 0.95,
  "blink_enabled": true,
  "blink_seconds": 15,
  "log_enabled": true,
  "fullscreen": false,
  "schedules": {
    "default": [
      { "minute_start": 0,  "minute_end": 45, "color": "#1a7a3c", "fg": "#ffffff", "name": "EN AIRE / PROGRAMA" },
      { "minute_start": 45, "minute_end": 50, "color": "#d97706", "fg": "#ffffff", "name": "PROMO / AVANCES" },
      { "minute_start": 50, "minute_end": 55, "color": "#2563eb", "fg": "#ffffff", "name": "CIERRE DE BLOQUE" },
      { "minute_start": 55, "minute_end": 60, "color": "#dc2626", "fg": "#ffffff", "name": "CORTE COMERCIAL" }
    ],
    "14": [
      { "minute_start": 0,  "minute_end": 25, "color": "#1a7a3c", "fg": "#ffffff", "name": "PROGRAMA CORTO" },
      { "minute_start": 25, "minute_end": 30, "color": "#dc2626", "fg": "#ffffff", "name": "CORTE" }
    ]
  }
}
```

Las claves de `schedules` son `"default"` o el número de la hora como texto (`"0"` a `"23"`). Los archivos de configuración antiguos que usaban una lista plana `blocks` se migran automáticamente a `schedules.default` al cargar.

### `radio_timer_log.csv`

Una fila por cada cambio de bloque, con columnas `timestamp`, `evento` y `zona_horaria`:

```csv
timestamp,evento,zona_horaria
2026-07-13 10:05:07,Entrada a bloque: EN AIRE / PROGRAMA,America/Santo_Domingo
```

Se puede ver y purgar desde el visor de historial (`L`).

---

## Estructura del proyecto

```
Timecon App/
├── main.py                  # Versión actual: programación por hora + multi-monitor
├── main.spec                # Spec de PyInstaller para main.py (icono wolp.ico)
├── index.py                 # Versión anterior: una sola lista de bloques para todas las horas
├── index.spec               # Spec de PyInstaller para index.py (icono logo.ico)
├── backup.py                # Prototipo original con horario fijo (50 / 55 min)
├── radio_timer_config.json  # Configuración persistente
├── radio_timer_log.csv      # Historial de cambios de bloque
├── wolp.ico / logo.ico      # Iconos del ejecutable
├── timecon.exe              # Compilación anterior del ejecutable
├── dist/                    # Ejecutables generados (main.exe, index.exe)
├── build/                   # Archivos intermedios de PyInstaller
└── .venv/                   # Entorno virtual de Python
```

### Historial de versiones

| Archivo | Descripción |
|---------|-------------|
| `backup.py` | Prototipo. Tres estados fijos: EN AIRE (0–50), CIERRE DE BLOQUE (50–55), CORTE (55–60). Sin configuración ni log. |
| `index.py` | Bloques configurables desde un panel visual, log CSV, modo compacto, pantalla completa básica. Un solo horario para todas las horas. |
| `main.py` | Horario independiente por cada hora del día, huecos con `SIN PROGRAMACIÓN`, detección real de monitores con la API de Windows, selector de zonas horarias con autocompletado, panel de configuración con scroll y botones fijos. |

### Componentes principales de `main.py`

| Clase / función | Responsabilidad |
|-----------------|-----------------|
| `get_monitors`, `monitor_for_point` | Enumeran los monitores conectados y localizan en cuál está la ventana. |
| `BlockConfig` | Un bloque: nombre, minuto inicio, minuto fin, colores. |
| `AppConfig` | Toda la configuración. Carga, guarda y migra el JSON. |
| `BlockLogger` | Escribe en el CSV cuando cambia el bloque activo. |
| `WindowManager` | Arrastre y redimensionado de la ventana sin bordes. |
| `SettingsPanel` | Ventana de configuración con la edición de horarios por hora. |
| `LogViewer` | Visor y purga del historial. |
| `RadioTimer` | Aplicación principal: construye la interfaz, hace el tick cada segundo y coordina el resto. |

---

## Notas

- El panel de configuración intenta cargar `logo_radio.ico` como icono de ventana. El archivo no está en el proyecto, así que se omite silenciosamente.
- La configuración y el log se guardan en la carpeta donde está el script (`Path(__file__).parent`). Al empaquetar con PyInstaller en modo `--onefile`, esa ruta apunta a la carpeta temporal de extracción, por lo que la configuración podría no persistir entre ejecuciones del `.exe`. Si se observa ese comportamiento, conviene usar la carpeta de `sys.executable` cuando la app corre congelada (`getattr(sys, "frozen", False)`).
- La carpeta `Fluffy/` contiene archivos personales que no forman parte de la aplicación.
