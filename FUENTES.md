# Catálogo de fuentes de CareerOS

Revisión: 18 de noviembre de 2026. Estado de la implementación, no garantía de disponibilidad futura.

| Fuente | Estado | Acceso y alcance | Referencia oficial |
|---|---|---|---|
| Himalayas | Conector implementado | API sin clave. Hasta 200 resultados recientes para Colombia por actualización; no es todo el catálogo. Conserva applicationLink, fuente, salarios y restricciones horarias. Actualización diaria. | [Referencia](https://himalayas.app/api) |
| Jobicy | Conector implementado | API pública con paginación por cursor. Hasta 1.000 ofertas publicadas en los últimos siete días; salir del feed no significa que la vacante esté cerrada. | [Referencia](https://github.com/Jobicy/remote-jobs-api) |
| Arbeitnow | Conector implementado | API pública. Hasta tres páginas de empleos europeos; remoto no implica elegibilidad desde Colombia. | [Referencia](https://www.arbeitnow.com/blog/job-board-api) |
| We Work Remotely | Conector implementado | RSS oficial de ofertas recientes con atribución y enlaces a WWR. Ventana del feed, no catálogo completo. | [Referencia](https://weworkremotely.com/remote-job-rss-feed) |
| Remote OK | Conector implementado | Feed JSON público, conserva enlace y atribución a Remote OK. Revisar disponibilidad de cada anuncio. | [Referencia](https://remoteok.com/api) |
| Remotive | Conector implementado | API pública. Atribución y enlace a Remotive; datos retrasados 24 horas. Máximo cuatro consultas diarias. | [Referencia](https://github.com/remotive-com/remote-jobs-api) |
| Canonical · Greenhouse | Conector implementado | Portal público por empresa. Añade más empresas en sources.json. | [Referencia](https://docs.greenhouse.io/job-board) |
| Caseware · Lever | Conector implementado | Vacantes del portal de la empresa. Revisar restricciones geográficas. | [Referencia](https://github.com/lever/postings-api) |
| Ashby · Empleos | Conector implementado | Vacantes y remuneración cuando la empresa las publica. | [Referencia](https://developers.ashbyhq.com/docs/public-job-posting-api) |
| LinkedIn Jobs | Manual | Descubrimiento manual. Guarda el enlace original de cada oferta. | [Referencia](https://www.linkedin.com/jobs/) |
| InfoJobs | Pendiente | Pendiente de credenciales y validación de acceso a su API. | [Referencia](https://developer.infojobs.net/documentation/operation-list/index.xhtml) |
| Reddit | Pendiente | Descubrimiento manual; integración pendiente de acceso autorizado. | [Referencia](https://www.reddit.com/r/forhire/) |
| Workana | Manual | Explora proyectos y registra los que te interesen con su enlace original. | [Referencia](https://www.workana.com/jobs) |
| Upwork | Manual | Descubrimiento manual; integración automática pendiente de autorización. | [Referencia](https://www.upwork.com/freelance-jobs/python/) |
| Contra | Manual | Explora proyectos y clientes; seguimiento manual en CareerOS. | [Referencia](https://contra.com/) |
| Devpost | Conector implementado | Catálogo JSON público del sitio: hasta siete páginas de convocatorias abiertas. Organizador, temáticas, fechas y premios; ficha resumida, contacto e inscripción en plataforma. No garantiza costo, requisitos completos ni correo. | [Referencia](https://devpost.com/hackathons) |
| Major League Hacking | Conector implementado | Lee los datos del calendario público de temporada. Solo importa Bogotá presencial u online explícito; puede haber cero eventos compatibles. | [Referencia](https://mlh.io/) |
| Meetup | Manual | Directorio manual. La API GraphQL requiere Meetup Pro y aprobación de OAuth; no está conectada. | [Referencia](https://www.meetup.com/graphql/) |
| Luma | Manual | Directorio manual. API de gestión por calendario con Luma Plus y clave; no ofrece un catálogo global con esa clave. | [Referencia](https://docs.luma.com/reference/getting-started-with-your-api) |
| Get on Board | Conector implementado | API pública sin clave, país Colombia y hasta tres páginas de 120. Conserva atribución y enlaces oficiales. Anuncios de más de 24 horas sin renovar se ocultan del feed activo. | [Referencia](https://www.getonbrd.com/api-doc) |
| Adzuna | Pendiente | API de búsqueda de empleo. Requiere app_id y app_key; validar mercados disponibles antes de asumir cobertura colombiana. | [Referencia](https://developer.adzuna.com/) |
| Jooble | Implementado, falta clave | Conector por Colombia/Bogotá. Se habilita con JOOBLE_API_KEY regional. No se ha probado una clave real en esta instalación. | [Referencia](https://jooble.org/api/about) |
| SmartRecruiters · Talan | Conector implementado | Publicaciones públicas de Talan filtradas por Colombia, con descripción bajo consulta al detalle. La lectura pública verificada funciona sin clave; no se accede a publicaciones internas. | [Referencia](https://developers.smartrecruiters.com/docs/posting-api) |
| Recruitee | Pendiente | API por empresa. Documenta token Careers Site obligatorio desde febrero de 2027; no depender de acceso anónimo. | [Referencia](https://docs.recruitee.com/reference/authentication-1) |
| Freelancer | Conector implementado | Proyectos públicos con descripción, presupuesto, habilidades y datos públicos del cliente. Hasta 300 resultados antes de deduplicar. El nombre/correo pueden estar ocultos; propuesta y contacto en la plataforma. | [SDK oficial](https://github.com/freelancer/freelancer-sdk-python) |
| Ticketmaster Discovery | Pendiente | API de búsqueda de eventos con clave. Cobertura de eventos técnicos y Colombia por validar. | [Referencia](https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/) |
| Eventbrite | Pendiente | Portal oficial localizado; documentación devolvió HTTP 429. Pendiente de revisar acceso y alcance real de búsqueda. | [Referencia](https://www.eventbrite.com/platform/api) |
| The Muse | Pendiente | La antigua documentación redirige a About. No se asume una API pública vigente; requiere nueva validación. | [Referencia](https://www.themuse.com/developers/api/v2) |
| Reed | Pendiente | API de búsqueda británica con clave y autenticación Basic. Revisar permiso para trabajar y ubicación. | [Referencia](https://www.reed.co.uk/developers/jobseeker) |
| Findwork | Pendiente | Portal de desarrolladores requiere iniciar sesión; condiciones y acceso pendientes de verificar. | [Referencia](https://findwork.dev/developers/) |
| USAJOBS | Pendiente | API oficial con clave. Empleo federal de EE. UU.; revisar ciudadanía y elegibilidad antes de priorizarla. | [Referencia](https://developer.usajobs.gov/tutorials/search-jobs) |
| SerpApi · Google Jobs | Conector implementado | Cinco búsquedas para Bogotá/Colombia, una página por búsqueda cada 24 horas. Requiere clave; comprueba cuota antes de consultar. Conserva enlaces de origen y filtra ubicaciones explícitas. | [Referencia](https://serpapi.com/google-jobs-api) |

## Criterios de integración

- Once conectores activos. El resto es un catálogo de investigación y directorios; no se presentan como conexiones activas.
- Los ATS se consultan por empresa. Añadir un proveedor no significa acceder a todas las empresas que lo usan.
- Los feeds y búsquedas paginadas tienen límites explícitos. Fuera del feed no equivale necesariamente a oferta cerrada.
- Se conservan enlaces del proveedor. En agregadores, el enlace puede llevar al anuncio del agregador; no se afirma que sea siempre el sitio del empleador.
- Get on Board devolvió 403; The Muse redirigió su documentación; Eventbrite devolvió 429. No se probaron claves ni cuentas de pago.
- LinkedIn, Reddit, Upwork, Workana, Contra y MLH no tienen ingesta automática en este MVP. No se ha confirmado aquí una API de búsqueda abierta para todos ellos.
- Prioridad siguiente para Colombia: resolver acceso documentado a Get on Board y conseguir credenciales de Jooble; ampliar empresas de Lever, Greenhouse y Ashby.

Los conectores Freelancer y Devpost se comprobaron con respuestas públicas reales el 18 de noviembre de 2026. Devpost expone el catálogo del sitio sin prometer un contrato estable de API; si cambia su estructura, la ingesta registra el error. No se eluden bloqueos ni se extrae contacto privado. Los detalles de un evento pueden requerir consultar sus bases originales.

### Radar ampliado: Bogotá, formación y certificaciones

Conectores `opportunity_web`: AWS User Group Bogotá, programación en Bogotá (Meetup), AWS Security Colombia, cursos gratuitos del portal Bogotá, Oracle University/certificaciones y beneficios de AWS Certification. Leen páginas públicas, sin credenciales ni API privada. Los eventos requieren fechas estructuradas y ubicación compatible. Las promociones y noticias oficiales quedan en una bandeja separada de verificación; no se convierten en inscripciones abiertas ni exámenes gratuitos sin evidencia. Cada catálogo tiene un máximo de páginas por carga y puede fallar si cambia su formato.

Google Places (New) está integrado bajo demanda en Freelance, con clave de entorno, selección por Bogotá y ausencia de sitio web publicado. No se ejecuta dentro de la sincronización general. No tiene resultados reales disponibles sin clave y facturación habilitadas.

## Ampliación local verificada: 20 de noviembre de 2026

Se comprobaron las respuestas JSON de los portales públicos de seis empleadores. Todos reutilizan conectores existentes, habilitados cada seis horas y con filtro por ubicación explícita Colombia/Bogotá. Los conteos son la ventana observada en esta revisión, antes de agrupar, no una garantía de vigencia ni plazas únicas.

| Conexión | Anuncios locales observados | Portal oficial |
|---|---:|---|
| Sezzle · Greenhouse | 50 | https://job-boards.greenhouse.io/sezzle |
| Antenna · Greenhouse | 3 | https://job-boards.greenhouse.io/Antenna |
| Cobre · Greenhouse | 9 | https://job-boards.greenhouse.io/cobre |
| Jeeves · Lever | 14 | https://jobs.lever.co/tryjeeves |
| Coupa · Lever | 6 | https://jobs.lever.co/coupa |
| Bluelight Consulting · Lever | 49 | https://jobs.lever.co/bluelightconsulting |

Los directorios e integraciones pendientes del catálogo no se activan por cambiar su etiqueta. Siguen separados de las conexiones operativas. Esta ampliación aporta vacantes concretas de empleadores; no promete cubrir todo el mercado colombiano.

### Verificación del acceso de noviembre de 2026

La prueba antigua de Get on Board con HTTP 403 dejó de reproducirse para su API pública; se verificaron búsqueda, expansión y paginación y se implementó el adaptador. La documentación HTML puede responder de forma distinta de los endpoints JSON. SmartRecruiters se comprobó con el portal público de Talan; habilitar esta empresa no da cobertura de todas las empresas de la plataforma. El conector de Jooble permanece listo para configurar y no se afirma que esté conectado sin una clave colombiana válida.

MLH: se añadió un lector del calendario público de temporada, sin API privada ni credenciales. La carga verificada de 2027 contiene únicamente eventos presenciales fuera de Bogotá y por tanto aporta cero convocatorias al radar personal en esta revisión. El conector sigue activo para futuras actualizaciones del calendario.

SerpApi: se añadió el adaptador de Google Jobs con clave privada local. El estado de cuenta se consulta sin consumir búsquedas. La carga se limita a cinco búsquedas por día con la configuración inicial; no cambia el plan ni compra créditos. La cobertura depende de los resultados y enlaces devueltos por Google; no garantiza todo LinkedIn ni otros portales.
