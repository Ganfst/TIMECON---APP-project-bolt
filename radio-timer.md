# Radio Timer — Temporizador de Programación para Emisoras

Aplicación de escritorio en Python que muestra una cuenta regresiva de los bloques de programación de una emisora de radio, sujeta al reloj real (no es un timer manual). Diseñada para ser leída a distancia por operadores y conductores, mayormente adultos.

**Cómo abrirla:** doble clic en `python/Abrir Radio Timer.bat`, o desde una terminal `cd python` y `python run.py`. Ver [python/README.md](python/README.md).

---

## Concepto principal

El contador **no se inicia manualmente ni decrementa por sí solo**: calcula el tiempo restante comparando la hora actual del sistema con la hora de inicio y fin de cada sección programada.

**Ejemplo:** una programación "EN AIRE" comienza a las 7:00 en punto y dura 45 minutos → el reloj muestra `45:00` y baja (`44:59`, `44:58`...) conforme avanza la hora real. Al llegar a `00:00`, pasa automáticamente a la siguiente sección (p. ej. PROMOS de 5 min) sin intervención del operador.

**Cada hora vuelve a empezar**, como en el `timecon.exe` original de cabina: a las 8:00 en punto la secuencia arranca de nuevo desde EN AIRE, sin tocar nada.

## Funcionalidades

### Reloj central
- Anillo de progreso que cambia de color según el bloque activo.
- Minutos y segundos restantes en tipografía grande (64–110 px, hasta 160 px en pantalla completa). El tamaño se ajusta para que los dígitos nunca se salgan del anillo.
- **Alerta de últimos 10 segundos:** el reloj parpadea en rojo, el anillo brilla con un halo que pulsa y el texto alterna entre blanco y rojo cada medio segundo hasta llegar a 0, para llamar la atención del conductor. Se puede desactivar en Configuración.

### Programas por hora (parrilla semanal)
- Cada día de la semana tiene su propia parrilla de programas, cargada **por rangos de horas en punto** (ej.: lunes 06:00–10:00 "Buenos Días Luz", 10:00–11:00 "Palabra de Vida"). Títulos de hasta 40 caracteres.
- El título del programa en curso aparece en grande sobre el reloj, con su horario, en todos los modos (también en compacto y pantalla completa), y en el título de la ventana. Se achica para caber en una línea.
- Las horas sin programa muestran "Sin programa asignado". Si la parrilla está vacía, no se muestra nada y la pantalla queda como antes.
- El panel izquierdo muestra el **programa siguiente** (hoy, mañana o el día que corresponda).
- En Configuración: botones por día (Lun…Dom), lista de programas del día con "Eliminar", campos Desde/Hasta/Título, aviso si un programa se cruza con otro, y "Copiar este día a" (lunes a viernes, todos los días o un día concreto; pide confirmación si reemplaza programas).
- Un programa que pasa la medianoche se carga en dos partes (22–24 un día y 00–02 el siguiente).
- Cada cambio de programa queda en el historial.

### Secciones de programación
- Cuatro bloques por hora de referencia: **EN AIRE (45 min), PROMOS (5), CIERRE (5), CORTE (5)**, que llenan la hora justa.
- **Reinicio automático en cada hora en punto:** la secuencia vuelve a empezar desde la primera sección. Si las secciones suman más de 60 minutos, las últimas no alcanzan a salir; Configuración lo avisa.
- Dos tipos de sección:
  - **En cadena:** se suman al total de la programación y se enlazan automáticamente. Al consumirse el tiempo de una, arranca la siguiente de inmediato, sin modificar el tiempo; solo cambia el color y el nombre del panel informativo inferior.
  - **Independiente:** no se suma al total; aparece en el panel derecho con su propio contador, que muestra su duración mientras espera y solo avanza cuando le toca su turno en la secuencia.
- Cada sección muestra su etiqueta "EN CADENA" o "INDEPENDIENTE".
- "Cadena total" muestra lo que falta de las secciones en cadena: el resto del bloque activo más la duración completa de las pendientes.
- Desde configuración se pueden agregar secciones (nombre de hasta 24 caracteres, duración, tipo), cambiar los minutos de cada una sin moverla de lugar y eliminar las que no se necesiten.

### Paneles
- **Panel izquierdo:** línea de tiempo de los bloques con el activo resaltado, aviso del próximo cambio (en la última sección: la primera de la nueva hora) y programa siguiente.
- **Panel derecho:** monitor de audio con animación de ondas, reloj principal (hora local) y secundario (UTC), contadores de secciones independientes.
- **Barra superior:** nombre de emisora, estado de señal, y botones de modo compacto, pantalla completa, modo pánico, historial y configuración.
- **Barra inferior:** indicador "EN AIRE" con el nombre de la emisora.
- Los paneles laterales muestran una barra de desplazamiento cuando hay más secciones de las que caben; nada se corta.

### Modos
- **Pantalla completa:** pantalla completa nativa de la ventana (botón o F11; Esc para salir). Oculta todos los paneles (barra superior, programación, temporizadores laterales, controles) y deja solo el reloj central con fecha/hora y la barra inferior "EN AIRE", que recuerda cómo salir.
- **Modo compacto:** oculta los paneles laterales y deja solo el reloj central, más grande; ideal para monitores pequeños.
- **Modo pánico:** activa un banner rojo parpadeante para alertar al operador.

### Fecha y hora
- Bloque dedicado con día de la semana, fecha (día y mes) y hora en texto grande.
- Tamaños: día/fecha 20–32 px, hora 40–68 px (más grandes en pantalla completa). Crecen con la ventana y se reducen en ventanas pequeñas sin cortarse ni sobreponerse a otros elementos.

### Configuración
- Ajuste de hora y minuto de inicio de la secuencia; vale hasta la siguiente hora en punto, cuando vuelve el reinicio automático.
- Botón **"Reiniciar al inicio"** para reprogramar toda la secuencia desde esa hora (único control manual).
- Nombre de emisora editable (hasta 40 caracteres) e interruptores de **alerta de cambio** (parpadeo) y **sonido de señal** (tono breve al cambiar de bloque).
- Panel de historial con registro real de actividad (entradas a bloque, reinicios, pánico, cambios de configuración) y exportación a CSV compatible con Excel.
- Emisora, secciones, parrilla de programas e interruptores se guardan en `%APPDATA%\RadioTimer\prefs.json`; la hora de inicio vuelve a la hora en punto actual en cada apertura.

### Tamaño de ventana
- La aplicación abre maximizada.
- Ventanas medianas (menos de 1180 px de ancho): se oculta el panel derecho.
- Ventanas angostas (menos de 820 px): el reloj queda arriba, la programación se apila debajo y los botones de la barra superior pasan a una segunda fila.
- Si el contenido no cabe en alto, el área central se desplaza con la rueda del ratón.
- En pantallas con escala de Windows (125 %, 150 %...) todos los tamaños se ajustan en proporción.

---

## Historial de versiones

| Versión | Fecha | Cambios |
|---|---|---|
| 1 | Sep 14, 9:33 AM | Interfaz inicial del timer de radio inspirada en la imagen de referencia. Reloj con anillo de progreso, bloques de programación, paneles laterales, modos pánico/compacto/pantalla completa. |
| 2 | Sep 14, 9:47 AM | Pantalla completa oculta todos los paneles. Fecha/hora más grandes y responsive. Primeras secciones continuas e independientes. |
| 3 | Sep 14, 9:52 AM | Timer corre solo sin botón de iniciar; encadenamiento automático de secciones. Todos los textos agrandados para lectura por adultos a distancia. |
| 4 | Sep 14, 10:16 AM | Contador atado al reloj real (calculado desde hora de inicio/fin, no decremento manual). Alerta parpadeante en los últimos 10 segundos. Configuración de hora de inicio. |
| 5 | Sep 14, 10:55 AM | Verificación y cierre de la versión web: monitor de audio, reloj principal y secundario, historial con CSV, interruptores funcionales, emisora editable, preferencias persistentes. |
| 6 | Sep 17 | Transcripción completa a Python/Tkinter (sin TypeScript ni navegador), con la lógica separada de la interfaz y pruebas automáticas. |
| 7 | Sep 25 | Revisión contra este documento y eliminación de la versión web (HTML, TypeScript, Node). Textos al tamaño de lectura a distancia; reloj 64–110 px y 160 px en pantalla completa; fecha/hora dentro de 20–32 y 40–68 px. Halo pulsante en la alerta. Interruptores reales. Desplazamiento en paneles y área central para que nada se corte. Apilado en ventanas angostas y ventana maximizada al abrir. Corregido: "Cadena total" sumaba tiempo de espera y los contadores independientes bajaban antes de su turno. Corregido: el texto de ayuda del campo de nombre se agregaba como sección. Nombres con largo máximo. Lanzador con doble clic. 49 pruebas automáticas. |
| 8 | Sep 26 | Revisión de `ref/timecon.exe` (timer original por minuto de la hora, se repite cada hora). Parrilla semanal: título del programa de cada hora sobre el reloj, distinto para cada día, cargado por rangos, con copia entre días y programa siguiente. La secuencia se reinicia sola en cada hora en punto. Bloques por defecto de 45/5/5/5 min para llenar la hora; minutos editables por sección y aviso si la secuencia pasa de 60 min. 64 pruebas automáticas. |

## Stack técnico

- Python 3.10 o superior con Tkinter (incluido en el instalador de Python; sin dependencias externas).
- Reloj y anillo dibujados en un lienzo (Canvas); se actualiza 10 veces por segundo con un costo menor a 1 ms por actualización.
- Preferencias en JSON, historial exportable a CSV, tono de señal con `winsound` en Windows.

## Archivos principales

Todo el código está en `python/`:

- `Abrir Radio Timer.bat` — lanzador con doble clic, sin consola
- `run.py` — arranque desde la terminal
- `radio_timer/model.py` — lógica pura: secciones, parrilla de programas, tiempo restante, formato
- `radio_timer/layout.py` — tamaños del reloj, la fecha y los paneles según este documento
- `radio_timer/app.py` — ventana principal: reloj, paneles, modos
- `radio_timer/dialogs.py` — ventanas de configuración e historial
- `radio_timer/widgets.py` — botones, campos, interruptores y áreas con desplazamiento
- `radio_timer/storage.py`, `radio_timer/activity_log.py` — preferencias (con la parrilla) e historial CSV
- `tests/` — pruebas de la lógica, de los tamaños y de la interfaz

## Comandos

Desde la carpeta `python`:

```
python run.py                      # abrir la aplicación
python run.py --hora 10:44:50      # simular la hora (probar la alerta de 10 s)
python run.py --hora 10:59:55      # ver el cambio de hora y de programa
python run.py --compacto           # abrir en modo compacto
python run.py --pantalla-completa  # abrir en pantalla completa
python run.py --ventana            # abrir sin maximizar
python -m unittest discover -s tests -t .   # pruebas
```
