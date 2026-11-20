"""Explainable priorities, not hiring probabilities or salary benchmarks."""
from career_rules import explain, fold, eligibility


def assess(item, profile):
    skills, _, _ = explain(item, profile)
    reasons = []
    freelance = item.get('kind') == 'freelance'
    score = min(50 if freelance else 60, len(skills) * 20)
    if skills:
        reasons.append('1 habilidad de tu perfil coincide' if len(skills) == 1 else f'{len(skills)} habilidades de tu perfil coinciden')
    location = fold(item.get('location', ''))
    compatible = eligibility(location) == 'Compatible por ubicación'
    if compatible:
        score += 10 if freelance else 25
        reasons.append('Ubicación compatible con Colombia')
    mismatch = False
    for key in ('level', 'mode'):
        preference, actual = profile.get(key), item.get(key)
        if preference and actual and actual != 'Por confirmar':
            if preference == actual:
                score += 5
                reasons.append('Coincide con tu ' + ('nivel' if key == 'level' else 'modalidad'))
            else:
                mismatch = True
                reasons.append('Revisar: difiere de tu ' + ('nivel' if key == 'level' else 'modalidad'))
    bids = item.get('bid_count')
    known_bids = type(bids) is int and bids >= 0
    if freelance:
        if known_bids:
            score += 30 if bids <= 5 else 20 if bids <= 10 else 10 if bids <= 20 else 0
            reasons.append('1 propuesta publicada en la última consulta' if bids == 1 else f'{bids} propuestas publicadas en la última consulta')
        else:
            reasons.append('La fuente no publica cuántas propuestas hay')
        if item.get('payment_verified') is True:
            score += 10
            reasons.append('Pago del cliente verificado por la plataforma')
    top = (score >= 65 and not mismatch and not item.get('closed') and item.get('active') is not False and
           (bool(skills) and known_bids and bids <= 10 and (item.get('mode') == 'Remoto' or compatible) if freelance else len(skills) >= 2 and compatible))
    if item.get('kind') not in ('empleo', 'freelance'):
        top = False
    return {'score': min(score, 100), 'label': 'Buena oferta' if top else 'Por revisar',
            'top': top, 'matched': bool(skills), 'low_competition': freelance and known_bids and bids <= 10,
            'reasons': reasons,
            'note': 'Prioridad orientativa según tu perfil y los datos publicados; no evalúa si el salario es competitivo ni predice una contratación.'}
