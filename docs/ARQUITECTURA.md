# Arquitectura

## Responsabilidades

| Archivo | Responsabilidad |
|---|---|
| `app.py` | Servidor local, normalización de proveedores, conectores de empleo, sincronización y rutas HTTP |
| `opportunity_sources.py` | Adaptadores de proyectos Freelancer y convocatorias Devpost, con campos de contacto y fechas |
| `career_rules.py` | Geografía conservadora, coincidencias técnicas y validación de perfil/fechas |
| `workspace.py` | Migración versionada, procedencias, búsqueda paginada, seguimiento, perfil, respaldo y recuperación |
| `static/app.js` | Vistas, peticiones paginadas, formularios, filtros persistentes y progreso |
| `sources.json` | Configuración y límites de fuentes |

No hay dependencias externas de ejecución. Los conectores de empleo siguen agrupados en `app.py` para conservar los contratos y las pruebas de ingesta; se pueden extraer por proveedor cuando crezca el catálogo.

## Datos e ingesta

`API/RSS → collect → parse_record/normalize → store → SQLite → API paginada → tarjetas → detalle bajo demanda`.

Cada fuente se procesa por separado. `Batch` conserva registros válidos y diagnósticos de rechazos. Si una página falla o todos los registros son inválidos, no se guarda ese lote. Una carga parcial guarda válidos sin desactivar observaciones anteriores. Los resultados completos reemplazan el lote de esa fuente; no confirman cierres.

`sightings(opportunity_id,source)` guarda cada observación con payload, active y seen. El mismo URL puede tener varias fuentes. `opportunities` conserva un registro principal y sus campos personales. Su indicador active es la unión de las observaciones activas. Si la fuente principal sale del lote, se usa otra observación activa, conservando todas las procedencias. Los upserts nunca modifican notas, etapa, favorito, acción ni fecha. Un alta manual de una URL existente no sustituye sus datos.

La identidad sigue siendo SHA-256 de URL exacta (24 hexadecimales). `duplicate_key` normaliza empresa y título para sugerir revisiones: no fusiona URLs distintas ni prueba que dos anuncios sean la misma vacante. El detalle limita a 20 sugerencias.

La disponibilidad se calcula al leer: cierre explícito, expiración, último lote o fuera del lote. El servidor no asigna cierre confirmado por ausencia. Las exclusiones geográficas prevalecen sobre señales positivas; restricciones ambiguas quedan por confirmar. La clasificación no comprueba permisos ni requisitos completos.

## Esquema y migración

- `opportunities`: payload principal, estado, notas, favorito, próxima acción, fecha, texto normalizado y clave de posibles duplicados.
- `sightings`: payload/estado por fuente y oportunidad.
- `stage_history`: transiciones reales de etapa y hora UTC.
- `settings`: perfil personal.
- `schema_migrations`: versiones aplicadas.
- `runs`: último intento por fuente; `run_history`: hasta 1.000 intentos globales, últimos 100 expuestos.

La versión 1 añade campos y tablas sin eliminar registros. Antes de migrar una base anterior se guarda una copia SQLite mediante `Connection.backup`. Los estados existentes se mantienen y se inicializan favoritos para las etapas activas; no se inventa historial pasado. Inicializar repetidamente no repite la migración ni reinicializa favoritos.

## Búsqueda y frontend

La API filtra y ordena en SQLite con parámetros enlazados y paginación 24 por defecto (máximo 100). La respuesta de tarjetas omite descripciones y notas. El detalle se consulta por ID. La búsqueda usa texto normalizado persistido; coincidencias personales usan patrones compilados y ese texto para evitar normalizar todas las descripciones en cada petición. Las razones se calculan para las tarjetas devueltas. No hay índice de texto completo: ciertos filtros y puntuaciones siguen recorriendo el catálogo.

Los filtros viven en `localStorage` por sección, con tolerancia a almacenamiento no disponible. El perfil se guarda en SQLite y se incluye en respaldos. Las respuestas de búsqueda obsoletas se descartan mediante una secuencia; escribir usa una demora de 250 ms. Los empates se ordenan por ID. Las fechas de calendario se muestran sin el desplazamiento de medianoche UTC; el filtro de pendientes usa el día de Bogotá.

El frontend escapa texto externo y los enlaces importados solo admiten HTTP(S). Se conservan etiquetas de formularios, diálogos nativos y avisos accesibles. Favorito y etapa son campos independientes.

## Concurrencia y recuperación

`threading.Lock` evita operaciones simultáneas de ingesta/recuperación dentro del servidor. Un bloqueo asesor de archivo por base (`flock` en Unix, `msvcrt` en Windows) extiende esa exclusión a CLI y otros servidores. Se libera al cerrar el archivo o morir el proceso. No borrar el archivo del bloqueo para forzar una ejecución.

La sincronización de interfaz se ejecuta en un hilo. `/api/sync/progress` expone fuente actual, terminadas, total y resultados. No existe una cola persistente ni un programador: reiniciar cancela el trabajo en curso; los lotes ya confirmados permanecen.

El respaldo JSON lee anuncios, procedencias, perfil e historial desde una transacción de lectura consistente. La restauración valida todo antes de escribir, crea una copia SQLite y aplica los cambios en una única transacción. Es una recuperación por combinación: conserva registros ajenos al archivo; reemplaza los campos y relaciones de IDs coincidentes. No ejecuta SQL recibido. La copia previa permite recuperar el estado completo anterior con el servidor detenido.

## Operación

Servidor solo en `127.0.0.1`; valida host local con puerto y origen para escrituras. No hay autenticación multiusuario, TLS ni servicio de producción. No cambiar a `0.0.0.0` para publicar.

La base, sus copias y archivos de bloqueo quedan bajo `data/` (o junto a `CAREEROS_DB`) y no se versionan. Las fuentes se consultan secuencialmente y respetan caché. Los fallos permiten reintento después de 60 segundos; no hay backoff exponencial ni tratamiento específico de `Retry-After`.

## Verificación

Pruebas unitarias y HTTP con SQLite temporal, respuestas externas simuladas y puertos efímeros. `tests/run_browser.py` arranca un servidor sintético aislado y comprueba el flujo completo con Playwright, sin APIs externas ni base personal. Las capturas y respaldo de prueba se escriben en una carpeta temporal; el servidor se detiene incluso si una comprobación falla.

Los dos adaptadores nuevos usan endpoints públicos fijos, paginación limitada y validación por registro. No consultan URLs arbitrarias del usuario ni siguen enlaces a perfiles o páginas bloqueadas. Un fallo de página impide reemplazar el lote completo; registros malformados producen una carga parcial que conserva observaciones anteriores. El payload admite campos nuevos sin alterar la identidad ni el seguimiento. El frontend muestra campos por tipo y valida los esquemas HTTP(S) de los enlaces de contacto antes de insertarlos.

## Agrupación de presentación y foco local

`feed_group` define una agrupación conservadora sin migrar identidades ni fusionar datos. SQL aplica filtros, calcula grupos y elige representante con ROW_NUMBER según el orden solicitado antes de LIMIT/OFFSET; COUNT DISTINCT produce el total paginable. Tracking mantiene cada registro. Un NOT EXISTS por la clave indexada de empresa/título evita que un seguimiento guardado reaparezca como otra variante del grupo. `local_market` distingue Bogotá, Colombia explícita, remoto compatible y resto, y no convierte restricciones ambiguas en elegibilidad.

Las seis nuevas fuentes ATS reutilizan los adaptadores existentes con `market_scope=colombia`; el filtro geográfico se aplica antes de guardar. Greenhouse conserva `first_published` cuando está disponible. No se infiere modalidad desde el país. Los directorios manuales y pendientes se conservan en el catálogo desplegable.

## Adaptadores de empleo adicionales

`job_connectors.py` implementa Get on Board, SmartRecruiters por empresa y Jooble Colombia. Reutiliza normalización, Batch, persistencia y exclusión de operaciones existentes. Los errores de página/detalle abortan el lote antes de guardarlo; los anuncios inválidos producen diagnósticos parciales sin desactivar observaciones anteriores. Los enlaces públicos se validan contra el dominio de cada proveedor. SmartRecruiters consulta solo publicaciones con visibility PUBLIC, con URLs de detalle construidas desde host fijo e ID validado, sin seguir el ref externo de la respuesta.

Get on Board solicita expansión de empresa, ciudades, modalidad y nivel; filtra por Colombia en la API y por señal geográfica explícita al normalizar. `refresh_before` separa la caducidad del dato (24 horas) de un cierre o expiración de la vacante. Jooble lee la clave de entorno solo al consultar; no la devuelve en metadatos ni la incorpora a respaldos. Sus errores HTTP/transporte se convierten en mensajes sin la URL que contiene la credencial. sources() solo activa Jooble si hay clave configurada.

`event_catalogues.py` lee exclusivamente el bloque JSON público `data-page=app` del calendario MLH, sin ejecutar JavaScript. Valida el formato y fechas, mantiene los enlaces publicados y aplica eligible_event. Cero eventos compatibles es una carga válida; datos malformados impiden desactivar observaciones anteriores.

## Correcciones de grupos remotos y configuración de Places

feed_group añade una clave de contenido para empleos remotos explícitos en Colombia, con empresa, SHA-256 del texto normalizado completo (mínimo 200 caracteres), firma tecnológica del título, nivel, contrato y salario. Sin dos tecnologías de título mantiene el título completo como firma. Los demás tipos conservan la agrupación anterior por ubicación/modalidad. La consulta calcula las claves de oportunidades atendidas una vez y aplica una función de pertenencia, evitando que la antigua clave empresa/título deje escapar variantes del mismo contenido. Las ubicaciones visibles se agregan con una ventana SQL antes de paginar. No hay nueva migración.

places_config.py gestiona la clave de entorno o un archivo privado junto a la base. No se almacena dentro de los respaldos ni se registra su valor. El formulario solo envía al servidor local y vacía el campo tras guardar o cerrar. Guardar un prospecto persiste place ID y referencia personal, con enlace canónico de Maps, no una copia del contenido consultado. Las respuestas de Google mantienen las atribuciones y el token paginable.

El servidor aumenta la cola de conexiones locales a 64. El cliente usa tiempos límite y recuperación de GET; no repite automáticamente POST. El progreso sigue consultándose tras una interrupción transitoria y solo se anuncia el resultado cuando vuelve a recibirse el estado del servidor. tests/test_frontend_network.js reproduce fallos de GET, respuesta perdida de POST y recuperación del progreso sin emitir escrituras duplicadas.

## Conector SerpApi

serpapi_connector.py consulta únicamente los endpoints fijos search.json y account.json de SerpApi. Filtra la respuesta de cuenta a contadores de cuota y descarta email, ID y clave. Los errores de transporte/HTTP/datos del proveedor se convierten en mensajes sin la URL autenticada ni el cuerpo remoto.

La consulta cuenta con límites de cinco términos y dos páginas máximas por término, con una página en la configuración inicial. Comprueba antes la cuota necesaria. Usa gl=co, hl=es, location=Bogota, Colombia y tokens de Google para paginar, sin seguir URLs de paginación externas que podrían contener secretos. Un error de consulta aborta el lote; registros inválidos producen carga parcial, conservando observaciones anteriores. La normalización requiere señal local explícita.

La identidad se calcula sobre el enlace de postulación público sin UTM; se preservan todos los portales apply_options y discovery_queries. Las URLs internas de SerpApi y URLs con parámetros de credenciales no se incorporan como anuncios. El secreto se carga desde SERPAPI_API_KEY o un archivo privado junto a la base, excluido de Git y respaldos.
