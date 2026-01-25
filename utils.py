

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def get_platform_info(player_id):
    """
    Retourne le nom de la plateforme et l'URL du profil selon l'ID du joueur.
    Steam IDs sont des nombres de 17 chiffres commençant par 7656.
    """
    player_id_str = str(player_id)

    if player_id_str.isdigit() and len(player_id_str) == 17 and player_id_str.startswith('7656'):
        return {
            'platform': 'Steam',
            'url': f'https://steamcommunity.com/profiles/{player_id_str}',
            'icon': 'fab fa-steam'
        }
    else:
        return {
            'platform': 'Epic',
            'url': None,  # Epic n'a pas de profil public accessible par ID
            'icon': 'fas fa-gamepad'
        }

