from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def kda_total(player):
    kills = player.get('kills', 0)
    deaths = player.get('deaths', 0)
    assists = player.get('assists', 0)
    if deaths == 0:
        return kills + assists
    return round((kills + assists) / deaths, 2)