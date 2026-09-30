# Cambios de Radio Timer

Cada versión estable tiene aquí su sección. Al hacer push a main con un `__version__` nuevo,
la GitHub Action de integración y entrega crea la etiqueta y el release con el título y las notas
de la sección correspondiente (`__version__ = "3.4.0"` → `## 3.4.0`); sin esa sección la
publicación falla. La app las muestra en Configuración → Versiones y actualizaciones.

Las compilaciones de desarrollo (canal Desarrollo) no necesitan sección: sus notas salen de los
títulos de los commits. Prefijos útiles en los commits: `feat:` o «Agrega…» (Nuevo), `fix:` o
«Corrige…» (Arreglado), `security:` (Seguridad); el resto cuenta como Cambiado.

Formato de cada sección (las categorías vacías se omiten):

```
## X.Y.Z — AAAA-MM-DD — Título corto

### Nuevo
- Función nueva.

### Arreglado
- Fallo corregido.

### Cambiado
- Comportamiento que cambió.

### Seguridad
- Aviso de seguridad.
```

## 3.3.0 — 2026-09-27 — Actualizaciones desde GitHub

### Nuevo
- La app se actualiza desde los GitHub Releases del repositorio: basta con el enlace del repositorio como fuente, y es la fuente por defecto.
- Integración y entrega continuas: en cada push GitHub corre las pruebas; al subir `__version__` publica la versión estable sola (etiqueta y release con las notas de este archivo), y en los demás pushes publica una compilación de desarrollo.
- Canales Estable y Desarrollo en Configuración → Versiones: la PC de cabina recibe solo versiones estables; el canal Desarrollo recibe además cada compilación (3.3.1-dev.N) para probar antes de publicar.
- CHANGELOG.md como lugar único de las notas de cada versión.

### Cambiado
- El gestor de versiones acepta tres fuentes: repositorio de GitHub, URL https con updates.json o carpeta local/de red.
- Las versiones se comparan con las reglas de semver: 3.3.1-dev.9 < 3.3.1-dev.10 < 3.3.1.

## 3.2.0 — 2026-09-27 — Gestor de versiones

### Nuevo
- Gestor de versiones: comprobación manual, diaria o semanal; lista de versiones con notas; instalar cualquier versión sin reinstalar la app.
- Sincronización de la programación semanal desde radioluz937fm.com.
- Programas con horario en minutos (por ejemplo 07:30–08:00).

### Arreglado
- El reloj central ya no se reinicia al pasar de una sección en cadena a la siguiente.
- La instalación de una versión se revierte por completo si falla a mitad.

### Cambiado
- Bloques de la hora: EN AIRE 50 + CIERRE 5 en cadena y CORTE Y PROMOCIONES 5.

### Seguridad
- Solo se aceptan fuentes https o carpetas locales; los paquetes se verifican con SHA-256.

## 3.1.0 — 2026-09-26 — Parrilla semanal

### Nuevo
- Título del programa de cada hora sobre el reloj, con parrilla distinta para cada día.
- La secuencia se reinicia sola en cada hora en punto.
