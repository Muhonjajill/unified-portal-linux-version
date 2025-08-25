# core/utils/escalation_constants.py

ESCALATION_TIME_LIMITS = {
    'low': 0.25, #8
    'medium': 0.2, #2
    'high': 0.1, #1
    'critical': 0, #0.5
}

ESCALATION_FLOW = {
    'Tier 1': 'Tier 2',
    'Tier 2': 'Tier 3',
    'Tier 3': 'Tier 4',
    'Tier 4': None,
}