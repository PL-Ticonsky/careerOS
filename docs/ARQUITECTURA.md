# Arquitectura actual

## Recorrido de los datos

`APIs/RSS → collect() → normalize() → store() → SQLite → snapshot() → API local → frontend`

`sync()` lee `sources.json`, ignora fuentes desactivadas y respeta el caché registrado en `runs`. Cada proveedor se consulta y guarda de forma independiente. Si un proveedor falla, se registra el error y se continúa con el siguiente. No se sustituye su lote anterior.

`store()` marca inactivas las filas previas de esa fuente y hace upsert del nuevo lote en una transacción. Los campos `status` y `notes` no se sobrescriben. Las altas manuales usan `deactivate=False`.

## Persistencia

Archivo predeterminado: `data/careeros.db`. Variable alternativa: `CAREEROS_DB`. La carpeta y las tablas se crean al iniciar. El esquema se define en `init()`; no existe un sistema de migraciones.

| Tabla / campo | Significado |
|---|---|
| `opportunities.id` | Primeros 24 caracteres hexadecimales del SHA-256 de la URL exacta |
| `source` | ID configurado de la fuente o `manual` |
| `payload` | JSON normalizado del anuncio |
| `active` | Presencia en el último lote guardado de la fuente |
| `seen` | Fecha ISO UTC de la última ingesta de esa fila |
| `status`, `notes` | Seguimiento personal persistente |
| `runs.source` | Clave de la fuente, una fila por fuente |
| `attempted` | Epoch del último intento terminado |
| `success` | Fecha ISO UTC de la última carga correcta |
| `count`, `error` | Tamaño del último lote correcto y error del último intento |

No se guarda el JSON original completo del proveedor. El JSON normalizado incluye título, empresa, ubicación, descripción en texto, URL, salario textual, publicación, modalidad, tipo, fecha de evento, elegibilidad, skills, nivel y score. Himalayas añade `apply_url`, `timezones`, `expires` y `employment_type`.

## Servidor y frontend

`ThreadingHTTPServer` escucha solo en `127.0.0.1`. `Handler` sirve `static/` y los endpoints `/api/*`. No hay paquetes externos de Python. `threading.Lock` evita dos sincronizaciones simultáneas en el mismo proceso; cada operación abre y cierra su propia conexión SQLite.

El frontend usa JavaScript nativo, `fetch`, `<dialog>` y renderizado de tarjetas. Las cadenas externas se escapan antes de insertarlas en HTML. Se descargan todos los registros, se filtran en memoria y se muestran 24 tarjetas por incremento. No hay framework, build, router de URLs ni almacenamiento del estado de filtros.

## Añadir un conector

1. Revisar documentación oficial, autenticación, límites, permisos de uso y atribución.
2. Crear una rama en `collect()` o extraer adaptadores a módulos sin cambiar el contrato normalizado.
3. Usar endpoints documentados y timeout; nunca aceptar URLs arbitrarias del visitante para consultas de backend.
4. Normalizar y preservar URL original y, si difiere, URL de postulación. No interpretar datos faltantes como compatibilidad confirmada.
5. Definir explícitamente paginación, alcance y semántica de cierre. El MVP trata todas las cargas como lotes reemplazables, incluso feeds parciales; mejorar esta distinción antes de ampliar casos.
6. Agregar fixtures sintéticos y pruebas del adaptador, errores y atribución; probar una carga real con permiso y acceso disponible.
7. Registrar la fuente en `sources.json` y actualizar `FUENTES.md`.

## Operación

- Inicio: `python3 app.py` o `./iniciar.sh` en Linux/macOS con Bash.
- Otro puerto: `python3 app.py --port 8766`.
- Ingesta sin interfaz: `python3 app.py --sync`; evitar concurrencia con otra ingesta.
- Backup: detener el servidor y copiar el archivo SQLite a una ubicación privada.
- Restauración: detener el servidor, conservar una copia del archivo actual y reemplazarlo por el respaldo compatible. No hay importador de `/api/export`.
- Tests: base temporal, `fetch` simulado y sin alterar los datos reales.
