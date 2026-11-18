# Entrega de CareerOS

## Objetivo y alcance

CareerOS centraliza oportunidades de empleo IT en Bogotá y remoto internacional, seguimiento de candidaturas, freelance y eventos. Es independiente del portafolio ticonsky.dev. El objetivo de producto es facilitar entrevistas y oportunidades profesionales, no solo acumular anuncios.

Esta entrega es un MVP local de un usuario. No es la arquitectura de producción inicialmente planteada (Next.js/FastAPI/PostgreSQL). Se eligió Python estándar, SQLite y frontend sin compilación para validar las fuentes y el flujo sin cuentas ni dependencias adicionales.

## Primeros 15 minutos

1. Obtener acceso al repositorio privado, clonarlo y leer el README.
2. Ejecutar `python3 -m unittest discover -s tests -v` desde la raíz.
3. Ejecutar `python3 app.py` y abrir http://127.0.0.1:8765.
4. Pulsar **Actualizar fuentes**. La primera carga puede tardar varios minutos y requiere Internet. Un clon nuevo empieza vacío: no incluye la base personal del propietario.
5. Filtrar por Himalayas y una tecnología; abrir una oferta y comprobar los enlaces de fuente y postulación.
6. Guardar una oportunidad, cambiar su estado y añadir notas. Recargar y comprobar persistencia.
7. Abrir Fuentes de datos para revisar los resultados de cada conexión.

No detengas el servidor mientras otra persona esté usando la vista local. Cambios en Python requieren reiniciar el proceso; cambios en HTML/CSS/JS requieren recargar el navegador.

## Estado comprobado de la entrega

- Nueve conectores: Himalayas, Jobicy, Arbeitnow, WWR, Remote OK, Remotive, Greenhouse, Lever y Ashby.
- 32 entradas de fuentes y directorios. No todas son APIs implementadas.
- Carga observada el 17 de noviembre de 2026: 2.238 registros en la máquina original. Es una referencia de la prueba, no un resultado garantizado en un clon nuevo.
- ATS configurados: Canonical (Greenhouse), Caseware (Lever) y Ashby (Ashby).
- Doce pruebas unitarias de persistencia, normalización y conectores.
- Navegador: comprobados filtro por fuente y texto, guardado, pantalla de seguimiento, detalle, enlace de Himalayas y cambio de estado.
- No se han probado todas las combinaciones de filtros, dispositivos o errores HTTP mediante pruebas de extremo a extremo automatizadas.

## Archivos que conviene leer

| Archivo | Responsabilidad |
|---|---|
| `app.py` | Servidor local, esquema SQLite, normalización, nueve adaptadores, sincronización y API |
| `sources.json` | Registro de fuentes, intervalos y límites de paginación |
| `static/app.js` | Navegación, filtros, tarjetas, formularios y seguimiento |
| `static/index.html` / `style.css` | Estructura y apariencia adaptable |
| `tests/test_app.py` | Pruebas sin acceso a la red y con base temporal |
| `FUENTES.md` | Investigación, documentación oficial y acceso pendiente |

## Límites y deuda técnica que no se deben perder

- La deduplicación usa URL exacta. Un mismo anuncio en varios agregadores puede aparecer varias veces. La misma URL importada de dos fuentes conserva el último payload/fuente, manteniendo notas y estado.
- `active` significa presencia en el último lote importado, no confirmación de que el empleador siga contratando. Con paginación limitada, un anuncio puede salir del lote sin estar cerrado.
- La expiración de Himalayas se aplica al leer los datos. El seguimiento conserva acceso a registros fuera del radar.
- Cada proveedor se procesa secuencialmente. Un registro inválido puede hacer fallar el lote completo del proveedor; se preserva su lote anterior. No hay cuarentena por registro.
- El bloqueo de sincronización es por proceso; no ejecutar CLI y servidor sincronizando a la vez. No hay cola, scheduler, reintento exponencial ni tratamiento específico de `Retry-After`.
- Los fallos permiten otro intento a partir de 60 segundos; las cargas correctas respetan `interval_hours`.
- La API entrega todas las descripciones al navegador; los filtros son locales. Conviene paginar y filtrar en servidor antes de ampliar mucho el volumen.
- El score solo cuenta palabras clave. El nivel se infiere del título. La señal Colombia no confirma condiciones migratorias, experiencia ni contratación. Los salarios permanecen en texto.
- Formularios de fechas y campos requieren validación más estricta del lado servidor antes de uso multiusuario. No hay historial de cambios de estado, recordatorios ni recuperación de una versión anterior de notas.
- El servidor estándar de Python es solo local. No hay autenticación, protección completa contra DNS rebinding, TLS, separación de usuarios ni endurecimiento de producción. No cambiar el bind a `0.0.0.0` para publicarlo sin rediseñar esa capa.
- Las escrituras comprueban Origin cuando está presente y exigen JSON; esto no reemplaza autenticación ni una revisión de seguridad para despliegue.
- La base personal y los anuncios importados no están versionados. El repositorio contiene código y configuración, no los datos de búsqueda del usuario.

## Próximas tareas recomendadas

1. **Calidad y cobertura Colombia:** ampliar empresas ATS con presencia local; resolver el 403 de Get on Board por vías documentadas y evaluar Jooble con credenciales autorizadas. Criterio: ofertas verificables de Bogotá y restricciones geográficas claras.
2. **Ingesta resistente:** separar adaptadores, validar esquema, aislar registros inválidos, guardar historial de ejecuciones y distinguir retirado, vencido y fuera del lote. Criterio: un fallo parcial no altera datos válidos ni etiqueta ofertas como cerradas sin evidencia.
3. **Datos y rendimiento:** paginación de API, pruebas HTTP, perfiles de habilidades configurables y migraciones de base. Criterio: filtros consistentes y seguimiento preservado con mayor volumen.
4. **Flujo profesional:** fechas de seguimiento, historial de etapas y métricas de respuestas/entrevistas. Freelance y eventos siguen siendo manuales en este MVP.
5. **Producción, cuando se decida:** autenticación, autorización por usuario, base gestionada, servidor de producción, secretos y despliegue. Evaluar la migración al stack inicialmente propuesto sin perder contratos ni pruebas.
6. **Integraciones posteriores:** eventos/freelance con acceso válido, alertas y borradores sociales revisables. No están implementados el envío de candidaturas ni las publicaciones en redes.

## Forma de colaborar

Crear una rama por cambio, mantener tests de regresión relevantes y describir validación en la PR. No subir bases SQLite, `.env`, credenciales, CVs ni exportaciones personales. No activar una fuente marcada pendiente solo cambiando `enabled`: primero implementar y probar su adaptador y verificar sus condiciones.

El propietario debe dar acceso al compañero por GitHub. Esta entrega no invita automáticamente a ninguna cuenta.
