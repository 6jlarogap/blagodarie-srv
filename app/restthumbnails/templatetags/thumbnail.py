from django.template import Library

from restthumbnails.helpers import get_thumbnail_proxy


register = Library()

@register.simple_tag(takes_context=True)
def thumbnail(context, source, size, method, extension):
    if source:
        return get_thumbnail_proxy(source, size, method, extension)
    return None
