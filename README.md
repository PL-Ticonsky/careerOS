# CareerOS

MVP privado de búsqueda y seguimiento profesional, separado de ticonsky.dev. Repositorio: `careerOS`. La carpeta local original se llama `CarrerOS`.

## Entrega a otro desarrollador

Empieza por [la guía de entrega](docs/HANDOFF.md), consulta [la arquitectura](docs/ARQUITECTURA.md) y [el contrato de la API local](docs/API.md). El [catálogo de fuentes](FUENTES.md) distingue conectores implementados de integraciones pendientes.

## Ejecutar

Requiere Python 3.11 o posterior. No necesita instalar paquetes. Node.js es opcional y solo se utiliza para comprobar la sintaxis de JavaScript. En Windows puedes usar `python` en lugar de `python3`.

```bash
git clone https://github.com/PL-Ticonsky/careerOS.git
cd careerOS
python3 app.py
```

Abre http://127.0.0.1:8765. Para otro puerto: `python app.py --port 8766`.

Pulsa **Actualizar fuentes** para traer datos. También puedes ejecutar `python app.py --sync` con el servidor detenido. Hace falta conexión a Internet; las ofertas y notas previamente guardadas siguen disponibles sin conexión. Cada fuente mantiene su intervalo mínimo de consulta.

## Incluido

- Nueve conectores reales: Himalayas, Jobicy, Arbeitnow, We Work Remotely (RSS), Remote OK, Remotive, Greenhouse, Lever y Ashby.
- 32 fuentes/directorios en el catálogo, con estado, documentación y limitaciones: ver [FUENTES.md](FUENTES.md).
- Búsqueda por texto, ubicación, modalidad, nivel, fuente, señal de compatibilidad geográfica y salario publicado.
- Ordenación por coincidencias técnicas, fecha y empresa; carga progresiva de tarjetas.
- Guardados, postulaciones, entrevistas, ofertas y descartadas; notas persistentes.
- Registro manual de empleos, proyectos freelance y eventos con enlace original y fecha.
- Base SQLite local, deduplicación por URL exacta, conservación del seguimiento al refrescar, aislamiento de errores por fuente.
- Se ocultan registros fuera del último lote de cada fuente; siguen accesibles con «Incluir fuera del feed» y en seguimiento. Eso no confirma que estén cerrados. Las ofertas Himalayas vencidas se ocultan automáticamente del radar.
- Frontend adaptable a móvil, navegación por teclado, formularios etiquetados, texto externo escapado y enlaces http(s).

## Alcance de esta versión

Se priorizó un MVP local que funcione sin cuentas, claves ni instalación de dependencias: Python, SQLite y HTML/CSS/JavaScript. Next.js, FastAPI y PostgreSQL quedan como evolución para despliegue multiusuario; no están implementados en esta versión. El servidor está limitado a 127.0.0.1 y no está preparado para exponerse a Internet. No hay despliegue, autenticación multiusuario, notificaciones, tareas programadas, LLM, publicaciones sociales ni envío automático de candidaturas.

Los eventos y freelance se registran manualmente desde sus directorios. No se inventan vacantes ni eventos. Los salarios conservan el texto, moneda y período que publique cada proveedor. No se convierten monedas ni se comparan automáticamente cifras de diferentes períodos.

El nivel se infiere del título. «Compatible por ubicación» es una señal textual, no validación de autorización laboral ni de todos los requisitos. Himalayas también evalúa su restricción horaria con UTC−5. La ordenación técnica cuenta coincidencias de palabras; no representa una probabilidad de contratación ni un análisis de tu CV.

Himalayas importa hasta diez páginas recientes para Colombia (200 resultados). Jobicy hasta cinco páginas de 200 registros del período de siete días. Arbeitnow hasta tres páginas. Las cifras de la interfaz reflejan lo importado, no el total mundial de las plataformas. Las mismas ofertas con URLs diferentes pueden aparecer más de una vez.

## Configuración y datos

`sources.json` contiene la lista de fuentes. Para ampliar un ATS, copia una entrada del proveedor y cambia `id`, `name`, `board`, `company` y `url`. `board` admite letras, números, guion y guion bajo. La documentación del proveedor indica cómo localizar el identificador. Solo activa proveedores implementados.

Los datos personales se guardan en `data/careeros.db`, excluido de Git. Haz una copia de ese archivo con el servidor detenido para respaldar tu seguimiento. `CAREEROS_DB` permite seleccionar otro archivo. Las fuentes con credenciales siguen desactivadas; no pongas secretos en `sources.json`.

Las tipografías se cargan opcionalmente desde Google Fonts; hay una alternativa local del sistema si no hay conexión.

## API local

- `GET /api/data`: oportunidades, estados y estado de fuentes.
- `GET /api/export`: exportación JSON para respaldo personal; no redistribuir feeds de terceros.
- `POST /api/sync`: actualización respetando caché.
- `POST /api/manual`: alta manual.
- `POST /api/status`: estado y notas.

Las escrituras requieren JSON y se rechazan solicitudes de otro origen. No debe ejecutarse `--sync` en paralelo entre varios procesos; el botón sí bloquea sincronizaciones simultáneas dentro del servidor.

## Validación

```bash
python -m unittest discover -s tests -v
node --check static/app.js
```

Pruebas de persistencia, deduplicación, URLs, clasificación geográfica, errores, caché, paginación, expiración y atribución. Pruebas de interfaz realizadas en el navegador local con ofertas reales.
