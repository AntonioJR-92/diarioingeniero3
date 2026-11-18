# Diario de un ingeniero

Web estática en HTML, CSS y JavaScript. Las páginas principales están en la raíz
y en `blog/`, `eco/`, `emprender/`, `mis_sitios/` y `viajes/`. Los directorios
`lm_brianda_20/` y `lm_brianda_21/` contienen ejercicios archivados.

## Ejecutar las comprobaciones

Requisitos: Python 3.12 y Node.js 22. Las comprobaciones del repositorio no
necesitan instalar paquetes adicionales.

```sh
python3 -m unittest discover -s tests -p '*test*.py'
node --test tests/cookies.test.js
python3 tools/check_javascript.py --include-archives
python3 tools/audit_site.py --include-archives --baseline docs/audit/archive-issues.json
python3 tools/generate_sitemap.py --check
```

GitHub Actions ejecuta estas mismas comprobaciones en cada push y pull request.
El auditor comprueba los archivos de la web principal y de los ejercicios
históricos, con las incidencias activas en `docs/audit/archive-issues.json`.
El inventario de originales pendientes indica los recursos históricos para los
que la página ofrece un aviso o una alternativa verificada.

Para obtener el inventario completo de problemas locales, incluyendo los ya
conocidos:

```sh
python3 tools/audit_site.py --json .audit-output/main.json
python3 tools/audit_site.py --include-archives --json .audit-output/all.json
python3 tools/check_javascript.py --include-archives
```

Estos comandos terminan con código 1 cuando detectan problemas; el auditor
escribe igualmente su informe JSON. El chequeo de JavaScript compila los
fragmentos activos, sin ejecutarlos. Los auditores no realizan peticiones de
red ni comprueban la disponibilidad de servicios externos.

## Previsualizar y publicar

```sh
python3 -m http.server 8000
```

Abre `http://localhost:8000/` en un navegador. La web carga algunas librerías y
servicios de terceros, por lo que su disponibilidad depende de la conexión.
Las rutas de recursos compartidos son relativas para permitir servir el sitio
tanto desde una raíz como desde un subdirectorio.

Después de añadir o retirar páginas principales, regenera el sitemap:

```sh
python3 tools/generate_sitemap.py
```

El sitemap usa la publicación de GitHub Pages del repositorio. Para usar otra
dirección en una generación puntual, pasa `--base-url` al generador. No se inventan fechas de
modificación. Los ejercicios archivados quedan fuera del sitemap principal.

## Auditoría

El [informe del 18 de noviembre de 2026](docs/audit/2026-11-18.md) explica las
correcciones, los resultados de las pruebas y los problemas que requieren
recuperar contenido o revisar decisiones editoriales.
