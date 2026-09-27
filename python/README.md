# Radio Timer — aplicación de escritorio (Python)

Temporizador de programación para emisoras de radio, escrito en Python con Tkinter.
No necesita navegador ni dependencias externas: solo Python 3.10 o superior (Tkinter viene incluido en el instalador oficial de Windows).

La especificación completa está en [../radio-timer.md](../radio-timer.md).

## Abrir

Doble clic en **Abrir Radio Timer.bat**, o desde una terminal:

```
cd python
python run.py
```

La ventana abre maximizada. Opciones:

```
python run.py --hora 10:54:50      # simula que el reloj arranca a esa hora (para probar la alerta)
python run.py --hora 10:59:55      # ver el cambio de hora y de programa
python run.py --compacto           # inicia en modo compacto
python run.py --pantalla-completa  # inicia en pantalla completa
python run.py --ventana            # abre sin maximizar
python run.py --prefs otro.json    # usa otro archivo de preferencias
```

## Atajos de teclado

| Tecla | Acción |
|---|---|
| F11 | Entrar o salir de pantalla completa |
| Escape | Cerrar configuración/historial y salir de pantalla completa |

## Cómo funciona

- El contador no se inicia ni decrementa a mano: cada sección tiene hora de inicio y fin calculadas desde la hora de inicio del programa, y el tiempo restante sale de compararlas con el reloj del sistema.
- Al llegar a 00:00 pasa sola a la siguiente sección. Las secciones **en cadena** suman al total; las **independientes** tienen su propio contador en el panel derecho, que solo avanza en su turno.
- El centro del anillo muestra el **tiempo en cadena**: al pasar de EN AIRE a CIERRE el número sigue corriendo, solo cambian el color y el nombre. Durante una sección independiente (CORTE Y PROMOCIONES) muestra el contador de esa sección. Lo que falta del bloque activo aparece en el panel "Bloque activo" y en "Resta del bloque".
- En los últimos 10 segundos antes de que ese número llegue a 0 el reloj parpadea en rojo y el anillo brilla con un halo pulsante (se puede apagar en Configuración).
- En cada hora en punto la secuencia vuelve a empezar sola desde la primera sección (como el `timecon.exe` original). Por eso las secciones por defecto suman 60 minutos (EN AIRE 50 + CIERRE 5 en cadena, CORTE Y PROMOCIONES 5); si suman más, Configuración avisa qué secciones no alcanzan a salir.
- **Programas por hora:** cada día de la semana tiene su parrilla (rangos horarios con un título). El título del programa en curso aparece sobre el reloj y el siguiente en el panel izquierdo. Se carga en Configuración → Programas por hora; "Copiar este día a" copia la parrilla a otros días.
- **Sincronizar desde la web:** el botón de Configuración → Programas por hora descarga la programación semanal de `https://radioluz937fm.com/weekSchedule` y reemplaza la parrilla (necesita Internet; si falla, la parrilla no se toca).
- La hora de inicio se ajusta en Configuración y vale hasta la próxima hora en punto; el botón **Reiniciar al inicio** reprograma toda la secuencia desde esa hora.
- El historial registra entradas a bloque, reinicios, pánico y cambios de configuración, y se exporta a CSV compatible con Excel.
- Si hay más secciones de las que caben, los paneles muestran una barra de desplazamiento y responden a la rueda del ratón.

## Actualizaciones

En Configuración → **Versiones y actualizaciones** se elige la cadencia de comprobación (manual,
diaria o semanal) y la fuente: una URL https o carpeta (red o USB) con `updates.json` y el ZIP de cada
versión. La lista muestra todas las versiones con sus notas (nuevo / arreglado / cambiado) y
cualquiera se puede instalar sin reinstalar la app; lo anterior queda respaldado en
`%APPDATA%\RadioTimer\backups\` y el cambio se aplica al reiniciar. Para publicar versiones:

```
python tools/make_release.py --out "D:/actualizaciones" --titulo "..." --nuevo "..." --arreglado "..."
```

El detalle del diseño (reutilizable en otros proyectos) está en
[../gestor-de-versiones.md](../gestor-de-versiones.md).

## Preferencias

Emisora, secciones, parrilla de programas e interruptores se guardan en `%APPDATA%\RadioTimer\prefs.json` (en Linux/macOS, `~/.config/RadioTimer/prefs.json`).
La hora de inicio vuelve a la hora en punto actual cada vez que se abre la aplicación.

## Pruebas

```
cd python
python -m unittest discover -s tests -t . -v
```

Las pruebas de interfaz (`test_app_smoke.py`) necesitan un entorno con pantalla; se omiten automáticamente si Tk no puede abrir una ventana.

## Estructura

```
Abrir Radio Timer.bat  lanzador con doble clic
run.py                 arranque desde la terminal
radio_timer/
  model.py             lógica pura: secciones, parrilla de programas, formato
  layout.py            tamaños del reloj, la fecha y los paneles
  storage.py           preferencias en JSON
  schedule_sync.py     descarga de la programación semanal desde la web
  updates.py           gestor de versiones (manifiesto, descarga, instalación)
tools/make_release.py  publica una versión (ZIP + updates.json)
  activity_log.py      historial y exportación CSV
  theme.py             colores y fuentes
  widgets.py           botones, campos, interruptores y áreas con desplazamiento
  app.py               ventana principal (reloj, paneles, modos)
  dialogs.py           ventanas de configuración e historial
  __main__.py          línea de comandos
tests/                 pruebas de lógica, tamaños e interfaz
```
