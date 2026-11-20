# API local

Base: `http://127.0.0.1:8765`. Un usuario local, sin autenticación. `Host` debe ser `127.0.0.1` o `localhost` con el puerto del servidor. No se habilita CORS. Las escrituras exigen JSON objeto y rechazan un `Origin` distinto del host.

## Lecturas que usa la interfaz

- `GET /api/meta`: `{sources, states, history, profile, stats}`. Estadísticas globales: total, active, compatible, tracking, due, stages y duplicate_groups y by_kind (conteos por empleo/freelance/evento). Los descartados sin favorito no cuentan en tracking; sí son accesibles en Postulaciones.
- `GET /api/opportunities`: `{items,total,raw_total,grouped_duplicates,offset,limit,has_more}`. Las tarjetas omiten `description` y `notes`. Incluyen favorito, próxima acción, fecha, disponibilidad, coincidencias y número de posibles duplicados.
- `GET /api/item?id=ID`: detalle completo, notas, `sources`, `timeline` y hasta 20 posibles `duplicates`. 404 si no existe.
- `GET /api/profile`: perfil personal actual.
- `GET /api/sync/progress`: `{running,current,completed,total,results,error?}`. `current` es el ID de fuente. `completed` incluye caché, éxito y fallo terminados. Un resultado desde caché no crea historial.
- `GET /api/runs`: los últimos 100 intentos reales.
- `GET /api/backup`: respaldo personal versionado, restaurable.

### Búsqueda paginada

Ejemplo:

```text
/api/opportunities?view=empleo&query=python&location=Colombia&limit=24&offset=0&sort=match
```

Parámetros:

| Parámetro | Valores |
|---|---|
| `view` | empleo (predeterminado), freelance, evento, tracking |
| `query`, `location` | Texto literal, sin distinguir mayúsculas o tildes |
| `mode`, `level`, `source`, `eligibility`, `status` | Coincidencia exacta; source consulta todas las procedencias |
| `salary`, `favorite`, `inactive`, `due` | `1` activa el filtro |
| `market` | vacío (todos), colombia (ubicación explícita), bogota, compatible (local o remoto compatible) |
| `show_saved`, `ungrouped` | `1` incluye seguimientos u omite la agrupación, respectivamente. Solo favoritos incluye guardadas expresamente. |
| `sort` | local (Bogotá, Colombia, remoto compatible y resto; coincidencias dentro de cada grupo), match (predeterminado), recent, company, due, event (próxima fecha de participación/inicio) |
| `limit` | 1–100; predeterminado 24 |
| `offset` | 0–1.000.000; predeterminado 0 |

`due=1` selecciona fechas de hoy o anteriores en Bogotá y excluye Oferta y Descartada. `tracking` incluye favoritos y cualquier etapa distinta de Sin guardar, incluso ofertas vencidas y descartadas. Las otras vistas requieren disponibilidad actual salvo `inactive=1`. Cada orden incluye ID como desempate estable; cambios concurrentes del catálogo pueden desplazar páginas con offset.

## Escrituras

### `POST /api/status`

```json
{
  "id": "ID_DE_24_HEXADECIMALES",
  "status": "Entrevista",
  "favorite": true,
  "notes": "Preparar conversación técnica",
  "next_action": "Revisar preguntas",
  "due_date": "2027-01-15"
}
```

ID obligatorio. Los demás campos son opcionales; omitirlos conserva sus valores. Debe enviarse al menos un cambio. Favorito requiere booleano. Estados: Sin guardar, Guardada, Postulada, Entrevista, Oferta, Descartada. Límites: notas 10.000 caracteres, acción 500, fecha real AAAA-MM-DD o vacía. Cambiar solo el favorito no modifica la etapa ni crea una transición. Un cambio de etapa registra estado anterior, nuevo estado y fecha UTC. Enviar el mismo estado no duplica el historial. 200 `{ok:true}`, 404 para ID inexistente.

### `POST /api/profile`

```json
{"skills":["python","sql","c++"],"level":"Junior","location":"Colombia","mode":"Remoto"}
```

Reemplaza el perfil. Máximo 50 habilidades de hasta 60 caracteres; ubicación hasta 200. Nivel y modalidad admiten vacío para ninguna preferencia. Las habilidades se normalizan y deduplican. Puntuación: 10 por habilidad detectada y 5 por cada coincidencia de nivel, modalidad o ubicación configurados; no es porcentaje. La interfaz muestra las razones, no una probabilidad de contratación.

### `POST /api/manual`

```json
{"kind":"evento","mode":"Presencial","title":"Evento sintético","company":"Organizador de prueba","url":"https://example.com/evento","event_date":"2027-01-15"}
```

Obligatorios: tipo (empleo/freelance/evento), modalidad, título y URL HTTP(S). Límites: título 300, empresa/ubicación/salario 200, URL 4096, descripción 20.000, fecha real AAAA-MM-DD. Una nueva oportunidad devuelve 201 con el objeto. Una URL exacta existente devuelve 200 `{duplicate:true,id:...}` sin reemplazar nada. Los IDs siguen siendo los primeros 24 hexadecimales del SHA-256 de la URL exacta.

### Sincronización

`POST /api/sync/start` con `{}` devuelve 202 `{started:true}` o `{busy:true}`. Sondear `/api/sync/progress`. Puede comenzar antes de conocer el total de fuentes. Una segunda sincronización o restauración no se ejecuta a la vez sobre la misma base, incluso desde otro proceso.

`POST /api/sync` conserva la llamada síncrona anterior: espera y devuelve `{results:[...]}` o `{busy:true}`. El 200 no garantiza éxito de todas las fuentes; consultar cada resultado. La interfaz utiliza la variante en segundo plano.

### Recuperar respaldo

Enviar el objeto completo obtenido de `/api/backup` a:

1. `POST /api/restore/preview`: valida y devuelve `{new,updated,preserved,total}` sin escribir.
2. `POST /api/restore`: vuelve a validar, crea una copia SQLite consistente y aplica la recuperación en una transacción. Devuelve los conteos y `safety_backup` (ruta local).

Formato `careeros`, versión `1`: opportunities, sightings, timeline y profile. No acepta SQL ni un archivo SQLite arbitrario. Valida IDs, URLs, tipos, referencias, fechas de seguimiento y estructura. Actualiza oportunidades coincidentes, conserva las ausentes del respaldo y reemplaza el perfil. Para oportunidades restauradas, reemplaza su historial y procedencias; restaurar dos veces no duplica transiciones. Configuración de fuentes y ejecuciones no se importan. La vista previa es orientativa: si hay escrituras posteriores, los conteos se recalculan al restaurar.

## Compatibilidad

- `GET /api/data`: snapshot completo anterior, con campos nuevos. La interfaz ya no lo utiliza.
- `GET /api/export`: array de oportunidades, con notas y estados. Exportación de lectura; el restaurador necesita `/api/backup`.

## Errores

Errores JSON `{error:"..."}`: 400 entradas inválidas, 403 host/origen no autorizado, 404 recurso inexistente, 409 restauración bloqueada por otra operación, 415 contenido distinto de JSON y 500 fallo interno. Las rutas `/api/*` desconocidas también devuelven JSON. Las rutas estáticas conservan las respuestas del servidor de archivos.

Tamaño máximo de escritura: 200.000 bytes; recuperación/vista previa: 100.000.000 bytes. Se conserva el límite de 100.000 oportunidades en un respaldo. No exponer este servidor en Internet.

## Datos ampliados de proyectos y eventos

Los payloads conservan, cuando existan: `contact_name`, `contact_email`, `contact_phone`, `contact_url`, `contact_note`, `contact_channel`, `requirements`, `deliverables`, `description_scope`, `summary`. Las tarjetas incluyen resumen (hasta 320 caracteres), pero no el cuerpo completo de la descripción. `description_scope=summary` indica que la fuente entregó solo una ficha resumida.

Freelance añade `project_type`, `project_deadline`, `client_location`, `required_skills`, `bid_count`, `payment_verified`. `salary` conserva presupuesto, moneda y período originales. El país del cliente no determina elegibilidad del profesional.

Eventos añade `event_type`, `event_period`, `event_end_date`, `registration_deadline`, `submission_deadline`, `registration_url`, `venue`, `topics`, `cost`, `prizes`, `participants`. Costo y premio son independientes. `salary=1` en la búsqueda de eventos filtra costo informado. Las fechas son de calendario: el cierre de entregas no implica una hora exacta. Devpost publica una ventana de entrega de proyectos, que no debe confundirse con un plazo específico de registro.

El alta manual acepta contacto (nombre 200, correo 254, teléfono 100, URL 4096, nota 1000 caracteres), requisitos/entregables (10.000 cada uno), tipo de proyecto/evento (100), sede (500), premios (300) y fechas reales de inicio/fin/cierre/plazo. Para eventos, el campo de importe del formulario se guarda como `cost`, sin convertir premios en precio. No se admiten URLs de contacto ajenas a HTTP(S) ni correos malformados. Estos campos quedan dentro del payload y del respaldo existente, sin una migración destructiva.

### Radar y prospectos

- `GET /api/opportunities?view=evento`: solo Bogotá presencial o modalidad online explícita. `discovery=1` cambia a anuncios oficiales por verificar. Admite `event_type` y `free=1` (costo explícito gratuito).
- `GET /api/places/status`: devuelve `{configured: boolean}` sin exponer credenciales.
- `POST /api/places/search`: `{query, area?, page_token?}`. Respuesta: `{items, next_page_token, examined, attribution}`. Consulta bajo demanda, sin escribir la base. Requiere `GOOGLE_PLACES_API_KEY`; errores de configuración o proveedor se devuelven como JSON sin el secreto. Cada página es una consulta facturable de Google. Guardar un resultado utiliza el flujo manual y favoritos existente.

### Agrupación y exclusión del feed

Las vistas empleo/freelance/evento agrupan por defecto antes de contar y paginar. `total` cuenta tarjetas agrupadas; `raw_total` cuenta registros filtrados, `grouped_duplicates` su diferencia y cada tarjeta incluye `group_count`. El detalle incluye `grouped_variants` con id, URL, fuente, ubicación, etapa y favorito. La clave de presentación añade tipo, ubicación normalizada, modalidad, contrato y fechas de evento a la empresa/título; sin empresa no agrupa. Las sugerencias antiguas `duplicates` son más amplias y siguen siendo orientativas.

El feed excluye por defecto favoritos y todas las etapas distintas de Sin guardar, junto con variantes del mismo grupo aunque el seguimiento esté fuera del filtro actual o del último lote. `show_saved=1` o `favorite=1` permite incluirlos. Tracking conserva registros individuales y no aplica esta exclusión ni agrupa. Mercado vacío sigue siendo el predeterminado de API; el navegador usa colombia inicialmente en empleo y recuerda la selección.

### Configuración de conexiones

GET /api/meta incluye `integration_status` cuando aplica: ready, needs_key, needs_access o access_review. Jooble devuelve enabled=false y needs_key si falta JOOBLE_API_KEY; nunca devuelve la clave. Get on Board y Talan utilizan el flujo /api/sync existente. Los payloads de Get on Board añaden company_url, provider_id, salary_min, salary_max y refresh_before. Al superar refresh_before, availability es Actualización pendiente; se omite del feed activo sin marcar la vacante como cerrada o vencida, y sigue accesible en Tracking o con inactive=1.

### Duplicados remotos, reconexión y configuración de Places

La agrupación remota de empleos colombianos admite variantes de ciudad y título únicamente con descripción sustancial idéntica, mismo empleador, nivel, tecnologías del título, contrato e importe. Las tarjetas incluyen group_locations; el detalle incluye title por cada grouped_variants. Las claves se calculan a partir del payload, sin fusionar oportunidades ni cambiar IDs.

- GET /api/places/status devuelve configured y source (none/local/environment), nunca la clave.
- POST /api/places/configure recibe {key: CLAVE}; guarda fuera de SQLite con permisos 0600. Exige el mismo origen/JSON que las demás escrituras; la respuesta solo incluye estado. Una clave de entorno no se sobrescribe desde este formulario.
- POST /api/places/save recibe {place_id, label}. Guarda una referencia personal favorita de tipo freelance con URL canónica de Google Maps y place ID. Devuelve 201 o 200 si el ID ya estaba guardado, conservando los datos anteriores. No persiste nombre, dirección ni teléfono de la respuesta de Google.

El cliente reintenta solo GET ante pérdida de conexión. Para POST /api/sync/start con respuesta perdida, consulta progreso sin repetir la escritura; el sondeo se recupera con espera progresiva. POST /api/places/search conserva un único intento para evitar repetir consultas facturables.

### Ofertas de SerpApi / Google Jobs

La fuente serpapi se habilita al configurar SERPAPI_API_KEY o el archivo privado local. Metadatos públicos incluyen las queries configuradas, nunca el secreto. Sus payloads incluyen apply_options ({title,link}), listing_provider, provider_id, discovery_queries y published_label. Esta última es la antigüedad textual al consultar, no una fecha real recalculada. La carga utiliza los endpoints de sincronización existentes y respeta el intervalo de 24 horas. Los fallos de cuota/proveedor conservan el lote anterior.

## Referencia COP y prioridad

`sort=relevance` ordena por la puntuación explicable antes de paginar. `priority=top|matched|low_competition` filtra antes de agrupar/paginar. `quality` aparece en tarjetas y detalle con score (puntos, no porcentaje), label, top, matched, low_competition, reasons y note. No compara salarios.

`salary` sigue siendo el original. `salary_reference` es nulo si no hay salario o es un evento; status native/converted/unknown/unavailable. Las conversiones incluyen display, estimated, currency, updated y provider_url, sin redistribuir el catálogo de tasas. La caché se actualiza en segundo plano al arrancar y cada hora, como máximo una descarga diaria tras éxito. Tasas con más de siete días no se utilizan; los errores no impiden buscar.

## Analíticas de postulaciones

`GET /api/analytics`: filtros `query`, `kind=empleo|freelance`, `stage` (estado existente), `period=30|90`, `limit` 1–100 (25 por defecto) y `offset`. Devuelve `items`, `total`, `has_more`, `summary`, `stages` actuales y `monthly` (últimos seis meses). Los totales son sobre todo el conjunto filtrado, antes de paginar. Los eventos y los favoritos sin postulación quedan fuera. Los procesos que tuvieron Postulada, Entrevista u Oferta siguen contando aunque se descarten.

`POST /api/status` admite `applied_date` (AAAA-MM-DD, no futura, vacío para quitar corrección) y `applied_via` (hasta 200 caracteres). Si se cambia a Postulada sin enviar applied_date y no existe una fecha guardada, se conserva la primera fecha del historial o se registra hoy en Bogotá. El detalle recupera la primera transición a Postulada cuando falta la fecha explícita. La migración agrega ambas columnas; los respaldos versión 1 anteriores siguen siendo compatibles y los nuevos conservan estos campos.

## Salud para el lanzador local

`GET /api/health` devuelve `{"app":"careeros","version":1}` sin datos personales ni claves. El lanzador lo usa para esperar el arranque y distinguir CareerOS de otra aplicación que ocupe el puerto 8765. Aplica las mismas comprobaciones de Host local que el resto de la API.
