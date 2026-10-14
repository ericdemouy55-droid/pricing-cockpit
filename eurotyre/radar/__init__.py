"""Market Price Radar : observations séparées des grilles tarifaires publiées."""

RETAILERS = ('Norauto', 'Euromaster', 'Feu Vert', 'First Stop')
DEFAULTS = {
    'enabled': False, 'selected_eans': [], 'zone': 'Compiègne',
    'centers': {name: '' for name in RETAILERS},
    'freshness_days': 7, 'method': 'median', 'include_promotions': False,
    'max_price_change': 30,
}


def settings(state):
    from copy import deepcopy
    result = deepcopy(DEFAULTS)
    result.update(state.get('radar', {}))
    result['centers'] = {**DEFAULTS['centers'], **result.get('centers', {})}
    return result
