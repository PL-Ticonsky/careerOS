const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
const views = {
  empleo: ['Oportunidades', 'Encuentra tu próximo paso.', 'Oportunidades reales, fuentes claras y un lugar para avanzar.'],
  analytics: ['Analíticas', 'Así avanzan tus procesos.', 'Tus postulaciones, próximos pasos y resultados en un solo lugar.'],
  tracking: ['Postulaciones', 'Cada paso cuenta.', 'Organiza tus candidaturas y decide tu siguiente acción.'],
  freelance: ['Freelance', 'Tu talento, nuevos proyectos.', 'Descubre clientes y lleva el seguimiento de tus propuestas.'],
  evento: ['Eventos y formación', 'Conecta con lo que viene.', 'Meetups, programación, formación y certificaciones para ampliar tus oportunidades.'],
  sources: ['Fuentes de datos', 'Un radar más amplio.', 'Consulta la cobertura y el resultado real de cada conexión.']
};
const filterIds = ['startups', 'callcenter', 'priority', 'query', 'location', 'mode', 'level', 'source', 'salary', 'inactive', 'sort', 'favorite', 'due', 'stage', 'event_type', 'free', 'discovery-only', 'show_saved', 'ungrouped'];
let meta = {sources: [], states: [], stats: {}, history: []};
let groupedDuplicates = 0;
let items = [], total = 0, view = 'empleo', state = {}, requestNumber = 0, searchTimer, pollTimer;
let restoreData = null, restoreSignature = '', restoreRequest = 0, busyPolling = false;
try { state = JSON.parse(localStorage.getItem('careeros.filters.v1')) || {}; } catch { state = {}; }
if (!state || typeof state !== 'object' || Array.isArray(state)) state = {};
if (Object.hasOwn(views, state.view)) view = state.view;

async function api(path, body, options = {}) {
  const attempts = body === undefined ? 2 : 1;
  for (let attempt = 0; attempt < attempts; attempt++) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), body === undefined ? 15000 : 35000);
    try {
      const response = await fetch('/api/' + path, {
        ...options, signal: controller.signal, cache: 'no-store',
        ...(body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
      });
      let result;
      try { result = await response.json(); }
      catch { throw Error('CareerOS devolvió una respuesta incompleta. Vuelve a consultar.'); }
      if (!response.ok) throw Error(result.error || 'No se pudo completar la operación');
      return result;
    } catch (error) {
      if (!(error instanceof TypeError) && error.name !== 'AbortError') throw error;
      if (attempt + 1 < attempts) { await new Promise(resolve => setTimeout(resolve, 500)); continue; }
      const unavailable = Error('La conexión con CareerOS se interrumpió o tardó demasiado. Comprueba que el servidor siga abierto.');
      unavailable.network = true;
      throw unavailable;
    } finally { clearTimeout(timeout); }
  }
}

function notice(message) { $('#notice').textContent = message; }
function sourceName(id) { return meta.sources.find(source => source.id === id)?.name || (id === 'manual' ? 'Registro manual' : id); }
function date(value) {
  if (!value) return 'La fuente no indica la fecha';
  // A calendar date is local; parsing it as midnight UTC changes the day in Colombia.
  const parsed = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? value + 'T12:00:00' : value);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleDateString('es-CO', {day: 'numeric', month: 'short', year: 'numeric'});
}
function storeFilters() {
  state.view = view;
  state[view] = Object.fromEntries(filterIds.map(id => [id, $('#' + id).type === 'checkbox' ? $('#' + id).checked : $('#' + id).value]));
  try { localStorage.setItem('careeros.filters.v1', JSON.stringify(state)); } catch { /* Browsing still works without local storage. */ }
}
function resetFilters() {
  clearTimeout(searchTimer);
  requestNumber++;
  for (const id of filterIds) {
    const field = $('#' + id);
    if (field.type === 'checkbox') field.checked = false;
    else field.value = id === 'sort' ? (view === 'evento' ? 'event' : 'relevance') : '';
  }
}
function restoreFilters() { resetFilters(); }
function renderShell() {
  const labels = views[view];
  $('#breadcrumb').textContent = labels[0]; $('#title').textContent = labels[0]; $('#subtitle').textContent = labels[2];
  document.querySelectorAll('[data-view]').forEach(button => {
    button.classList.toggle('selected', button.dataset.view === view);
    if (button.dataset.view === view) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
  });
  $('#top-search').classList.toggle('hidden', ['sources', 'analytics'].includes(view));
  $('#opportunities').classList.toggle('hidden', ['sources', 'analytics'].includes(view));
  $('#analytics').classList.toggle('hidden', view !== 'analytics');
  $('#stats').classList.toggle('hidden', view === 'analytics' || (view === 'empleo' && $('#callcenter').checked));
  $('#source-list').classList.toggle('hidden', view !== 'sources');
  $('#places-panel').classList.toggle('hidden', view !== 'freelance');
  $('#priority-label').classList.toggle('hidden', view === 'evento');
  $('#priority option[value="low_competition"]').disabled = view !== 'freelance' && view !== 'tracking';
  $('#event-filters').classList.toggle('hidden', view !== 'evento');
  $('#feed-controls').classList.toggle('hidden', view === 'tracking');
  $('#tracking-filters').classList.toggle('hidden', view !== 'tracking');
  const callcenterFilter = view === 'empleo' && $('#callcenter').checked;
  $('#callcenter-toggle').classList.toggle('hidden', view !== 'empleo');
  $('#callcenter-toggle').setAttribute('aria-pressed', String(callcenterFilter));
  if (!$('#sync').disabled) $('#sync').textContent = callcenterFilter ? '↻ Actualizar call center' : '↻ Actualizar fuentes';
  const startupFilter = view === 'empleo' && $('#startups').checked;
  $('#startups-toggle').classList.toggle('hidden', view !== 'empleo');
  $('#startups-toggle').setAttribute('aria-pressed', String(startupFilter));
  const statsKind = startupFilter ? 'startups' : view;
  const stats = ['empleo', 'freelance', 'evento'].includes(view) ? {...meta.stats, ...(meta.stats.by_kind?.[statsKind] || {active: 0, compatible: 0, tracking: 0})} : meta.stats;
  const relevantSources = meta.sources.filter(source => (!['empleo', 'freelance', 'evento'].includes(view) || (source.category || 'empleo') === view) && (!startupFilter || source.tech_radar) && (!source.on_demand || callcenterFilter || view === 'sources'));
  const connected = relevantSources.filter(source => source.enabled && source.run?.success && !source.run?.error).length;
  const selectedSource = $('#source').value;
  $('#source').innerHTML = '<option value="">Todas las fuentes</option><option value="manual">Registro manual</option>' + relevantSources.filter(source => source.enabled).map(source => `<option value="${esc(source.id)}">${esc(source.name)}</option>`).join('');
  $('#source').value = selectedSource;
  $('#level').closest('label').classList.toggle('hidden', view === 'evento');
  $('#salary-label').textContent = view === 'evento' ? 'Costo de inscripción informado' : view === 'freelance' ? 'Presupuesto informado' : 'Salario publicado';
  $('#query').placeholder = view === 'evento' ? 'Busca por evento, organizador o temática…' : view === 'freelance' ? 'Busca por proyecto, necesidad o tecnología…' : 'Busca por cargo, empresa o tecnología…';
  $('#stats').innerHTML = [
    [stats.active || 0, 'En tu radar', 'Presentes en el último lote; revisa la fuente'],
    [stats.compatible || 0, 'Ubicación compatible', 'Requisitos pendientes de revisar'],
    [stats.tracking || 0, 'En seguimiento', `${stats.due || 0} acciones para hoy o pendientes`],
    [connected, 'Fuentes sincronizadas', `${relevantSources.filter(s => s.enabled).length} automáticas · ${relevantSources.length} en catálogo`]
  ].map(([number, title, caption]) => `<div class="stat"><label>${title}</label><strong>${number.toLocaleString('es-CO')}</strong><small>${caption}</small></div>`).join('');
  $('#tracking-summary').innerHTML = view === 'tracking' ? '<p class="section-note">' + ['Postulada', 'Entrevista', 'Oferta', 'Descartada'].map(stage => `${esc(stage)}: ${meta.stats.stages?.[stage] || 0}`).join(' · ') + '</p>' : '';
  $('#discovery').innerHTML = callcenterFilter ? '<p class="section-note">Presencial en Bogotá o remoto compatible con Colombia.</p>' : startupFilter ? '<p class="section-note">Startups y empresas tecnológicas seleccionadas. Puedes combinar este filtro con ubicación, nivel y modalidad.</p>' : view === 'freelance' ? '<p class="section-note">Proyectos que buscan profesionales: descripción, presupuesto, requisitos publicados y contacto del cliente. Cuando la plataforma oculta el contacto, lo indicamos en el detalle.</p>' : view === 'evento' ? '<p class="section-note">Tu radar personal: presenciales en Bogotá y eventos online. Confirma los requisitos de acceso. Activa «Anuncios por verificar» para revisar promociones, formación y certificaciones oficiales cuya vigencia o modalidad falta confirmar; no son inscripciones abiertas confirmadas.</p>' : '';
  if (view === 'sources') renderSources();
}
function renderSourceCard(source) {
  const automatic = !!source.enabled;
  const status = automatic ? source.run?.error ? 'Error de conexión' : source.run?.success ? 'Conectada' : 'Lista para sincronizar' : source.integration_status === 'needs_key' ? 'Conector listo · falta clave' : source.integration_status === 'needs_access' ? 'Requiere acceso y desarrollo' : source.integration_status === 'access_review' ? 'Acceso por verificar' : source.provider === 'manual' ? 'Directorio manual' : 'Pendiente de integración';
  return `<article class="source-card"><span class="tag ${automatic && source.run?.success && !source.run?.error ? 'green' : ''}">${status}</span><h3>${esc(source.name)}</h3><p>${esc(source.note)}</p>${source.queries?.length ? `<details class="source-queries"><summary>Ver búsquedas (${source.queries.length})</summary><ul>${source.queries.map(query => `<li>${esc(query)}</li>`).join('')}</ul></details>` : ''}${publicLink(source.url, 'Visitar fuente ↗')}${source.docs ? ' · ' + publicLink(source.docs, 'Documentación ↗') : ''}${source.setup_url ? ' · ' + publicLink(source.setup_url, 'Solicitar clave de Colombia ↗') : ''}<small>${automatic ? source.run?.success ? `${source.run.count} registros · ${esc(date(source.run.success))}` : 'Aún sin sincronización correcta' : source.integration_status === 'needs_key' ? 'Conector implementado. Pendiente únicamente de configurar la clave.' : source.provider === 'manual' ? 'Consulta externa; guarda los enlaces que te interesen.' : 'No importa ofertas. Requiere validar el acceso o completar la integración.'}</small>${automatic && source.run?.error ? `<small class="error">${esc(source.run.error)}</small>` : ''}</article>`;
}
function renderSources() {
  const local = meta.sources.filter(s => s.enabled && s.market_scope === 'colombia');
  const other = meta.sources.filter(s => s.enabled && s.market_scope !== 'colombia');
  const manual = meta.sources.filter(s => !s.enabled && s.provider === 'manual');
  const ready = meta.sources.filter(s => !s.enabled && s.integration_status === 'needs_key');
  const pending = meta.sources.filter(s => !s.enabled && s.provider !== 'manual' && s.integration_status !== 'needs_key');
  const section = (title, entries) => `<h2 class="history-heading">${title} · ${entries.length}</h2><div class="source-grid">${entries.map(renderSourceCard).join('')}</div>`;
  $('#source-list').innerHTML = '<p class="section-note">Primero las conexiones de Colombia y Bogotá. Solo las conexiones automáticas importan oportunidades al actualizar. Fuera del lote no equivale a vacante cerrada.</p>' + section('Empleo en Colombia y Bogotá', local) + section('Otras conexiones automáticas', other) + (ready.length ? section('Conectores listos para configurar', ready) : '') + `<details class="source-catalog"><summary>Directorios manuales · ${manual.length}</summary><p class="section-note">Accesos para consultar fuera de CareerOS. No cuentan como conexiones.</p><div class="source-grid">${manual.map(renderSourceCard).join('')}</div></details><details class="source-catalog"><summary>Integraciones pendientes · ${pending.length}</summary><p class="section-note">Catálogo de investigación: estas fuentes todavía no traen ofertas.</p><div class="source-grid">${pending.map(renderSourceCard).join('')}</div></details>` + '<h2 class="history-heading">Historial de actualizaciones</h2><div class="history-scroll"><table class="history-table"><thead><tr><th>Fuente</th><th>Finalizó</th><th>Resultado</th><th>Importadas</th><th>Omitidas</th></tr></thead><tbody>' + meta.history.map(run => `<tr><td>${esc(sourceName(run.source))}</td><td>${esc(new Date(run.finished).toLocaleString('es-CO'))}</td><td>${esc({success: 'Completa', partial: 'Parcial', error: 'Error'}[run.outcome])}${run.error ? `<small class="error">${esc(run.error)}</small>` : ''}</td><td>${run.count}</td><td>${run.rejected}</td></tr>`).join('') + '</tbody></table></div>';
}
async function loadMeta() {
  meta = await api('meta');
  const selected = $('#source').value;
  $('#source').innerHTML = '<option value="">Todas las fuentes</option><option value="manual">Registro manual</option>' + meta.sources.filter(s => s.enabled).map(source => `<option value="${esc(source.id)}">${esc(source.name)}</option>`).join('');
  $('#source').value = selected;
  const stage = $('#stage').value;
  $('#stage').innerHTML = '<option value="">Todas las etapas</option>' + meta.states.map(s => `<option>${esc(s)}</option>`).join('');
  $('#stage').value = stage;
  renderShell();
}
function kindLabels(kind) {
  return kind === 'freelance' ? {owner: 'Cliente sin nombre público', detail: 'Ver proyecto →', amount: 'El cliente no informa el presupuesto', action: 'Ver proyecto y presentar propuesta ↗', description: 'Lo que necesita el cliente'}
    : kind === 'evento' ? {owner: 'Organizador no indicado por la fuente', detail: 'Ver evento →', amount: 'La fuente no informa el costo de inscripción', action: 'Ver inscripción ↗', description: 'Información de la convocatoria'}
    : {owner: 'La fuente no indica la empresa', detail: 'Ver oportunidad →', amount: 'La empresa no informa el salario', action: 'Abrir oferta ↗', description: 'Descripción del puesto'};
}
function publicLink(url, label, className = '') {
  try {
    const parsed = new URL(url);
    if (!['https:', 'http:'].includes(parsed.protocol) || parsed.username || parsed.password) return '';
    return `<a class="${className}" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
  } catch { return ''; }
}
function eventPeriod(item) {
  if (item.event_period) return item.event_period;
  if (item.event_date) return date(item.event_date) + (item.event_end_date && item.event_end_date !== item.event_date ? ' – ' + date(item.event_end_date) : '');
  return 'La fuente no informa las fechas';
}
function locationText(item) { if (item.mode === 'Remoto' && item.group_locations?.length > 1) return 'Colombia · ' + item.group_locations.length + ' ubicaciones agrupadas'; return !item.location || item.location === 'No publicada' ? 'La fuente no informa la ubicación' : item.location; }
function amount(item) { if (item.salary_reference?.display) return (item.salary_reference.estimated ? '≈ ' : '') + item.salary_reference.display; return item.kind === 'evento' ? item.cost || item.salary || kindLabels(item.kind).amount : item.salary || kindLabels(item.kind).amount; }
function salaryNote(item) {
  const ref = item.salary_reference;
  if (!ref || item.kind === 'evento') return '';
  if (ref.status === 'converted') return `<p class="section-note salary-reference">Original: ${esc(item.salary)}<br>Estimación en COP · tasa del ${esc(date(ref.updated))} · ${publicLink(ref.provider_url, 'Rates By Exchange Rate API')}</p>`;
  return ref.note ? `<p class="section-note salary-reference">${esc(ref.note)}</p>` : '';
}
function qualityInfo(item, full = false) {
  const quality = item.quality;
  if (!quality || !['empleo', 'freelance'].includes(item.kind)) return '';
  return `<div class="quality-info"><span class="tag ${quality.top ? 'green' : ''}">${esc(quality.label)}</span> <small>Relevancia: ${quality.score} puntos</small><p class="section-note">${(full ? quality.reasons : quality.reasons.slice(0, 3)).map(esc).join(' · ') || 'Sin coincidencias de perfil detectadas'}${full ? '<br>' + esc(quality.note) + '<br>Habilidades: hasta 60 puntos en empleo / 50 en freelance. Ubicación compatible: 25 / 10. Cada preferencia de nivel o modalidad: 5. Freelance: 30 puntos con 0–5 propuestas, 20 con 6–10 y 10 con 11–20; pago verificado: 10. Máximo 100. Buena oferta: al menos 65 puntos, sin diferencias conocidas de nivel o modalidad; empleo exige dos habilidades y ubicación compatible, freelance una habilidad, hasta 10 propuestas y modalidad remota o ubicación compatible. Estos criterios no comparan salarios.' : ''}</p></div>`;
}
function facts(entries) {
  return '<dl class="opportunity-facts">' + entries.filter(([, value]) => value !== '' && value !== undefined && value !== null).map(([label, value]) => `<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join('') + '</dl>';
}
function opportunityFacts(item, full = false) {
  if (item.kind === 'freelance') return facts([
    ['Modalidad del contrato', item.project_type || 'Consulta el tipo de contrato con el cliente'],
    ['Ubicación del cliente', item.client_location],
    ['Fecha límite', item.project_deadline ? date(item.project_deadline) : full ? 'El cliente no especifica un plazo en los datos recibidos' : ''],
    ['Propuestas recibidas', Number.isInteger(item.bid_count) ? item.bid_count : ''],
    ['Pago del cliente', typeof item.payment_verified === 'boolean' ? item.payment_verified ? 'Verificado por Freelancer' : 'Sin verificación publicada por Freelancer' : '']
  ]);
  if (item.kind === 'evento') return facts([
    ['Verificación', item.verification],
    ['Fechas / participación', eventPeriod(item)],
    ['Cierre de inscripción', item.registration_deadline ? date(item.registration_deadline) + ' · confirma la hora en la convocatoria' : ''],
    ['Entrega de proyectos hasta', item.submission_deadline ? date(item.submission_deadline) + ' · confirma la hora en las bases' : ''],
    ['Lugar', item.venue], ['Tipo', item.event_type], ['Premios', item.prizes],
    ['Inscritos en la fuente', full && Number.isInteger(item.participants) ? item.participants : '']
  ]);
  return '';
}
function contactInfo(item) {
  const name = item.contact_name || item.company;
  const email = typeof item.contact_email === 'string' && /^[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+$/.test(item.contact_email) ? item.contact_email : '';
  const emailLink = email ? `<a href="mailto:${encodeURIComponent(email)}">${esc(email)}</a>` : '';
  return `<section class="contact-panel"><h3>${item.kind === 'evento' ? 'Organizador y contacto' : 'Cliente y contacto'}</h3>${name ? `<p><strong>${esc(name)}</strong></p>` : '<p>La fuente no publica el nombre de contacto.</p>'}${emailLink || '<p class="section-note">No hay un correo público en la información recibida.</p>'}${item.contact_phone ? `<p>Teléfono publicado: ${esc(item.contact_phone)}</p>` : ''}${item.contact_note ? `<p class="section-note">${esc(item.contact_note)}</p>` : ''}${publicLink(item.contact_url || item.url, item.contact_channel ? 'Contactar en ' + item.contact_channel + ' ↗' : 'Consultar contacto en la fuente ↗')}</section>`;
}
function renderItems() {
  const noun = view === 'freelance' ? ['proyecto', 'proyectos'] : view === 'evento' ? ['evento', 'eventos'] : ['oportunidad', 'oportunidades'];
  $('#result-count').textContent = `${total.toLocaleString('es-CO')} ${noun[total === 1 ? 0 : 1]} · ${items.length} ${items.length === 1 ? 'visible' : 'visibles'}${groupedDuplicates ? ' · ' + groupedDuplicates + (groupedDuplicates === 1 ? ' anuncio repetido agrupado' : ' anuncios repetidos agrupados') : ''}`;
  $('#list').innerHTML = items.map(item => {
    const labels = kindLabels(item.kind);
    const tags = item.kind === 'evento' ? item.topics || [] : item.required_skills?.length ? item.required_skills : item.skills;
    const extra = item.kind !== 'empleo';
    const metaLine = item.kind === 'evento' ? `${item.mode === 'Remoto' ? 'En línea' : item.mode}` : `${item.mode}${item.kind === 'empleo' ? ' · ' + item.level : ''}`;
    return `<article class="job" data-kind="${esc(item.kind)}"><div class="job-top"><span class="company-icon">${esc(item.company.slice(0, 2).toUpperCase() || '↗')}</span><div><div class="company-name">${item.company_url ? publicLink(item.company_url, item.company || labels.owner) : esc(item.company || labels.owner)}</div><small>${esc(sourceName(item.source))}${item.published ? ' · ' + esc(date(item.published)) : item.kind === 'empleo' ? ' · La fuente no indica la fecha' : ''}</small></div><button class="save" data-save="${item.id}" aria-pressed="${item.favorite}" aria-label="${item.favorite ? 'Quitar de favoritos' : 'Añadir a favoritos'} ${esc(item.title)}">${item.favorite ? '★' : '☆'}</button></div><h3>${esc(item.title)}</h3><div class="meta">⌖ ${esc(locationText(item).length > 110 ? locationText(item).slice(0, 110) + '…' : locationText(item))}<br>${esc(metaLine)}</div>${extra && item.summary ? `<p class="opportunity-summary">${esc(item.summary)}</p>` : ''}<div class="tags">${tags.slice(0, 5).map(skill => `<span class="tag">${esc(skill)}</span>`).join('')}${item.eligibility === 'Compatible por ubicación' ? '<span class="tag green">Ubicación compatible</span>' : ''}${!item.active ? `<span class="tag">${esc(item.availability)}</span>` : ''}${item.status !== 'Sin guardar' ? `<span class="tag green">${esc(item.status)}</span>` : ''}${item.group_count > 1 ? `<span class="tag">${item.group_count} anuncios similares agrupados</span>` : item.duplicate_count ? '<span class="tag">Posible coincidencia · revisar detalle</span>' : ''}</div><div class="salary">${esc(amount(item))}</div>${salaryNote(item)}${qualityInfo(item)}${opportunityFacts(item)}${extra ? `<p class="contact-preview">${item.contact_email ? 'Contacto público disponible en el detalle' : item.contact_channel ? 'Contacto en ' + esc(item.contact_channel) : 'Contacto y datos en el detalle'}</p>` : ''}${item.next_action || item.due_date ? `<p class="next-action">${esc(item.next_action || 'Acción pendiente')}${item.due_date ? '<br>Seguimiento: ' + esc(date(item.due_date)) : ''}</p>` : ''}<div class="card-bottom">${publicLink(item.url, sourceName(item.source) + ' ↗', 'source-link')}<button class="detail-btn" data-detail="${item.id}">${labels.detail}</button></div></article>`;
  }).join('') || `<div class="empty"><h3>No hay ${noun[1]} con estos filtros.</h3><p>Actualiza las fuentes, limpia los filtros o añade una oportunidad con su información y contacto.</p></div>`;
  $('#more').classList.toggle('hidden', items.length >= total);
}

async function search(append = false) {
  clearTimeout(searchTimer);
  const number = ++requestNumber;
  storeFilters();
  renderShell();
  if (view === 'sources') { renderShell(); return; }
  if (view === 'analytics') { await loadAnalytics(append); return; }
  const params = new URLSearchParams({view, limit: '24', offset: String(append ? items.length : 0)});
  for (const id of filterIds) {
    const field = $('#' + id);
    if (['startups', 'callcenter'].includes(id) && view !== 'empleo') continue;
    if ((view === 'evento' && id === 'priority') || (view === 'tracking' && ['show_saved', 'ungrouped'].includes(id))) continue;
    if (field.type === 'checkbox') { if (field.checked) params.set(id === 'discovery-only' ? 'discovery' : id, '1'); }
    else if (field.value) params.set(id === 'stage' ? 'status' : id === 'location' ? 'market' : id, field.value);
  }
  $('#more').disabled = true;
  if (!append) { items = []; $('#list').innerHTML = ''; $('#result-count').textContent = 'Buscando oportunidades…'; $('#more').classList.add('hidden'); }
  try {
    const result = await api('opportunities?' + params);
    if (number !== requestNumber) return;
    items = append ? items.concat(result.items) : result.items;
    total = result.total; groupedDuplicates = result.grouped_duplicates || 0;
    renderItems();
  } catch (error) {
    if (number === requestNumber) { notice(error.message); $('#result-count').textContent = 'No se pudo completar la búsqueda'; }
  } finally { if (number === requestNumber) $('#more').disabled = false; }
}
let analyticsItems = [], analyticsRequest = 0, analyticsTimer;
const analyticsFilters = ['analytics-query', 'analytics-kind', 'analytics-stage', 'analytics-period'];
function resetAnalyticsFilters() {
  clearTimeout(analyticsTimer); analyticsRequest++;
  analyticsFilters.forEach(id => { $('#' + id).value = ''; });
}
function analyticsBars(title, entries) {
  const max = Math.max(1, ...entries.map(entry => entry.count));
  return `<section class="source-card"><h2>${esc(title)}</h2><ul class="analytics-bars">${entries.map(entry => `<li><span>${esc(entry.label)}</span><meter min="0" max="${max}" value="${entry.count}" aria-label="${esc(entry.label)}">${entry.count}</meter><strong>${entry.count}</strong></li>`).join('')}</ul></section>`;
}
async function loadAnalytics(append = false) {
  const number = ++analyticsRequest;
  const params = new URLSearchParams({limit: '25', offset: String(append ? analyticsItems.length : 0)});
  analyticsFilters.forEach(id => { if ($('#' + id).value) params.set(id.replace('analytics-', ''), $('#' + id).value); });
  $('#analytics-more').disabled = true;
  if (!append) { analyticsItems = []; $('#analytics-content').textContent = 'Cargando tus procesos…'; }
  try {
    const data = await api('analytics?' + params);
    if (number !== analyticsRequest || view !== 'analytics') return;
    analyticsItems = append ? analyticsItems.concat(data.items) : data.items;
    const summary = data.summary;
    const cards = [[summary.total,'Postulaciones registradas'],[summary.active,'Procesos abiertos'],[summary.interviews,'En entrevista'],[summary.offers,'Ofertas recibidas'],[summary.due,'Seguimientos para hoy o vencidos']];
    $('#analytics-content').innerHTML = `<div class="stats analytics-stats">${cards.map(([count,label]) => `<div class="stat"><label>${esc(label)}</label><strong>${count}</strong></div>`).join('')}</div>` +
      `<div class="analytics-charts">${analyticsBars('Estado actual de tus procesos', data.stages.map(entry => ({label: entry.stage, count: entry.count})))}${analyticsBars('Postulaciones por mes · últimos 6 meses', data.monthly.map(entry => ({label: new Date(entry.month + '-15T12:00:00').toLocaleDateString('es-CO', {month:'short',year:'numeric'}), count:entry.count})))}</div>` +
      `<p class="section-note">Cifras según los filtros seleccionados. ${summary.unknown_date ? summary.unknown_date + ' procesos sin fecha de postulación; puedes completarla desde el detalle.' : 'Las fechas corresponden a tu registro, no a la publicación del anuncio.'}</p>` +
      (data.total ? `<h2 class="analytics-list-title">Tus procesos · ${data.total}</h2><div class="analytics-table-wrap"><table class="analytics-table"><caption>Postulaciones y próximos pasos</caption><thead><tr><th>Oportunidad</th><th>Postulación</th><th>Estado actual</th><th>Próximo paso</th><th></th></tr></thead><tbody>${analyticsItems.map(item => `<tr><td><strong>${esc(item.title)}</strong><small>${esc(item.company || 'Empresa sin publicar')} · ${item.kind === 'freelance' ? 'Freelance' : 'Empleo'}</small></td><td>${esc(item.applied_date ? date(item.applied_date) : 'Sin fecha registrada')}<small>${esc(item.applied_via || 'Canal sin registrar')}</small></td><td><span class="tag green">${esc(item.status)}</span><small>${item.last_change ? 'Último cambio: ' + esc(date(item.last_change)) : 'Sin cambios registrados'}</small></td><td>${esc(item.next_action || 'Sin próxima acción')}<small class="${item.overdue ? 'error' : ''}">${item.due_date ? 'Seguimiento: ' + esc(date(item.due_date)) + (item.overdue ? ' · Para hoy o pendiente' : '') : 'Sin fecha de seguimiento'}</small></td><td><button class="text-button" data-detail="${item.id}">Ver proceso</button></td></tr>`).join('')}</tbody></table></div>` : `<div class="empty"><h3>${analyticsFilters.some(id => $('#' + id).value) ? 'No hay procesos con estos filtros.' : 'Tu próxima postulación empieza aquí.'}</h3><p>Abre una oportunidad, marca la etapa «Postulada» y guarda el seguimiento. Aquí verás la fecha, la evolución y tus próximos pasos.</p><button class="secondary" data-view="tracking">Ir a Postulaciones</button></div>`);
    $('#analytics-more').classList.toggle('hidden', !data.has_more);
  } catch (error) {
    if (number === analyticsRequest && view === 'analytics') { $('#analytics-content').textContent = error.message; $('#analytics-more').classList.add('hidden'); }
  } finally { if (number === analyticsRequest) $('#analytics-more').disabled = false; }
}
analyticsFilters.forEach(id => $('#' + id).addEventListener('input', () => {
  clearTimeout(analyticsTimer); analyticsRequest++;
  analyticsTimer = setTimeout(() => loadAnalytics(), id === 'analytics-query' ? 250 : 0);
}));
$('#analytics-reset').onclick = () => { resetAnalyticsFilters(); loadAnalytics(); };
$('#analytics-more').onclick = () => loadAnalytics(true);
async function refresh() { await loadMeta(); await search(); }
let detailNumber = 0;
async function detail(id) {
  const number = ++detailNumber;
  const item = await api('item?id=' + encodeURIComponent(id));
  if (number !== detailNumber) return;
  const labels = kindLabels(item.kind);
  const extra = item.kind !== 'empleo';
  const groupedIds = new Set((item.grouped_variants || []).map(variant => variant.id));
  item.duplicates = item.duplicates.filter(variant => !groupedIds.has(variant.id));
  const topics = item.kind === 'evento' ? item.topics || [] : item.required_skills || [];
  $('#detail-body').innerHTML = `<p class="overline">${esc(sourceName(item.source))}</p><h2>${esc(item.title)}</h2><p>${item.company_url ? publicLink(item.company_url, item.company || labels.owner) : esc(item.company || labels.owner)} · ${esc(item.mode === 'Remoto' && item.kind === 'evento' ? 'En línea' : item.mode)}</p><p class="meta">${esc(locationText(item))} · ${esc(item.availability)}</p><p><strong>${esc(amount(item))}</strong></p>${salaryNote(item)}${qualityInfo(item, true)}${opportunityFacts(item, true)}${topics.length ? `<h3>${item.kind === 'evento' ? 'Temáticas' : 'Habilidades solicitadas'}</h3><div class="tags">${topics.map(topic => `<span class="tag">${esc(topic)}</span>`).join('')}</div>` : ''}<p class="section-note">${esc(item.eligibility)}. ${item.kind === 'evento' ? 'Confirma las condiciones de participación y la zona horaria en la convocatoria.' : 'Confirma país, permisos y horario en el anuncio.'}${item.kind === 'empleo' ? ' Nivel inferido: ' + esc(item.level) + '.' : ''}</p><p class="section-note">Coincidencias con tu perfil: ${esc(item.match_reasons.join(' · ') || 'Ninguna detectada')}. Son señales textuales, no una probabilidad de contratación.</p>${item.discovery_queries?.length ? '<p class="section-note">Encontrada en: ' + item.discovery_queries.map(esc).join(' · ') + '</p>' : ''}${item.published_label ? '<p class="section-note">Antigüedad indicada por la fuente al consultar: ' + esc(item.published_label) + '</p>' : ''}<h3>${labels.description}</h3>${item.description_scope === 'summary' ? '<p class="section-note content-scope">La fuente facilita una ficha resumida. Revisa las bases y condiciones completas en la convocatoria original.</p>' : ''}<div class="description">${esc(item.description || 'La fuente no incluyó una descripción. Puedes consultar el anuncio original.')}</div>${item.requirements ? '<h3>Requisitos</h3><div class="opportunity-text">' + esc(item.requirements) + '</div>' : ''}${item.deliverables ? '<h3>Entregables / qué presentar</h3><div class="opportunity-text">' + esc(item.deliverables) + '</div>' : ''}${extra ? contactInfo(item) : ''}${publicLink(item.kind === 'evento' ? item.registration_url || item.apply_url || item.url : item.apply_url || item.url, labels.action, 'primary')}${item.apply_options?.length > 1 ? '<section class="apply-options"><h3>Dónde postular</h3>' + item.apply_options.map(option => '<p>' + publicLink(option.link, option.title + ' ↗') + '</p>').join('') + '</section>' : ''}<p class="section-note">Fuentes: ${item.sources.map(s => `${esc(sourceName(s.source))} (${s.active ? 'en último lote' : 'fuera del lote'})`).join(' · ')}</p>${item.grouped_variants?.length > 1 ? '<section class="duplicates"><h3>Anuncios agrupados</h3><p class="section-note">Anuncios similares de la misma empresa. Las versiones remotas de Colombia con descripción idéntica se agrupan aunque cambien el título o la ciudad. Cada enlace conserva su seguimiento.</p>' + item.grouped_variants.map(d => `<p>${publicLink(d.url, sourceName(d.source) + ' ↗')} · ${esc(d.title || item.title)} · ${esc(d.location)} · ${esc(d.status)}${d.favorite ? ' · Favorito' : ''} <button class="text-button" data-detail="${d.id}">Ver este anuncio</button></p>`).join('') + '</section>' : ''}${item.duplicates.length ? '<section class="duplicates"><h3>Posibles coincidencias</h3><p class="section-note">Misma empresa y título. Pueden ser vacantes diferentes; no se fusionan automáticamente.</p>' + item.duplicates.map(d => `<button class="text-button" data-detail="${d.id}">${esc(d.title)} · ${esc(d.location)}</button>`).join('<br>') + '</section>' : ''}<hr><form id="tracking-form"><label>${item.kind === 'evento' ? 'Estado de seguimiento' : 'Etapa de candidatura'}<select id="status">${meta.states.map(s => `<option ${s === item.status ? 'selected' : ''}>${esc(s)}</option>`).join('')}</select></label><label>Fecha de postulación<input id="applied-date" type="date" value="${esc(item.applied_date)}"><small>Al pasar a Postulada se registra hoy si dejas esta fecha vacía. Puedes indicar una fecha anterior.</small></label><label>Dónde te postulaste<input id="applied-via" maxlength="200" value="${esc(item.applied_via)}" placeholder="LinkedIn, web de la empresa, correo…"></label><label class="favorite-label"><input id="detail-favorite" type="checkbox" ${item.favorite ? 'checked' : ''}> Favorito</label><label>Próxima acción<input id="next-action" maxlength="500" value="${esc(item.next_action)}" placeholder="Preparar CV, contactar o enviar candidatura"></label><label>Fecha de seguimiento<input id="due-date" type="date" value="${esc(item.due_date)}"></label><label>Notas<textarea id="notes" rows="3" maxlength="10000">${esc(item.notes)}</textarea></label><p id="tracking-error" role="alert"></p><button class="secondary" type="submit">Guardar seguimiento</button></form><h3>Historial de etapas</h3><ul class="timeline">${item.timeline.map(event => `<li>${esc(event.previous)} → <strong>${esc(event.status)}</strong> · ${esc(new Date(event.changed).toLocaleString('es-CO'))}</li>`).join('') || '<li>Sin cambios registrados. El historial comienza con tus próximos cambios.</li>'}</ul>`;
  $('#tracking-form').onsubmit = async event => {
    event.preventDefault();
    const button = event.submitter; button.disabled = true;
    try {
      await api('status', {id, status: $('#status').value, favorite: $('#detail-favorite').checked, notes: $('#notes').value, next_action: $('#next-action').value, due_date: $('#due-date').value, ...($('#status').value === 'Postulada' && item.status !== 'Postulada' && !$('#applied-date').value ? {} : {applied_date: $('#applied-date').value}), applied_via: $('#applied-via').value});
      $('#detail').close(); notice('Seguimiento guardado.'); await refresh();
    } catch (error) { $('#tracking-error').textContent = error.message; } finally { button.disabled = false; }
  };
  if (!$('#detail').open) $('#detail').showModal();
}
document.addEventListener('click', async event => {
  const button = event.target.closest('button');
  if (!button) return;
  try {
    if (button.dataset.view) {
      view = button.dataset.view; resetFilters(); resetAnalyticsFilters(); renderShell(); await search();
    }
    if (button.dataset.detail) await detail(button.dataset.detail);
    if (button.dataset.save) {
      button.disabled = true;
      const item = items.find(item => item.id === button.dataset.save);
      await api('status', {id: item.id, favorite: !item.favorite});
      notice(item.favorite ? 'Quitada de favoritos. La etapa de candidatura se conserva.' : 'Guardada en Postulaciones; se oculta del feed.');
      await refresh();
    }
    if (button.classList.contains('close')) button.closest('dialog').close();
    if (button.dataset.mode) { $('#mode').value = button.dataset.mode; await search(); }
  } catch (error) { notice(error.message); } finally { if (button.dataset.save) button.disabled = false; }
});
for (const [id, other] of [['startups', 'callcenter'], ['callcenter', 'startups']]) {
  $('#' + id + '-toggle').onclick = () => {
    const field = $('#' + id);
    field.checked = !field.checked;
    if (field.checked) $('#' + other).checked = false;
    $('#source').value = '';
    search();
  };
}
$('#reset').onclick = () => { resetFilters(); search(); };
filterIds.forEach(id => $('#' + id).addEventListener('input', () => {
  // Invalidate a pending request immediately, including during the debounce.
  requestNumber++; clearTimeout(searchTimer); storeFilters();
  searchTimer = setTimeout(() => search(), id === 'query' ? 250 : 0);
}));
$('#more').onclick = () => search(true);
$('#apply-profile').onclick = () => {
  const location = (meta.profile.location || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  $('#location').value = /\bbogota\b/.test(location) ? 'bogota' : /\bcolombia\b/.test(location) ? 'colombia' : ''; $('#mode').value = meta.profile.mode; $('#level').value = meta.profile.level;
  search();
};
let syncConnectionLost = false, syncReconnects = 0;
async function pollSync(initial = false) {
  if (busyPolling) { pollTimer = setTimeout(() => pollSync(initial), 250); return; }
  busyPolling = true;
  clearTimeout(pollTimer);
  try {
    const progress = await api('sync/progress');
    syncConnectionLost = false; syncReconnects = 0;
    $('#sync').disabled = progress.running;
    $('#sync').textContent = progress.running ? `↻ ${progress.completed}/${progress.total} fuentes` : view === 'empleo' && $('#callcenter').checked ? '↻ Actualizar call center' : '↻ Actualizar fuentes';
    $('#sync-progress').classList.toggle('hidden', !progress.running);
    $('#sync-progress').textContent = progress.running ? `Actualizando: ${progress.current ? sourceName(progress.current) : 'preparando fuentes'} · ${progress.completed} de ${progress.total} terminadas. Puedes seguir explorando.` : '';
    if (progress.running) pollTimer = setTimeout(() => pollSync(), 1000);
    else if (!initial) {
      const errors = progress.results.filter(r => r.error).length;
      const rejected = progress.results.reduce((count, run) => count + (run.rejected || 0), 0);
      notice(progress.error ? 'La actualización se interrumpió: ' + progress.error : `Actualización terminada: ${errors} fuentes con error · ${rejected} registros omitidos. Consulta el historial de fuentes.`);
      await refresh();
    }
  } catch (error) {
    $('#sync').disabled = false; $('#sync').textContent = '↻ Consultar actualización';
    if (error.network) {
      syncConnectionLost = true; syncReconnects++;
      $('#sync-progress').classList.remove('hidden');
      $('#sync-progress').textContent = 'Conexión interrumpida. Reintentando consultar el progreso; la actualización puede seguir trabajando.';
      pollTimer = setTimeout(() => pollSync(initial), Math.min(1000 * 2 ** Math.min(syncReconnects, 4), 10000));
    } else notice('No se pudo consultar el progreso: ' + error.message);
  } finally { busyPolling = false; }
}
$('#sync').onclick = async () => {
  $('#sync').disabled = true;
  try {
    if (!syncConnectionLost) await api('sync/start', {callcenter: view === 'empleo' && $('#callcenter').checked});
    await pollSync();
  } catch (error) {
    $('#sync').disabled = false;
    if (error.network) { syncConnectionLost = true; notice('Comprobando si la actualización empezó…'); await pollSync(); }
    else notice(error.message);
  }
};
$('#add').onclick = () => {
  $('#manual-form').elements.kind.value = ['evento', 'freelance'].includes(view) ? view : 'empleo';
  updateManualFields();
  $('#form-error').textContent = ''; $('#manual').showModal();
};
function updateManualFields() {
  const kind = $('#manual-form').elements.kind.value;
  for (const [selector, visible] of [['.extra-field', kind !== 'empleo'], ['.event-field', kind === 'evento'], ['.freelance-field', kind === 'freelance']]) {
    document.querySelectorAll(selector).forEach(label => {
      label.classList.toggle('hidden', !visible);
      label.querySelectorAll('input,textarea,select').forEach(field => { field.disabled = !visible; });
    });
  }
  $('#manual-amount-label').textContent = kind === 'evento' ? 'Costo de inscripción' : kind === 'freelance' ? 'Presupuesto y moneda' : 'Salario y período';
}
$('#manual-form').elements.kind.onchange = updateManualFields;
$('#manual-form').onsubmit = async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true;
  try {
    const result = await api('manual', Object.fromEntries(new FormData(event.target)));
    event.target.reset(); $('#manual').close(); await refresh();
    notice(result.duplicate ? 'Este enlace ya existe. Conservamos sus datos y seguimiento.' : 'Oportunidad añadida con su enlace original.');
    await detail(result.id);
  } catch (error) { $('#form-error').textContent = error.message; } finally { button.disabled = false; }
};
$('#settings-open').onclick = () => {
  const profile = meta.profile;
  $('#profile-skills').value = profile.skills.join(', '); $('#profile-location').value = profile.location;
  $('#profile-level').value = profile.level; $('#profile-mode').value = profile.mode;
  $('#settings-notice').textContent = ''; $('#settings').showModal();
};
$('#profile-form').onsubmit = async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true;
  try {
    await api('profile', {skills: $('#profile-skills').value.split(',').map(s => s.trim()).filter(Boolean), location: $('#profile-location').value, level: $('#profile-level').value, mode: $('#profile-mode').value});
    $('#settings-notice').textContent = 'Perfil guardado. Las coincidencias ya usan tus preferencias.'; await refresh();
  } catch (error) { $('#settings-notice').textContent = error.message; } finally { button.disabled = false; }
};
$('#backup-download').onclick = async () => {
  try {
    const data = await api('backup');
    const url = URL.createObjectURL(new Blob([JSON.stringify(data)], {type: 'application/json'}));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = `careeros-respaldo-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    $('#settings-notice').textContent = 'Respaldo descargado. Incluye anuncios, notas, favoritos, perfil e historial de etapas.';
  } catch (error) { $('#settings-notice').textContent = error.message; }
};
$('#restore-file').onchange = async event => {
  const number = ++restoreRequest;
  restoreData = null; restoreSignature = ''; $('#restore-confirm').disabled = true; $('#restore-preview').textContent = '';
  const file = event.target.files[0]; if (!file) return;
  try {
    if (file.size > 100000000) throw Error('El respaldo supera el límite de 100 MB.');
    const parsed = JSON.parse(await file.text());
    const preview = await api('restore/preview', parsed);
    if (number !== restoreRequest) return;
    restoreData = parsed; restoreSignature = file.name + ':' + file.lastModified;
    $('#restore-preview').textContent = `${preview.new} nuevas · ${preview.updated} existentes se actualizarán · ${preview.preserved} se conservarán. Se reemplazarán las notas, etapas e historial de las oportunidades coincidentes y el perfil. Antes se guardará una copia de seguridad local.`;
    $('#restore-confirm').disabled = false;
  } catch (error) { if (number === restoreRequest) $('#restore-preview').textContent = 'No se puede restaurar: ' + error.message; }
};
$('#restore-confirm').onclick = async () => {
  if (!restoreData || !restoreSignature) return;
  $('#restore-confirm').disabled = true;
  try {
    const result = await api('restore', restoreData);
    restoreData = null; restoreSignature = ''; $('#restore-file').value = '';
    $('#restore-preview').textContent = `Restauración completada: ${result.new} nuevas y ${result.updated} actualizadas. Copia previa guardada en la carpeta de respaldos local.`;
    await refresh();
  } catch (error) { $('#restore-preview').textContent = error.message; $('#restore-confirm').disabled = false; }
};
async function init() {
  await loadMeta(); restoreFilters(); renderShell(); await search(); await pollSync(true);
}
init().catch(error => notice('No se pudo cargar CareerOS: ' + error.message));

let placesRows = [], placesToken = '', placesQuery = null, placesBusy = false;
async function findPlaces(more = false) {
  if (placesBusy) return;
  placesBusy = true;
  const button = $('#places-search'); button.disabled = true; $('#places-more').disabled = true;
  if (!more) { placesQuery = {query: $('#places-query').value, area: $('#places-area').value}; placesRows = []; placesToken = ''; $('#places-results').innerHTML = ''; }
  $('#places-status').textContent = 'Consultando Google Maps…';
  try {
    const result = await api('places/search', {...placesQuery, page_token: more ? placesToken : ''});
    const seen = new Set(placesRows.map(row => row.place_id));
    placesRows.push(...result.items.filter(row => !seen.has(row.place_id)));
    placesToken = result.next_page_token;
    $('#places-results').innerHTML = placesRows.map((row, index) => `<article class="source-card"><span class="tag">Posible cliente · por verificar</span><h3>${esc(row.name)}</h3><p>${esc(row.address)}</p><p>${esc(row.phone || 'Teléfono no publicado')}</p><p class="section-note">${esc(row.signal)}</p>${publicLink(row.url, 'Ver ficha en Google Maps ↗')}<small>Google Maps${(row.attributions || []).map(a => ' · ' + publicLink(a.providerUri, a.provider || 'Proveedor de datos')).join('')}</small><label class="place-reference">Referencia personal<input id="places-label-${index}" maxlength="200" value="${esc('Prospecto · ' + placesQuery.query + ' · ' + row.place_id.slice(-6))}"></label><button class="text-button" data-save-place="${index}">Guardar prospecto en Freelance</button></article>`).join('');
    $('#places-status').textContent = `${placesRows.length} posibles clientes sin web publicada. Se revisaron ${result.examined} fichas en esta página. ${!placesRows.length ? 'Prueba otro sector o consulta la siguiente página si está disponible.' : 'Verifica sus necesidades antes de contactar.'}`;
  } catch (error) { $('#places-status').textContent = error.message; }
  finally { placesBusy = false; button.disabled = false; $('#places-more').disabled = false; $('#places-more').classList.toggle('hidden', !placesToken); }
}
$('#places-form').addEventListener('submit', event => { event.preventDefault(); findPlaces(); });
$('#places-more').addEventListener('click', () => findPlaces(true));
$('#places-results').addEventListener('click', async event => {
  const button = event.target.closest('[data-save-place]'); if (!button) return;
  const row = placesRows[Number(button.dataset.savePlace)]; if (!row) return;
  button.disabled = true;
  try {
    const saved = await api('places/save', {place_id: row.place_id, label: $('#places-label-' + button.dataset.savePlace).value});
    button.textContent = saved.duplicate ? 'Ya estaba guardado' : 'Prospecto guardado';
    await refresh();
  } catch (error) { notice(error.message); button.disabled = false; }
});

async function loadPlacesStatus() {
  try {
    const result = await api('places/status');
    $('#places-search').disabled = !result.configured;
    $('#places-setup-open').textContent = result.configured ? 'Configuración de Google Places' : 'Configurar Google Places';
    $('#places-status').textContent = result.configured ? 'Google Places configurado. Busca un sector y, si quieres, un barrio de Bogotá. Cada página es una consulta a Google.' : 'Falta conectar Google Cloud. Abre «Configurar Google Places» para preparar el proyecto y guardar tu clave localmente.';
    $('#places-api-key').disabled = result.source === 'environment';
    $('#places-config-save').disabled = result.source === 'environment';
    return result;
  } catch (error) { $('#places-status').textContent = error.message; }
}
$('#places-setup-open').onclick = async () => {
  $('#places-api-key').value = '';
  const result = await loadPlacesStatus();
  $('#places-config-status').textContent = result?.source === 'environment' ? 'El servidor ya usa una clave configurada en su entorno.' : result?.configured ? 'Ya hay una clave guardada. Puedes reemplazarla introduciendo la nueva.' : '';
  $('#places-setup').showModal();
};
$('#places-config-form').onsubmit = async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true;
  try {
    await api('places/configure', {key: $('#places-api-key').value});
    $('#places-api-key').value = '';
    $('#places-config-status').textContent = 'Clave guardada localmente. La primera búsqueda comprobará el acceso a Google.';
    await loadPlacesStatus();
  } catch (error) { $('#places-config-status').textContent = error.message; }
  finally { button.disabled = false; }
};
$('#places-setup').addEventListener('close', () => { $('#places-api-key').value = ''; });
loadPlacesStatus();
