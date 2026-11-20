# Entrega de CareerOS

CareerOS centraliza oportunidades de empleo IT, seguimiento de candidaturas, freelance y eventos. Sigue siendo una aplicación local de un usuario, independiente de ticonsky.dev. Python estándar, SQLite y JavaScript nativo permiten ejecutarla sin instalar dependencias.

## Inicio para colaborar

1. Lee [README](../README.md), [Arquitectura](ARQUITECTURA.md), [API](API.md) y [Fuentes](../FUENTES.md).
2. Ejecuta `python3 -m unittest discover -s tests -v` y `node --check static/app.js`.
3. Detén una instancia anterior antes de arrancar `python3 app.py`. No mates servidores usados por otra persona.
4. Abre http://127.0.0.1:8765. Un clon empieza vacío: no incluye la base personal.
5. Prueba filtros, favorito, etapa, notas, próxima acción y fecha. Recarga para verificar persistencia.
6. Edita el perfil desde **Perfil y respaldos** y comprueba las razones de coincidencia en el detalle.
7. Prueba recuperación solo con una base temporal: su vista previa explica qué reemplaza y qué conserva.
8. Para el navegador automatizado: instala Playwright y Chromium y ejecuta `python3 tests/run_browser.py`.

## Cambios de esta revisión

- Favoritos independientes de la etapa; historial de transiciones, acciones y fechas.
- Clasificación conservadora de exclusiones geográficas.
- Procedencia por fuente para URLs compartidas; protección frente a altas manuales repetidas.
- Disponibilidad diferenciada entre último lote, fuera del lote, expiración y cierre explícito.
- Búsqueda SQL paginada, detalle bajo demanda y filtros reiniciados al cambiar de sección.
- Perfil configurable y coincidencias explicadas.
- Sugerencias de posibles duplicados sin fusiones automáticas.
- Respaldo versionado y recuperación con validación, vista previa, transacción y copia previa.
- Sincronización en segundo plano, progreso por fuente y exclusión entre procesos.
- Separación de reglas y persistencia en módulos, pruebas HTTP y flujo de navegador aislado.

La base observada antes de estos cambios tenía 2.238 registros de nueve conexiones. Es un dato local de referencia; no garantiza cobertura o disponibilidad actual. El catálogo tiene 32 fuentes/directorios y muchos siguen siendo manuales o pendientes.

## Preservación de datos

La migración v1 conserva anuncios, estados y notas, guarda una copia antes de migrar y no crea transiciones históricas ficticias. Debe arrancarse el código nuevo en todas las instancias que usan la misma base: una instancia antigua desconoce las nuevas procedencias.

Los respaldos JSON nuevos contienen datos personales y son restaurables. El antiguo `/api/export` sigue siendo una exportación de lectura y no tiene el formato del restaurador. No subas bases, copias, archivos de entorno, credenciales, CVs o respaldos a Git. Las copias SQLite automáticas no se eliminan solas; conserva las que necesites y administra su espacio de forma consciente.

## Límites pendientes

- Las sugerencias por empresa/título no prueban identidad; faltan IDs de empleador y normalización de URLs para una deduplicación más precisa.
- Los lotes limitados y feeds recientes no confirman el cierre de ofertas. No existe verificación en vivo de cada enlace.
- Geografía y seniority son inferencias; no verifican permisos laborales. Los salarios con moneda explícita incluyen una estimación en COP, sin mezclar períodos; se conserva el importe original.
- La búsqueda está paginada, pero ciertos filtros y puntuaciones aún recorren textos. Evaluar FTS si el volumen lo justifica.
- No hay notificaciones, recordatorios fuera de la app, programador, reintentos exponenciales ni `Retry-After` específico.
- El progreso es del proceso actual y no se conserva tras reiniciar. El historial de sincronizaciones sí persiste.
- No hay despliegue, cuentas, permisos multiusuario ni autenticación. No publicar el servidor estándar.
- Freelance y eventos tienen ingesta de Freelancer y Devpost, además de captura manual. El contacto privado no se importa y las bases completas pueden no estar en el catálogo resumido. No hay envío automático de candidaturas o mensajes.

## Próxima evolución

Ampliar cobertura local mediante empresas ATS verificadas y accesos documentados. Evaluar el stack multiusuario cuando exista esa necesidad, manteniendo contratos, reglas y pruebas. La incorporación de nuevas fuentes requiere probar su adaptador, atribución, límites y semántica de disponibilidad; no basta con cambiar `enabled`.

Trabaja en una rama por cambio y describe la validación en cada PR. El propietario administra por separado los accesos al repositorio privado.

## Ampliación de proyectos y eventos

Ahora hay once conexiones configuradas. Se añadieron `opportunity_sources.py` y pruebas específicas de proyectos/contacto, fechas, premios frente a costo, paginación, fallos y conservación de datos. El navegador verifica también tarjetas, fichas y formularios de ambas secciones en escritorio y móvil. Las limitaciones de cada plataforma quedan explícitas en el detalle; no se generan CVs ni se envían candidaturas en esta entrega.
