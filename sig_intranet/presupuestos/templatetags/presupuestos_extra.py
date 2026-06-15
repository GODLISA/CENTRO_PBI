from django import template

register = template.Library()


@register.filter
def clp(valor):
    """Formatea 1234567 -> $1.234.567 (formato chileno, sin decimales)."""
    if valor is None:
        return '-'
    try:
        return '$' + f'{int(valor):,}'.replace(',', '.')
    except (TypeError, ValueError):
        return valor
