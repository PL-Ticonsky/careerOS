"""Role and location rules for the temporary call center search."""
import re

from career_rules import fold

SOURCE = 'serpapi-callcenter'
ROLE = re.compile(
    r'\b(?:call\s*cent(?:er|re)s?|contact\s*cent(?:er|re)s?|teleoperador\w*|'
    r'telemercadeo|telemarketing|asesor\w* telefonic\w*|agente\w* telefonic\w*)\b'
)
SERVICE = re.compile(
    r'\b(?:servicio al cliente|atencion al cliente|customer (?:service|support|care)|'
    r'agente bilingue|bilingual agent|asesor\w* bilingue\w*)\b'
)
EMPLOYER = re.compile(r'\b(?:foundever|concentrix|teleperformance|ttec|sutherland|intouchcx|alorica|konecta|atelco|emtele|solvo|bpo)\b')
HYBRID = re.compile(r'\b(?:hibrid[oa]|hybrid|presencial y remot[oa])\b')
ONSITE = re.compile(r'\b(?:presencial(?:es)?|on[ -]?site|en sitio)\b')
REMOTE = re.compile(r'\b(?:remot[oa]s?|remote|work (?:from|at) home|teletrabajo|desde casa)\b')
MODALITY_LABEL = r'(?:modalidad(?: de trabajo)?|tipo de trabajo|work(?:place)? (?:modality|model|location|type))\s*[:–-]?\s*'
REMOTE_ONLY = re.compile(r'\b(?:100\s*%\s*(?:remot[oa]|remote|presencial)|fully remote|completamente remot[oa])\b')
REMOTE_LOCATION = re.compile(r'\b(?:colombia|bogota)\b|^(?:remote|remot[oa])?[\s·,–-]*(?:latam|latin america|south america|worldwide|anywhere in the world)$')


def role(item):
    title = fold(item.get('title', ''))
    return bool(ROLE.search(title) or (
        SERVICE.search(title) and (
            EMPLOYER.search(fold(item.get('company', ''))) or
            ROLE.search(fold(item.get('description', '')))
        )
    ))


def mode(item):
    title = fold(item.get('title', ''))
    description = fold(item.get('description', ''))
    current = item.get('mode', '')
    if current == 'Híbrido' or HYBRID.search(title) or re.search(MODALITY_LABEL + HYBRID.pattern, description):
        return 'Híbrido'
    if ONSITE.search(title):
        return 'Presencial' if not REMOTE.search(title) and current != 'Remoto' else 'Por confirmar'
    if REMOTE.search(title) or current == 'Remoto':
        return 'Remoto'
    evidence = re.search(MODALITY_LABEL + r'(' + ONSITE.pattern + '|' + REMOTE.pattern + ')', description)
    evidence = evidence or REMOTE_ONLY.search(description)
    if evidence:
        return 'Presencial' if ONSITE.search(evidence[0]) else 'Remoto'
    return current


def matches(item, market):
    modality = item.get('mode')
    return role(item) and (
        (modality == 'Presencial' and market == 3) or
        (modality == 'Remoto' and market >= 1 and
         REMOTE_LOCATION.search(fold(item.get('location', '')).strip()) is not None)
    )
