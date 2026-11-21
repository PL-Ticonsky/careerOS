# CareerOS

Espacio privado de búsqueda y seguimiento profesional, separado de ticonsky.dev. Repositorio: `careerOS`; la carpeta local original se llama `CarrerOS`.

## Ejecutar

Python 3.11 o posterior, sin paquetes adicionales para usar la aplicación:

```bash
python3 app.py
```

Abre http://127.0.0.1:8765. Otro puerto: `python3 app.py --port 8766`. También puedes usar `./iniciar.sh`; en Windows, `python app.py`.

Al actualizar una instalación existente, detén primero el servidor anterior y vuelve a iniciarlo. La primera ejecución conserva los anuncios, estados y notas, guarda una copia SQLite en `data/backups/before-migration-*.db` y aplica la migración versionada. El historial empieza con los próximos cambios de etapa; no se inventan fechas anteriores.

## Qué puedes hacer

- Consultar conectores de empleo y proyectos: Himalayas, Jobicy, Arbeitnow, WWR, Remote OK, Remotive, Greenhouse, Lever, Ashby, Freelancer y Devpost. [Catálogo completo](FUENTES.md): 39 fuentes y directorios, distinguiendo conexiones, registro manual e integraciones pendientes.
- Buscar y filtrar en el servidor, con páginas de 24 tarjetas y descripciones que se cargan al abrir el detalle.
- Volver a tu última sección con los filtros limpios. La ubicación ofrece Todos, Colombia y Bogotá; los filtros se reinician al cambiar de sección. La elección de modo claro u oscuro se conserva localmente.
- Usar favoritos sin cambiar la etapa de una candidatura. Las etapas siguen disponibles: Sin guardar, Guardada, Postulada, Entrevista, Oferta y Descartada.
- Guardar notas, próxima acción y fecha; consultar acciones para hoy o pendientes e historial de etapas en Postulaciones.
- Editar habilidades, nivel, ubicación y modalidad desde **Perfil y respaldos**. La ordenación explica las coincidencias. **Aplicar mis preferencias** aplica los filtros elegidos; guardar un perfil no oculta ofertas.
- Revisar posibles duplicados por empresa y título desde el detalle. No se fusionan automáticamente: pueden corresponder a ubicaciones o plazas distintas.
- Añadir empleos, freelance y eventos manualmente. Un enlace exacto ya existente abre el registro original y conserva sus datos.
- Ver progreso por fuente durante una actualización y consultar su historial de resultados completos, parciales o fallidos.
- Descargar y restaurar respaldos completos desde **Perfil y respaldos**, con vista previa y copia SQLite automática antes de restaurar.

## Fuentes y disponibilidad

Pulsa **Actualizar fuentes**. Se ejecuta en segundo plano y puedes seguir explorando. Cada fuente respeta su intervalo de consulta. `python3 app.py --sync` permite actualizar sin interfaz. Un bloqueo del sistema operativo impide sincronizar o restaurar simultáneamente la misma base desde varios procesos.

Cada anuncio conserva las fuentes que publicaron su URL exacta. Una fuente no desactiva la observación de otra. Los estados de disponibilidad son diferentes:

- **En el último lote:** apareció en la última carga válida; comprueba su disponibilidad en el anuncio.
- **Fuera del lote:** ya no apareció en ese lote; no prueba que esté cerrado.
- **Vencida:** su fecha explícita de expiración pasó.
- **Cierre confirmado:** reservado a datos con evidencia explícita de cierre; la ausencia en un feed nunca lo asigna.

Las cargas con registros defectuosos conservan las observaciones anteriores. Los errores de una fuente no interrumpen las demás. Himalayas consulta hasta 200 resultados recientes para Colombia; Jobicy hasta cinco páginas de 200; Arbeitnow hasta tres páginas. Las cifras reflejan lo importado, no el total de las plataformas.

«Compatible por ubicación» sigue siendo una señal textual conservadora. Las exclusiones, negaciones y restricciones ambiguas quedan por confirmar; Himalayas considera UTC−5. No se comprueban permisos laborales. El nivel se infiere del título y las coincidencias no predicen contratación. Las fechas de seguimiento se evalúan en el día de Bogotá (UTC−5).

Los salarios conservan moneda, período y texto originales, sin conversión. Freelance incorpora proyectos de Freelancer y Eventos incorpora convocatorias de Devpost. Ambos permiten además registro manual con contacto, requisitos y entregables. La sincronización no envía candidaturas ni mensajes.

## Datos y recuperación

La base está en `data/careeros.db`, excluida de Git. `CAREEROS_DB` permite elegir otra ruta. Las copias automáticas se guardan en `backups/` junto a la base elegida.

El nuevo respaldo JSON versión 1 incluye anuncios, procedencias, notas, favoritos, próximas acciones, fechas, perfil e historial de etapas. La recuperación **actualiza las oportunidades con el mismo ID y conserva las que no están en el archivo**. Reemplaza el perfil y el historial de las oportunidades coincidentes. La vista previa explica los cambios antes de ejecutarlos. Si el archivo es inválido, se rechaza antes de escribir. Las escrituras de recuperación se aplican en una transacción.

Los resultados históricos de sincronización y `sources.json` permanecen en la instalación: no forman parte del respaldo personal. El antiguo `/api/export` sigue disponible como exportación de lectura, pero su array no es compatible con el nuevo restaurador. Para una copia integral de SQLite, detén el servidor y copia la base. Para recuperar una copia SQLite, detén el servidor, conserva la base actual y reemplázala por la copia.

No subas bases, respaldos, CVs, credenciales ni notas personales a Git. No pongas secretos en `sources.json`. Las tipografías de Google Fonts son opcionales; existe una alternativa local.

## Alcance

Aplicación local de un usuario: Python estándar, SQLite y JavaScript nativo. El servidor solo escucha en `127.0.0.1`, valida el host local y el origen de las escrituras. No está preparado para publicarse en Internet. No incluye autenticación multiusuario, despliegue, notificaciones automáticas, LLM ni publicaciones sociales.

No hay deduplicación automática de URLs diferentes ni validación en vivo del cierre de cada vacante. La búsqueda SQL evita descargar todos los anuncios, pero todavía recorre textos para ciertos filtros y puntuaciones; un índice de texto completo sería una evolución para volúmenes mayores.

## Validación y colaboración

```bash
python3 -m unittest discover -s tests -v
node --check static/app.js
```

Pruebas de navegador opcionales, con una base temporal y fuentes sintéticas, sin tocar datos personales ni APIs externas:

```bash
python3 -m pip install 'playwright>=1.48,<2'
python3 -m playwright install chromium
python3 tests/run_browser.py
```

El navegador comprueba paginación, reinicio de filtros, persistencia del tema, favoritos, etapas, próximas acciones, perfil, respaldo y recuperación, enlaces repetidos, geografía, sincronización y móvil. GitHub Actions configura las pruebas unitarias/HTTP con Python 3.11 y 3.14 y un trabajo separado de navegador.

Para colaborar, consulta [Entrega](docs/HANDOFF.md), [Arquitectura](docs/ARQUITECTURA.md) y [API local](docs/API.md). Mantén una rama por cambio y pruebas relevantes.

## Proyectos freelance y eventos

**Freelance** muestra tarjetas de proyectos concretos: necesidad del cliente, descripción recibida, presupuesto y moneda, precio fijo/por hora, habilidades solicitadas, ubicación pública del cliente y propuestas recibidas cuando estén disponibles. La ubicación del cliente no se interpreta como restricción del profesional. El detalle distingue el nombre/contacto publicado de los datos que Freelancer mantiene ocultos. El canal de propuesta se conserva en la plataforma; no se envían mensajes.

**Eventos** muestra convocatorias concretas: organizador, temáticas, período de participación, cierre de entregas por fecha, premios, inscripción y contacto disponible. Los premios no se muestran como costo de entrada. Devpost ofrece una ficha resumida, no siempre descripción completa, costo o correo: la interfaz lo explica y conserva la convocatoria original. No se inventa una hora límite ni se interpreta «en línea» como elegibilidad mundial. Las convocatorias cuya fecha final ya pasó se muestran como vencidas al incluir inactivas.

Las estadísticas y fuentes visibles corresponden a la sección actual. Los directorios manuales permanecen en Fuentes de datos y ya no ocupan el lugar de las oportunidades. La captura manual de proyectos/eventos permite guardar persona, correo y teléfono públicos, enlace de contacto, requisitos, entregables, fechas, sede y premios.

Freelancer consulta hasta dos páginas de 50 por cada búsqueda configurada (Python, JavaScript y backend; hasta 300 resultados antes de deduplicar), cada seis horas. Devpost consulta hasta siete páginas del catálogo abierto cada doce horas. Son ventanas de descubrimiento, no catálogos completos. Ambos usan endpoints públicos y pueden cambiar; un bloqueo o cambio de formato conserva los datos anteriores.

## Radar personal de Bogotá y formación

**Eventos y formación** aplica siempre la regla personal: asistencia presencial únicamente en Bogotá; fuera de Bogotá, solo modalidad online explícita. Los eventos híbridos fuera de Bogotá necesitan acceso virtual publicado para entrar como online. Se mantienen los requisitos por confirmar; la modalidad remota por sí sola no acredita elegibilidad. Los registros antiguos fuera de esta regla no se borran y siguen accesibles desde el seguimiento si se guardaron.

Los nuevos conectores leen eventos estructurados de Meetup (AWS Bogotá, Security Colombia y programación en Bogotá) y páginas oficiales de Bogotá, Oracle y AWS. Actualizan con **Actualizar fuentes**, respetando intervalos y conservando datos cuando una página falla. La búsqueda de programación sigue hasta ocho páginas de eventos por consulta: no garantiza cubrir toda la ciudad. Las páginas públicas pueden cambiar o bloquearse; el resultado real queda en Fuentes de datos.

**Anuncios por verificar** separa formación, promociones y certificaciones cuya inscripción, modalidad o vigencia no está confirmada. Incluye los beneficios de certificación AWS y Race to Certification de Oracle. Un curso gratuito no implica un examen gratuito; estos anuncios no se etiquetan como «Gratis confirmado». El ejemplo distrital de formación con Amazon con cierre el 7 de agosto de 2026 queda vencido y requiere **Incluir fuera del lote y vencidas**. El catálogo de cursos gratuitos del Distrito se consulta para descubrir nuevas publicaciones relevantes.

## Prospectos freelance de Google Maps

En **Freelance**, busca un sector y opcionalmente un barrio. La aplicación consulta Places API (New) por páginas de hasta 20 fichas, limita la búsqueda a Bogotá, comprueba la localidad y muestra negocios sin `websiteUri` publicado. La ausencia de web en la ficha no demuestra que no exista una web. No es posible encontrar en Maps negocios ausentes de Maps. No se necesita mostrar un mapa.

La integración necesita `GOOGLE_PLACES_API_KEY` en el entorno del servidor, Places API (New) habilitada y facturación configurada. Google puede cobrar las consultas, especialmente los campos de contacto y web. La clave nunca se envía al navegador ni se guarda en respaldos. Si falta, la interfaz explica la configuración; no genera prospectos ficticios. Configura la variable antes de iniciar `python3 app.py`; no la guardes en `sources.json` ni en Git.

Los resultados permanecen en memoria del navegador hasta guardarlos expresamente como prospectos. **Guardar prospecto en Freelance** conserva el enlace, dirección y teléfono públicos para seguimiento personal y lo marca como favorito. Se identifica como posible cliente, no como oferta de trabajo ni solicitud de contratación. No envía mensajes. Las consultas posteriores no eliminan ni duplican el seguimiento guardado por URL.

## Feed enfocado en Colombia y Bogotá (20 de noviembre de 2026)

- Oportunidades abre en **Colombia y Bogotá**. El selector Mercado permite Bogotá, Colombia, Colombia + remoto compatible o todos los mercados. La ordenación local da prioridad a Bogotá y después a Colombia, con coincidencias técnicas dentro de cada nivel. Los filtros existentes de texto, nivel y modalidad siguen aplicándose; usa Limpiar para recuperar el foco inicial.
- Los anuncios con la misma empresa, título, ubicación, modalidad, tipo y fechas de evento se agrupan antes de paginar. Se muestra una tarjeta y el número de anuncios agrupados. **Mostrar anuncios sin agrupar** permite verlos por separado; el detalle conserva enlaces individuales. No se fusionan registros ni notas. Las ubicaciones o modalidades diferentes siguen separadas para no ocultar plazas distintas.
- El feed oculta favoritos y oportunidades con una etapa distinta de Sin guardar, además de sus variantes agrupables. Se conservan en **Postulaciones**, sin agrupar seguimientos diferentes. **Incluir guardadas y en seguimiento** permite volver a verlas; Solo favoritos también las muestra expresamente. Los descartados salen del feed y permanecen accesibles en Postulaciones.
- Nuevas conexiones directas: **Sezzle, Antenna, Cobre, Jeeves, Coupa y Bluelight Consulting**. Solo importan ubicaciones que mencionan Colombia o Bogotá y pasan la clasificación geográfica conservadora. No se utiliza la ubicación de la empresa para inventar elegibilidad. Consulta cada seis horas.
- Fuentes de datos muestra primero las conexiones locales y luego las demás automáticas. Los directorios manuales y las integraciones pendientes quedan en secciones desplegables separadas; no se presentan como importadores activos.

## Conectores directos adicionales (20 de noviembre de 2026)

**Get on Board · Colombia** ya utiliza su API pública de búsqueda, sin clave, con país `co`, hasta tres páginas de 120 anuncios y expansión de empresa/ciudades. Mantiene enlaces a Get on Board y a la empresa, descripciones y montos publicados; no inventa moneda ni período cuando no están presentes. No importa una ubicación `Remote` como colombiana por sí sola. Los anuncios de esta fuente pasan a **Actualización pendiente** al superar 24 horas desde su lectura y salen del feed activo hasta renovarlos. Se conservan en Postulaciones y con Incluir fuera del lote y vencidas. Usa Actualizar fuentes para renovarlos; el programa no incorpora un programador fuera de la app.

**Talan · Colombia (SmartRecruiters)** utiliza las publicaciones públicas filtradas por Colombia y consulta el detalle para recuperar la descripción. No consulta anuncios internos ni información de candidatos. Es una conexión por empresa, ampliable a otros portales públicos verificados.

**Jooble** tiene el conector implementado y aparece como **Conector listo · falta clave**. Solicita una clave regional en https://co.jooble.org/api/about y configura `JOOBLE_API_KEY` en el entorno del servidor antes de reiniciarlo. `sources()` habilita esta conexión solamente si existe la variable. No la guardes en sources.json ni en respaldos. La clave de otro país no sirve para Colombia. Se buscan desarrollador, Python y datos en Bogotá, con dos páginas de 20 por consulta; hasta 12 consultas por carga, cada doce horas cuando se pulsa Actualizar fuentes. Las consultas pueden consumir cuota. La integración real de Jooble queda pendiente de una clave válida; las pruebas usan respuestas simuladas.

En Fuentes de datos, los conectores implementados pendientes de clave se muestran separados del catálogo todavía sin desarrollar. Las demás fichas explican si falta acceso, verificar la API o desarrollar el adaptador; cambiar una etiqueta no habilita la importación.

**Major League Hacking** también deja de ser un directorio manual: lee el calendario público de temporada. Aplica la regla Bogotá presencial u online explícito. La verificación actual puede dar cero eventos compatibles; una fuente conectada no garantiza convocatorias locales en cada carga. El lector usa los datos publicados por la propia página y registra un fallo si cambia el formato.

## Corrección de duplicados remotos y Google Places (20 de noviembre de 2026)

Las ofertas remotas que mencionan Colombia también se agrupan entre ciudades y variantes de título cuando coinciden empresa, descripción sustancial completa, tecnologías del título, nivel, contrato e importe. No se usa coincidencia aproximada del texto: dos descripciones distintas permanecen separadas. El detalle muestra títulos, ciudades y enlaces de todas las variantes. Guardar cualquiera oculta todo ese grupo del feed; los seguimientos originales permanecen individuales. La agrupación se calcula al consultar, sin migrar ni fusionar registros.

Las lecturas HTTP reintentan una vez ante fallos de conexión; las escrituras no se repiten automáticamente. Si se pierde la respuesta al comenzar una sincronización, la interfaz consulta su progreso para averiguar si empezó. Si falla la consulta, mantiene la observación con espera progresiva hasta diez segundos entre intentos. No da por terminada una importación solo porque falló la red. No se garantiza continuidad si se detiene el servidor: al volver, consulta el estado real.

En Freelance, **Configurar Google Places** abre la guía de Google Cloud: proyecto, facturación, Places API (New) y clave restringida a esa API. La facturación y creación de credenciales se completan en la cuenta de Google del usuario. La clave se introduce en el formulario local; CareerOS la escribe atómicamente en `data/places-private.json` con permisos 0600, fuera de SQLite y del respaldo personal. Una clave GOOGLE_PLACES_API_KEY del entorno tiene prioridad. No se devuelve la clave en ninguna respuesta ni se guarda en localStorage. Se puede consultar inmediatamente después de guardarla, sin reiniciar.

La búsqueda de negocios sin web publicada mantiene el límite de Bogotá y la consulta explícita por página; la selección de campos incluye el token de siguiente página y atribuciones del proveedor. La ficha, dirección y teléfono se muestran durante la consulta. **Guardar prospecto en Freelance** conserva solo el place ID, enlace canónico de Google Maps y referencia personal que escribas; no copia automáticamente nombre, dirección ni teléfono del proveedor a SQLite. Los prospectos guardados quedan en Postulaciones por ser favoritos. No se han efectuado consultas facturables si la instalación no tiene clave y facturación configuradas.

Jooble también admite una clave privada persistida en `data/jooble-private.json` junto a la base configurada, fuera de SQLite y respaldos. JOOBLE_API_KEY tiene prioridad; el estado público nunca devuelve el valor. Se activa al reiniciar y conserva la configuración en inicios posteriores.

## Google Jobs mediante SerpApi

El conector SerpApi se activa cuando existe SERPAPI_API_KEY o una clave privada en `data/serpapi-private.json` junto a la base. La clave no se devuelve en metadatos, respaldos ni mensajes de error. No es una conexión directa a LinkedIn ni la API oficial de Google.

Se configuran cinco búsquedas: desarrollador Python Bogotá, desarrollador backend Bogotá, desarrollador React Bogotá, analista de datos Bogotá y desarrollador junior remoto Colombia. Cada actualización consulta una página por búsqueda (hasta diez resultados por página), con un intervalo mínimo de 24 horas. El plan se comprueba mediante la API gratuita de cuenta antes de consultar; si falta cuota para el lote completo se conserva la carga anterior. No se compran créditos ni se cambia el plan.

Solo se importan ubicaciones explícitas en Colombia o Bogotá. El origen de una búsqueda en Bogotá no acredita la elegibilidad de un anuncio que diga Anywhere. Las ofertas conservan los enlaces de postulación devueltos por Google Jobs; LinkedIn aparece cuando el proveedor lo entrega entre esos enlaces. Varias búsquedas de una misma URL no duplican el registro. Se eliminan parámetros de seguimiento UTM de la identidad, conservando los parámetros funcionales del anuncio.

En Fuentes de datos, Ver búsquedas lista todas las consultas configuradas. El detalle de una oferta muestra las consultas donde apareció y los portales disponibles para postular. Una fecha relativa como Hace 2 días se conserva como antigüedad indicada al consultar; no se transforma en una fecha de publicación inventada. La carga es una ventana de descubrimiento limitada y no todo el catálogo de Google Jobs.

### Salarios en COP y relevancia

El feed y el detalle muestran una estimación en COP conservando el importe original, el período y la fecha de la tasa. Se usa ExchangeRate-API Open Access, sin clave ni pagos, con caché diaria y atribución visible. La tasa es orientativa, no la TRM oficial. Sin moneda explícita o tasa reciente se conserva el original; no se infiere USD por el símbolo $. Los presupuestos fijos y por hora no se convierten en salarios mensuales. El archivo local data/exchange-rates.json no contiene credenciales.

Ordena por «Más relevantes para mí» o filtra «Buenas ofertas», «Con habilidades de mi perfil» y, en freelance, «hasta 10 propuestas». La etiqueta Buena oferta identifica prioridad según habilidades, ubicación y preferencias; en freelance incluye competencia publicada y verificación de pago. No evalúa competitividad salarial ni promete contratación. El detalle muestra los criterios y motivos; actualiza Mi perfil para personalizarlos. Sin dato de propuestas no se considera baja competencia.

### Analíticas de postulaciones

El menú Analíticas muestra postulaciones de empleo y freelance, procesos abiertos, entrevistas, ofertas y seguimientos para hoy o vencidos. Incluye estados actuales, actividad mensual y una tabla con fecha de postulación, canal, estado, último cambio y próxima acción. Se puede filtrar por cargo/empresa, tipo, etapa y últimos 30/90 días. Los filtros se limpian al cambiar de sección.

Al cambiar una oportunidad a Postulada se registra la fecha local de Bogotá; el detalle permite corregirla e indicar el canal de postulación. Se conservan el historial y los datos en los respaldos. Marcar favorito, guardar o visitar un enlace no cuenta como postularse. Los procesos avanzados sin fecha figuran como sin fecha registrada; no se inventa una fecha a partir de la publicación. Los eventos permanecen en el seguimiento general.

### Aplicación de escritorio Linux

Ejecuta `python3 instalar_app.py` desde la carpeta del proyecto para registrar CareerOS en el buscador de aplicaciones del usuario. No requiere sudo y no instala paquetes. Usa GTK 4, PyGObject y WebKitGTK 6 si están disponibles; si faltan, abre el navegador habitual. En este equipo se ofrece una ventana propia con perfil web persistente.

El lanzador arranca `careeros.service` bajo demanda, espera la respuesta local y reutiliza el servidor si ya está abierto. La app es de instancia única. El servidor solo escucha en 127.0.0.1:8765 y sigue disponible al cerrar la ventana; termina con la sesión o con `systemctl --user stop careeros.service`. No se habilita inicio automático al encender. Los enlaces de ofertas se abren en el navegador habitual; las descargas se guardan en Descargas sin sobreescribir archivos existentes.

Pruebas de arranque: `python3 desktop_launcher.py --backend-only` y `python3 desktop_launcher.py --smoke-test`. Para abrir en el navegador: `python3 desktop_launcher.py --browser`. Si mueves la carpeta del proyecto, vuelve a ejecutar el instalador. La app usa la misma base de datos y las mismas claves locales; no las empaqueta ni sube. Apariencia y preferencias del navegador integrado se conservan por separado en ~/.local/share/careeros/webview.

Archivos de integración: ~/.local/share/applications/io.careeros.CareerOS.desktop, iconos en ~/.local/share/icons/hicolor y ~/.config/systemd/user/careeros.service. Para retirar la integración, cierra la app, detén el servicio y elimina esos archivos; conserva el proyecto y su carpeta data para mantener tus oportunidades.

## Filtro Startups y portales oficiales (21 de noviembre de 2026)

Oportunidades incluye un botón **Startups** que combina el radar de startups y empresas tecnológicas seleccionadas con los filtros habituales. No hay una pestaña separada. El filtro se aplica en el servidor antes de agrupar y paginar; favoritos y postulaciones conservan su flujo habitual. `tech_radar.py` contiene nombres y variantes explícitas de empresas, sin clasificarlas por menciones dentro de la descripción.

Se revisaron 19 portales: 17 lectores automáticos y dos accesos manuales. Cuatro lectores ya existían y se incorporaron 13. Los lectores verificados aportaron 211 anuncios antes de agrupar; no son puestos únicos ni una garantía de elegibilidad. La actualización respeta el intervalo de seis horas y se realiza con **Actualizar fuentes**.

Sofka y Alegra utilizan páginas públicas de Teamtailor, con datos estructurados o campos visibles del detalle. Bold utiliza su catálogo público de Recruitee, comprobado sin credenciales en esta fecha; si exige autenticación, la carga falla conservando los registros anteriores. Platzi usa el widget público y detalles de Workable. Solum Health, Rebill y ARQ leen los puestos publicados por cada empresa en YC. Addi, Simetrik, Yuno y Belvo reutilizan los lectores de Ashby y Lever.

Blend360 tiene cobertura parcial: contrasta el listado con dos fichas públicas conocidas. Ambas estaban marcadas inactivas en esta revisión; no se importan como vacantes abiertas. Una carga parcial conserva las observaciones anteriores y se identifica en el historial. Alegra aportó 14 anuncios verificables y seis detalles incompletos; esa carga también se conserva como parcial. Belvo y Kushki devolvieron cero anuncios compatibles verificables.

Pomelo permanece como acceso manual: no se validó un catálogo automático. Ontop ofrece un formulario general de talento; no se presenta como una vacante. Ambos aparecen en Fuentes de datos con su enlace oficial y la limitación correspondiente. No se envían solicitudes ni se crean cuentas automáticamente.
