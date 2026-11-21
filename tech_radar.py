"""Curated employer radar; membership does not imply startup status."""
import re
from career_rules import fold

COMPANIES = {
    'blend': ('Blend360', ('blend', 'blend360', 'blend 360')),
    'addi': ('Addi', ('addi',)),
    'simetrik': ('Simetrik', ('simetrik',)),
    'yuno': ('Yuno', ('yuno',)),
    'bold': ('Bold', ('bold', 'bold co', 'bold.co')),
    'alegra': ('Alegra', ('alegra', 'alegra com', 'alegra.com')),
    'belvo': ('Belvo', ('belvo',)),
    'kushki': ('Kushki', ('kushki',)),
    'pomelo': ('Pomelo', ('pomelo',)),
    'ontop': ('Ontop', ('ontop',)),
    'platzi': ('Platzi', ('platzi',)),
    'solum-health': ('Solum Health', ('solum health',)),
    'rebill': ('Rebill', ('rebill',)),
    'arq': ('ARQ', ('arq', 'arq finance')),
    'sofka': ('Sofka / Softka', ('sofka', 'sofka technologies', 'sofka technologies sas', 'softka')),
    'epam': ('EPAM', ('epam', 'epam systems', 'epam anywhere', 'epam systems inc')),
    'globant': ('Globant', ('globant',)),
    'endava': ('Endava', ('endava',)),
    'talan': ('Talan', ('talan',)),
    'thoughtworks': ('Thoughtworks', ('thoughtworks', 'thought works')),
    'accenture': ('Accenture', ('accenture',)),
    'nagarro': ('Nagarro', ('nagarro',)),
    'bairesdev': ('BairesDev', ('bairesdev', 'bairesdev llc')),
    'perficient': ('Perficient', ('perficient',)),
    'encora': ('Encora', ('encora',)),
    'neoris': ('NEORIS', ('neoris',)),
    'bluelight': ('Bluelight Consulting', ('bluelight', 'bluelight consulting')),
    'cobre': ('Cobre', ('cobre',)),
    'sezzle': ('Sezzle', ('sezzle',)),
    'jeeves': ('Jeeves', ('jeeves',)),
    'antenna': ('Antenna', ('antenna',)),
    'coupa': ('Coupa', ('coupa', 'coupa software')),
}


def normalized(company):
    return re.sub(r'[^\w]+', ' ', fold(company or '')).strip()


ALIASES = {normalized(alias): key for key, (_, aliases) in COMPANIES.items() for alias in aliases}


def company_id(company):
    return ALIASES.get(normalized(company), '')


def catalog():
    return [{'id': key, 'name': name} for key, (name, _) in COMPANIES.items()]
