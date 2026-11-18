# Catálogo de fuentes de CareerOS

Revisión: 17 de noviembre de 2026. Estado de la implementación, no garantía de disponibilidad futura.

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
| Devpost | Manual | Directorio de hackatones. Registra cada evento con fechas y URL de inscripción. | [Referencia](https://devpost.com/hackathons) |
| Major League Hacking | Manual | Calendario oficial de hackatones; registro manual de oportunidades. | [Referencia](https://mlh.io/) |
| Meetup | Manual | Directorio manual. La API GraphQL requiere Meetup Pro y aprobación de OAuth; no está conectada. | [Referencia](https://www.meetup.com/graphql/) |
| Luma | Manual | Directorio manual. API de gestión por calendario con Luma Plus y clave; no ofrece un catálogo global con esa clave. | [Referencia](https://docs.luma.com/reference/getting-started-with-your-api) |
| Get on Board | Pendiente | API pública documentada para empleos de LATAM. La prueba desde este entorno devolvió HTTP 403; integración pendiente, sin intentar eludir el bloqueo. | [Referencia](https://www.getonbrd.com/api-doc) |
| Adzuna | Pendiente | API de búsqueda de empleo. Requiere app_id y app_key; validar mercados disponibles antes de asumir cobertura colombiana. | [Referencia](https://developer.adzuna.com/) |
| Jooble | Pendiente | API de búsqueda por palabras y ubicación; requiere solicitar una clave. Prioridad alta para Colombia. | [Referencia](https://jooble.org/api/about) |
| SmartRecruiters | Pendiente | API por empresa; validar credenciales y alcance de la API de publicaciones antes de activarla. | [Referencia](https://developers.smartrecruiters.com/docs/posting-api) |
| Recruitee | Pendiente | API por empresa. Documenta token Careers Site obligatorio desde febrero de 2027; no depender de acceso anónimo. | [Referencia](https://docs.recruitee.com/reference/authentication-1) |
| Freelancer | Pendiente | Portal oficial de desarrolladores localizado; pendiente de validar autenticación, alcance y condiciones para proyectos freelance. | [Referencia](https://developers.freelancer.com/) |
| Ticketmaster Discovery | Pendiente | API de búsqueda de eventos con clave. Cobertura de eventos técnicos y Colombia por validar. | [Referencia](https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/) |
| Eventbrite | Pendiente | Portal oficial localizado; documentación devolvió HTTP 429. Pendiente de revisar acceso y alcance real de búsqueda. | [Referencia](https://www.eventbrite.com/platform/api) |
| The Muse | Pendiente | La antigua documentación redirige a About. No se asume una API pública vigente; requiere nueva validación. | [Referencia](https://www.themuse.com/developers/api/v2) |
| Reed | Pendiente | API de búsqueda británica con clave y autenticación Basic. Revisar permiso para trabajar y ubicación. | [Referencia](https://www.reed.co.uk/developers/jobseeker) |
| Findwork | Pendiente | Portal de desarrolladores requiere iniciar sesión; condiciones y acceso pendientes de verificar. | [Referencia](https://findwork.dev/developers/) |
| USAJOBS | Pendiente | API oficial con clave. Empleo federal de EE. UU.; revisar ciudadanía y elegibilidad antes de priorizarla. | [Referencia](https://developer.usajobs.gov/tutorials/search-jobs) |
| SerpApi · Google Jobs | Pendiente | Proveedor externo con clave y cuotas. No es una API oficial de Google; validar costo y condiciones antes de conectarla. | [Referencia](https://serpapi.com/google-jobs-api) |

## Criterios de integración

- Nueve conectores activos. El resto es un catálogo de investigación y directorios; no se presentan como conexiones activas.
- Los ATS se consultan por empresa. Añadir un proveedor no significa acceder a todas las empresas que lo usan.
- Los feeds y búsquedas paginadas tienen límites explícitos. Fuera del feed no equivale necesariamente a oferta cerrada.
- Se conservan enlaces del proveedor. En agregadores, el enlace puede llevar al anuncio del agregador; no se afirma que sea siempre el sitio del empleador.
- Get on Board devolvió 403; The Muse redirigió su documentación; Eventbrite devolvió 429. No se probaron claves ni cuentas de pago.
- LinkedIn, Reddit, Upwork, Workana, Contra, Devpost y MLH no tienen ingesta automática en este MVP. No se ha confirmado aquí una API de búsqueda abierta para todos ellos.
- Prioridad siguiente para Colombia: resolver acceso documentado a Get on Board y conseguir credenciales de Jooble; ampliar empresas de Lever, Greenhouse y Ashby.
