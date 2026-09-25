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
- En los últimos 10 segundos el reloj parpadea en rojo y el anillo brilla con un halo pulsante (se puede apagar en Configuración).
- La hora de inicio se ajusta en Configuración; el botón **Reiniciar al inicio** reprograma toda la secuencia desde esa hora.
- El historial registra entradas a bloque, reinicios, pánico y cambios de configuración, y se exporta a CSV compatible con Excel.
- Si hay más secciones de las que caben, los paneles muestran una barra de desplazamiento y responden a la rueda del ratón.

## Preferencias

Emisora, secciones e interruptores se guardan en `%APPDATA%\RadioTimer\prefs.json` (en Linux/macOS, `~/.config/RadioTimer/prefs.json`).
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
  model.py             lógica pura: secciones, programación, formato
  layout.py            tamaños del reloj, la fecha y los paneles
  storage.py           preferencias en JSON
  activity_log.py      historial y exportación CSV
  theme.py             colores y fuentes
  widgets.py           botones, campos, interruptores y áreas con desplazamiento
  app.py               ventana principal (reloj, paneles, modos)
  dialogs.py           ventanas de configuración e historial
  __main__.py          línea de comandos
tests/                 pruebas de lógica, tamaños e interfaz
```
