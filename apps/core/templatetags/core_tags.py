from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.simple_tag(takes_context=True)
def puede_acceder(context, modulo):
    """{% puede_acceder 'CONSTRUCCION' as ok %} → True/False según RBAC del usuario (#44)."""
    from apps.core.permissions import user_can_access_modulo
    request = context.get('request')
    user = getattr(request, 'user', None)
    return user_can_access_modulo(user, modulo)


@register.simple_tag(takes_context=True)
def es_admin_rbac(context):
    """True si el usuario es nivel admin (RBAC #44)."""
    from apps.core.permissions import user_es_admin
    request = context.get('request')
    user = getattr(request, 'user', None)
    return user_es_admin(user)
