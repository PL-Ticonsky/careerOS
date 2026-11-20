"""Pure classification rules shared by ingestion and personal search."""
import re
import unicodedata
from datetime import date
from functools import lru_cache

DEFAULT_PROFILE = {
    'skills': ['python', 'sql', 'postgresql', 'fastapi', 'django', 'javascript',
               'typescript', 'react', 'data', 'backend', 'api'],
    'level': '', 'location': '', 'mode': '',
}


def fold(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value).lower())
                   if unicodedata.category(c) != 'Mn')


def eligibility(location, country='Colombia'):
    text = fold(location)
    # Prefer uncertainty when restrictions or negation appear, even if the text
    # also contains a positive country/region keyword. Never infer work permits.
    if re.search(r'\b(except|excluding|exclude[ds]?|not|no|only|restricted|excluding|'
                 r'excepto|exclu\w*|solo|solamente|unicamente|sin)\b', text):
        return 'Por confirmar'
    if re.search(r'\b(colombia|bogota|latam|latin america|south america|worldwide|anywhere|global)\b', text):
        return 'Compatible por ubicación'
    return 'Por confirmar'


@lru_cache(maxsize=100)
def skill_pattern(skills):
    return re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(s) for s in sorted(skills, key=len, reverse=True)) + r')(?!\w)') if skills else None


def matches_folded(text, skills):
    pattern = skill_pattern(tuple(skills))
    found = {m.group(0) for m in pattern.finditer(text)} if pattern else set()
    return [skill for skill in skills if skill in found]


def matches(text, skills):
    return matches_folded(fold(text), skills)


def valid_date(value):
    if value and (not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) or not date.fromisoformat(value)):
        raise ValueError('Fecha inválida; usa AAAA-MM-DD')
    return value


def validate_profile(data):
    if not isinstance(data, dict):
        raise ValueError('Se requiere un perfil')
    skills = data.get('skills', [])
    if not isinstance(skills, list) or len(skills) > 50:
        raise ValueError('Introduce como máximo 50 habilidades')
    clean = []
    for skill in skills:
        if not isinstance(skill, str) or not 1 <= len(skill.strip()) <= 60:
            raise ValueError('Cada habilidad debe tener entre 1 y 60 caracteres')
        skill = fold(skill.strip())
        if skill not in clean:
            clean.append(skill)
    result = {'skills': clean}
    for key, choices in [('level', ['', 'Junior', 'Mid', 'Senior', 'Por confirmar']),
                         ('mode', ['', 'Remoto', 'Híbrido', 'Presencial', 'Por confirmar'])]:
        if data.get(key, '') not in choices:
            raise ValueError(f'Preferencia inválida: {key}')
        result[key] = data.get(key, '')
    location = data.get('location', '')
    if not isinstance(location, str) or len(location) > 200:
        raise ValueError('La ubicación debe ser texto de hasta 200 caracteres')
    result['location'] = location.strip()
    return result


def explain(item, profile):
    skills = matches(item['title'] + ' ' + item.get('description', ''), profile['skills'])
    reasons = [f'Habilidad: {skill}' for skill in skills]
    score = len(skills) * 10
    for key, label in [('level', 'Nivel'), ('mode', 'Modalidad')]:
        if profile[key] and item.get(key) == profile[key]:
            score += 5
            reasons.append(f'{label}: {profile[key]}')
    if profile['location'] and fold(profile['location']) in fold(item.get('location', '')):
        score += 5
        reasons.append(f"Ubicación: {profile['location']}")
    return skills, score, reasons
