# Gestor de versiones — especificación reutilizable

Qué debe tener un módulo de gestión de versiones para que una aplicación de escritorio se
actualice **sin reinstalarse**, el usuario pueda **elegir qué versión instalar** (incluida una
anterior) y cada versión llegue con **notas claras** de qué arregla y qué agrega.

Este documento es independiente de la aplicación: puede copiarse a otro proyecto y usarse como
lista de requisitos. Al final hay una sección corta con cómo está aplicado en Radio Timer.

---

## 1. Idea general

```
┌────────────────────┐        ┌─────────────────────────────┐
│  Fuente de         │        │  Aplicación instalada       │
│  actualizaciones   │  HTTP  │                             │
│                    │ ◄───── │  1. Comprueba el manifiesto │
│  updates.json      │  o     │  2. Compara versiones       │
│  app-1.0.0.zip     │ carpeta│  3. Descarga y verifica     │
│  app-1.1.0.zip     │  local │  4. Instala y respalda      │
│  app-2.0.0.zip     │        │  5. Reinicia                │
└────────────────────┘        └─────────────────────────────┘
```

- La **fuente** es cualquier lugar que sirva archivos: una web, una carpeta de red o una USB.
  No requiere servidor propio ni base de datos: basta un archivo índice (el **manifiesto**) y un
  paquete (ZIP) por versión.
- La app **nunca instala sola**: comprueba y avisa según la cadencia elegida; instalar y reiniciar
  son siempre acciones del usuario.
- Los **datos del usuario** (preferencias, historial) viven fuera de la carpeta del código
  (p. ej. `%APPDATA%\MiApp\`), así ninguna actualización los toca.

## 2. Requisitos del módulo

### 2.1 Identidad de versión
- Un único lugar declara la versión instalada (p. ej. `__version__ = "3.2.0"` en el paquete).
- Versionado semántico `MAYOR.MENOR.PARCHE` y un comparador numérico propio
  (`3.10.0 > 3.2.0`; compararlas como texto falla).
- El paquete de cada versión declara internamente su versión, y el instalador la coteja con la
  anunciada en el manifiesto: detecta paquetes subidos al lugar equivocado.

### 2.2 Manifiesto de versiones (`updates.json`)
Un JSON con la lista completa de versiones publicadas, de la más nueva a la más vieja:

```json
{
  "app": "mi-app",
  "releases": [
    {
      "version": "3.2.0",
      "date": "2026-09-26",
      "title": "Parrilla web y gestor de versiones",
      "notes": {
        "nuevo":     ["Sincronización de la programación desde la web"],
        "arreglado": ["El reloj ya no se reinicia entre secciones en cadena"],
        "cambiado":  ["Bloques por defecto de 50/5/5 minutos"],
        "seguridad": []
      },
      "file": "mi-app-3.2.0.zip",
      "sha256": "9f2c…64 caracteres…",
      "size": 91234
    }
  ]
}
```

| Campo | Obligatorio | Para qué |
|---|---|---|
| `version` | sí | comparar con la instalada y elegir cuál instalar |
| `date` | recomendado | ordenar y mostrar |
| `title` | recomendado | resumen de una línea |
| `notes` | recomendado | desglose por categoría: **nuevo** (funciones), **arreglado** (correcciones), **cambiado** (comportamiento), **seguridad** |
| `file` | sí | nombre del ZIP, relativo al manifiesto (o URL absoluta) |
| `sha256` | sí | verificar la descarga; sin hash válido la entrada se descarta |
| `size` | recomendado | segundo control de integridad y dato para la interfaz |

Reglas:
- **Historial completo**: se conservan todas las versiones, no solo la última; eso habilita elegir
  versión y volver a una anterior.
- **Tolerancia**: una entrada rota se ignora sin invalidar el resto del manifiesto.
- El lector nunca ejecuta nada que venga en el manifiesto: son solo datos.

### 2.3 Comprobación de actualizaciones
- **Cadencias**: `manual` (solo con el botón), `daily` y `weekly`. La elección se guarda en las
  preferencias del usuario.
- Se guarda la **fecha de la última comprobación**; "diaria" significa "al menos 24 h desde la
  última", no "a medianoche". Si la app queda abierta varios días, un temporizador interno
  (p. ej. cada 30 min) revisa si ya venció el plazo; también se revisa al abrir.
- La comprobación corre **en segundo plano** (hilo): la interfaz nunca se congela por la red.
- Al encontrar versión nueva: **aviso pasivo** (indicador en la ventana + entrada en el
  historial), nunca una instalación automática ni un diálogo que interrumpa la operación.
- Sin conexión o con la fuente caída: mensaje claro y no se toca nada; la fecha de última
  comprobación solo se actualiza cuando la comprobación funcionó.

### 2.4 Descarga
- Descargar a una carpeta propia (p. ej. `%APPDATA%\MiApp\updates\`), nunca sobre la app.
- Verificar **SHA-256** (y tamaño, si viene) antes de dar el paquete por bueno; si no coincide,
  se descarta con un error legible.
- Escritura atómica: primero archivo temporal, luego renombrar.
- Con fuente remota, **solo HTTPS** (rechazar `http://` y descargas redirigidas a él): el paquete
  es código que se ejecutará, y por un canal sin cifrar cualquiera en la red podría reemplazar
  manifiesto y ZIP juntos (el hash viaja por el mismo canal, no autentica). Quien quiera más
  garantía puede añadir una firma (p. ej. Ed25519 sobre el manifiesto) con la clave pública
  embebida en la app.
- **Tope de tamaño** al descargar (manifiesto y paquete): un servidor comprometido no debe poder
  agotar la memoria de la app con una respuesta gigante.

### 2.5 Instalación sin reinstalar
- El paquete es la **carpeta de la app en un ZIP**; instalar = reemplazar esos archivos.
- **Validar el ZIP** antes de tocar nada: que contenga la app (un archivo ancla conocido) y que
  ninguna ruta escape de la carpeta (`../`, rutas absolutas, unidades) — el clásico *zip slip*.
- **Extraer a una carpeta temporal** (staging) y recién entonces hacer el intercambio: nunca
  extraer directo sobre la app.
- **Respaldo**: lo que se va a reemplazar se mueve a `%APPDATA%\MiApp\backups\v<versión>\`
  antes del intercambio. Si algo falla a mitad, se restaura el respaldo (la app queda como estaba).
- **Reemplazo por entradas de primer nivel**: las carpetas se sustituyen completas, para que los
  módulos eliminados en la versión nueva no queden huérfanos; lo que el ZIP no trae
  (archivos del usuario junto a la app) no se toca.
- **Migración de datos**: al arrancar, la versión nueva debe tolerar preferencias escritas por la
  vieja (campos desconocidos se ignoran, faltantes toman su valor por defecto). Si el formato
  cambia de verdad, migrar al cargar, como parte del código de la app.
- **Reiniciar para terminar**: el proceso en ejecución sigue usando el código viejo cargado en
  memoria; el módulo ofrece "Reiniciar la aplicación" (lanza el proceso nuevo y cierra el actual).
  Hasta entonces, la interfaz recuerda que hay un reinicio pendiente.
- App congelada (PyInstaller y similares): el ejecutable en uso está bloqueado por Windows; ahí
  el intercambio lo hace el proceso nuevo o un pequeño lanzador (descargar → cerrar → reemplazar
  → abrir). Con una app que corre desde código fuente este problema no existe.

### 2.6 Elegir versión (instalar la que se quiera)
- La interfaz lista **todas** las versiones del manifiesto con sus notas, no solo la última.
- Cada una se puede instalar: actualizar, **reinstalar** la actual o **volver a una anterior**
  (con confirmación explícita al bajar de versión).
- La versión instalada y la pendiente de reinicio quedan marcadas en la lista.

### 2.7 Notas de versión
- Cada versión publica sus notas **por categoría**: qué hay de **nuevo**, qué quedó
  **arreglado**, qué **cambió** y avisos de **seguridad**; la interfaz las muestra con esa
  separación para que el operador decida si le conviene actualizar.
- Las notas se escriben al publicar (parámetros del script de publicación), no después.

### 2.8 Interfaz mínima
- Versión instalada visible.
- Selector de cadencia (manual / diaria / semanal) y campo de fuente.
- Botón "Comprobar ahora" + línea de estado (comprobando, al día, nueva versión, error en rojo).
- Lista de versiones con notas y botón de instalar por versión; botón de reiniciar cuando hay
  una instalación pendiente.
- Indicador pasivo en la ventana principal cuando hay versión nueva o reinicio pendiente.
- Todo lo que descarga o instala muestra estado y desactiva los botones mientras trabaja.

### 2.9 Publicación (el otro lado)
Un script de publicación que deje la fuente lista en un solo paso:
1. Lee la versión declarada en el código (la sube el desarrollador antes).
2. Empaqueta la app en `mi-app-<versión>.zip` (excluyendo pruebas, herramientas, cachés).
3. Calcula `sha256` y `size`.
4. Inserta la entrada (con título y notas pasadas como argumentos) al principio de
   `updates.json`, conservando las versiones anteriores.
5. La carpeta resultante se sube a la web o se copia a la carpeta de red/USB tal cual.

### 2.10 Registro y pruebas
- Cada comprobación con novedad, instalación, error y cambio de cadencia queda en el registro
  de actividad de la app.
- Pruebas mínimas del módulo:
  - comparador de versiones (incluido `3.10 > 3.2`);
  - cadencias (`manual` nunca; `daily`/`weekly` según la fecha guardada; fecha corrupta ⇒ comprobar);
  - manifiesto: orden, entradas rotas ignoradas, formatos inválidos rechazados;
  - descarga: hash y tamaño incorrectos rechazados;
  - instalación: reemplaza, respalda, conserva lo ajeno, elimina módulos huérfanos, rechaza
    rutas inseguras y paquetes con versión distinta a la anunciada, y no deja la app a medias
    si falla;
  - interfaz: comprobar/instalar en segundo plano, avisos, persistencia de cadencia y fuente.

## 3. Cómo está aplicado en Radio Timer

| Requisito | Dónde |
|---|---|
| Lógica del gestor (manifiesto, descarga, instalación, cadencias) | `python/radio_timer/updates.py` |
| Preferencias (`updateMode`, `updateUrl`, `lastUpdateCheck`) | `python/radio_timer/storage.py` → `%APPDATA%\RadioTimer\prefs.json` |
| Integración (hilo, temporizador de cadencia, aviso en el pie, reinicio) | `python/radio_timer/app.py` |
| Interfaz (Configuración → Versiones y actualizaciones) | `python/radio_timer/dialogs.py` (`VersionsDialog`) |
| Publicación | `python/tools/make_release.py` |
| Descargas y respaldos | `%APPDATA%\RadioTimer\updates\` y `%APPDATA%\RadioTimer\backups\` |
| Pruebas | `python/tests/test_updates.py` y `python/tests/test_app_smoke.py` |

Publicar una versión de Radio Timer:

```
cd python
python tools/make_release.py --out "D:/actualizaciones" --titulo "Alertas por bloque" --nuevo "Aviso sonoro configurable por sección" --arreglado "El título largo se cortaba con escala de 125 %"
```

(Todo en una línea; la continuación con `^` solo funciona en cmd, no en PowerShell.)

y en la app: Configuración → **Versiones y actualizaciones** → fuente `D:/actualizaciones`
(o la URL donde se haya subido esa carpeta) → **Comprobar ahora** → **Instalar** → **Reiniciar**.
