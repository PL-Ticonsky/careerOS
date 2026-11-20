"""Personal application dashboard, based on recorded actions, never outbound clicks."""
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from career_rules import fold
from workspace import STATES, today

APPLIED_STATES = ('Postulada', 'Entrevista', 'Oferta')


def local_date(timestamp):
    try:
        return datetime.fromisoformat(timestamp.replace('Z', '+00:00')).astimezone(timezone(timedelta(hours=-5))).date().isoformat()
    except (ValueError, TypeError, AttributeError):
        return ''


def report(connect, params):
    def value(key, default=''):
        return params.get(key, [default])[0]
    try:
        limit, offset = int(value('limit', '25')), int(value('offset', '0'))
    except ValueError:
        raise ValueError('Paginación inválida') from None
    if not 1 <= limit <= 100 or not 0 <= offset <= 1000000:
        raise ValueError('Paginación fuera de rango')
    stage, kind, period = value('stage'), value('kind'), value('period')
    if stage not in ('', *STATES) or kind not in ('', 'empleo', 'freelance') or period not in ('', '30', '90'):
        raise ValueError('Filtro de analíticas inválido')
    cutoff = (datetime.fromisoformat(today()).date() - timedelta(days=int(period)-1)).isoformat() if period else ''
    with connect() as c:
        c.execute('BEGIN')
        histories = defaultdict(list)
        for row in c.execute('SELECT opportunity_id,previous,status,changed FROM stage_history ORDER BY id'):
            histories[row['opportunity_id']].append(dict(row))
        rows = c.execute("""SELECT * FROM opportunities WHERE
            json_extract(payload,'$.kind') IN ('empleo','freelance') AND
            (status IN ('Postulada','Entrevista','Oferta') OR applied_date<>'' OR EXISTS(
                SELECT 1 FROM stage_history h WHERE h.opportunity_id=opportunities.id
                AND h.status IN ('Postulada','Entrevista','Oferta')))""").fetchall()
    applications = []
    for row in rows:
        item = json.loads(row['payload'])
        history = histories[row['id']]
        first = next((event['changed'] for event in history if event['status'] == 'Postulada'), '')
        applied = row['applied_date'] or local_date(first)
        if (stage and row['status'] != stage) or (kind and item['kind'] != kind):
            continue
        if cutoff and (not applied or applied < cutoff):
            continue
        if value('query') and fold(value('query')) not in fold(item['title'] + ' ' + item.get('company', '')):
            continue
        last = history[-1] if history else None
        applications.append(dict(id=row['id'], title=item['title'], company=item.get('company',''),
            kind=item['kind'], source=item['source'], status=row['status'], applied_date=applied,
            date_source='manual_or_recorded' if row['applied_date'] else 'history' if first else 'unknown',
            applied_via=row['applied_via'], last_change=last['changed'] if last else '',
            next_action=row['next_action'], due_date=row['due_date'],
            overdue=bool(row['due_date'] and row['due_date'] <= today() and row['status'] not in ('Oferta','Descartada'))))
    applications.sort(key=lambda item: (item['applied_date'], item['last_change'], item['id']), reverse=True)
    stages = Counter(item['status'] for item in applications)
    months = Counter(item['applied_date'][:7] for item in applications if item['applied_date'])
    monthly = []
    current = datetime.fromisoformat(today()).date()
    month_index = current.year * 12 + current.month - 1
    for index in range(month_index - 5, month_index + 1):
        key = f'{index // 12:04d}-{index % 12 + 1:02d}'
        monthly.append({'month': key, 'count': months[key]})
    return {'items': applications[offset:offset+limit], 'total': len(applications), 'offset': offset,
            'limit': limit, 'has_more': offset+limit < len(applications),
            'summary': {'total': len(applications), 'active': stages['Postulada']+stages['Entrevista'],
                        'interviews': stages['Entrevista'], 'offers': stages['Oferta'],
                        'due': sum(i['overdue'] for i in applications),
                        'unknown_date': sum(not i['applied_date'] for i in applications)},
            'stages': [{'stage': stage, 'count': stages[stage]} for stage in STATES if stage != 'Sin guardar' or stages[stage]],
            'monthly': monthly}
