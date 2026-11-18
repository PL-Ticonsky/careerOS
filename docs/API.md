# API local del MVP

Base: `http://127.0.0.1:8765`. Uso local de un usuario. Respuestas JSON UTF-8; sin autenticación. Ejecutar el servidor antes de probar los ejemplos.

## Lecturas

### `GET /api/data`

Retorna `{ "items": [...], "sources": [...], "states": [...] }`.

Cada item contiene el payload normalizado más `status`, `notes`, `active` y `seen`. Cada fuente incluye su configuración y `run` (última ejecución o `null`). No hay paginación ni parámetros de búsqueda: los filtros actuales viven en el navegador.

### `GET /api/export`

Retorna el array completo de oportunidades con notas y estados. Es una exportación personal, no una autorización para redistribuir anuncios. No hay endpoint de importación.

## Escrituras

Requieren `Content-Type: application/json`, cuerpo JSON objeto y tamaño de 1 a 200.000 bytes. Si se envía `Origin`, su host/puerto debe coincidir con `Host`. Se omite CORS; no está diseñada para consumo desde otra web.

### `POST /api/sync`

Cuerpo: `{}`. Respuesta `200` con `results`, cuyos elementos incluyen `source` y uno de `count`, `cached: true` o `error`. Si otra sincronización del mismo servidor está en curso, devuelve `{ "busy": true }`.

El HTTP 200 no garantiza éxito de todas las fuentes: revisar cada resultado. No hay sondeo de progreso; la solicitud espera a que termine el recorrido de fuentes.

### `POST /api/manual`

Ejemplo sintético para pruebas en una base temporal:

```json
{
  "kind": "evento",
  "title": "Evento de prueba",
  "company": "Organizador de prueba",
  "location": "Bogotá, Colombia",
  "url": "https://example.com/evento-de-prueba",
  "mode": "Presencial",
  "description": "Registro sintético, no es un evento real.",
  "salary": "Gratuito",
  "event_date": "2027-01-15"
}
```

Obligatorios: `kind`, `title`, `url`, `mode`. Tipos: `empleo`, `freelance`, `evento`. Modalidades: `Remoto`, `Híbrido`, `Presencial`, `Por confirmar`. El resto es opcional. `salary` se usa como texto de salario, presupuesto o costo. Una URL repetida actualiza su registro; no crea otro.

Respuesta `201` con el objeto normalizado. La validación de formato de fecha depende actualmente del formulario del navegador; la API requiere endurecimiento antes de producción.

### `POST /api/status`

```json
{
  "id": "ID_OBTENIDO_DE_API_DATA",
  "status": "Guardada",
  "notes": "Revisar requisitos y preparar candidatura."
}
```

Estados: `Sin guardar`, `Guardada`, `Postulada`, `Entrevista`, `Oferta`, `Descartada`. Respuesta `200`: `{ "ok": true }`. `notes` ausente se convierte en texto vacío; siempre reenviar las notas actuales si solo se desea modificar el estado. Notas limitadas a 10.000 caracteres.

## Errores y límites

- `400`: entradas inválidas que cubre la validación actual.
- `403`: Origin no autorizado.
- `404`: ruta de escritura desconocida o ID inexistente al actualizar estado.
- `415`: contenido distinto de JSON.

Los errores de aplicación usan `{ "error": "..." }`. Algunas lecturas desconocidas pasan al servidor estático y pueden responder HTML. No existe un manejador global de errores ni validación completa por esquema: no se garantiza un JSON 400 para toda entrada malformada imaginable. Son prioridades para la siguiente fase.
