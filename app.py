import logging
from flask import Flask, request, jsonify, render_template, url_for
from functools import wraps
import datetime

import database
from gamemode import GameMode
from utils import get_platform_info

app = Flask(__name__)
app.config.from_pyfile("config.py", silent=True)

logger = logging.getLogger(__name__)

HISTORIQUE_MAX_LIMIT = 200

# Rendre get_platform_info disponible dans tous les templates
app.jinja_env.globals['get_platform_info'] = get_platform_info


# ================================
# Middleware d'authentification
# ================================

def require_auth(f):
    """
    Décorateur qui vérifie l'authentification HMAC-SHA256 des requêtes.
    Nécessite les headers X-Player-Id et X-Signature.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        player_id = request.headers.get('X-Player-Id')
        signature = request.headers.get('X-Signature')

        logger.debug("[Auth] Endpoint: %s, Player ID: %s", request.endpoint, player_id)

        if not player_id or not signature:
            logger.warning("[Auth] FAILED - Missing headers")
            return jsonify({'error': 'Missing authentication headers'}), 401

        body = request.get_data(as_text=True)

        if not database.verify_hmac_signature(player_id, body, signature):
            logger.warning("[Auth] FAILED - Invalid signature for player %s", str(player_id)[:64])
            return jsonify({'error': 'Invalid signature'}), 401

        logger.debug("[Auth] SUCCESS - Player %s authenticated", str(player_id)[:64])
        request.authenticated_player_id = player_id
        return f(*args, **kwargs)
    return decorated_function

# -------
# BACKEND
# -------

@app.route('/initPlayer', methods=['POST'])
def init_player():
    """
    Initialise ou met à jour un joueur.
    Retourne auth_secret si:
    - C'est un nouveau joueur
    - Le joueur n'avait pas d'auth_secret
    - Le plugin demande explicitement (needs_auth_secret=true) - pour migration
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body must be valid JSON'}), 400
    if 'player_id' not in data or 'player_name' not in data:
        return jsonify({'error': 'Missing params'}), 400

    player_id = data['player_id']
    player_name = data['player_name']
    needs_auth_secret = data.get('needs_auth_secret', False)

    # Vérifier si le joueur avait déjà un auth_secret AVANT la mise à jour
    existing_secret = database.get_player_auth_secret(player_id)

    # Insère ou met à jour le joueur et récupère les infos d'auth
    auth_info = database.insert_or_update_player(player_id, player_name)

    # Construire la réponse
    response = {
        "message": f"player {player_name} ready [{player_id}]",
        "is_hidden": auth_info['is_hidden'],
        "access_token": auth_info['access_token'] if auth_info['is_hidden'] else None
    }

    # Retourner auth_secret si:
    # 1. Nouveau joueur (pas de secret avant)
    # 2. Plugin demande explicitement (migration depuis ancienne version)
    if not existing_secret:
        response["auth_secret"] = auth_info['auth_secret']
        logger.info("[initPlayer] New player %s - returning auth_secret", str(player_id)[:64])
    elif needs_auth_secret:
        response["auth_secret"] = auth_info['auth_secret']
        logger.info("[initPlayer] Plugin requested auth_secret (migration) for %s", str(player_id)[:64])
    else:
        logger.info("[initPlayer] Existing player %s - NOT returning auth_secret", str(player_id)[:64])

    return jsonify(response)


@app.route('/updateMmr', methods=['POST'])
@require_auth
def updateMmr():
    """Met à jour le MMR d'un joueur. Requiert authentification HMAC."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body must be valid JSON'}), 400
    requirements = ['player_id', 'timestamp', 'mmr', 'gamemode_id']
    missing = [r for r in requirements if r not in data]
    if missing:
        return jsonify({'error': 'Missing parameters', 'missing': missing}), 400

    player_id = data['player_id']
    timestamp = data['timestamp']
    mmr = data['mmr']
    gamemode_id = data['gamemode_id']

    # Vérifier que le player_id dans le body correspond à celui authentifié
    if player_id != request.authenticated_player_id:
        return jsonify({'error': 'Player ID mismatch'}), 403

    try:
        GameMode(gamemode_id)
    except (ValueError, KeyError):
        return jsonify({'error': 'Unknown gamemode_id'}), 400

    database.insert_data(player_id, timestamp, gamemode_id, mmr)
    logger.debug("updateMmr called for player_id=%s gamemode=%s", str(player_id)[:64], gamemode_id)
    return jsonify({'message': 'Data received and stored successfully'}), 200


@app.route('/updateHistorique', methods=['POST'])
@require_auth
def updateHistorique():
    """Met à jour l'historique d'un joueur. Requiert authentification HMAC."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body must be valid JSON'}), 400
    requirements = ['player_id', 'timestamp', 'victory', 'mmr_won', 'gamemode_id']
    missing = [r for r in requirements if r not in data]
    if missing:
        return jsonify({'error': 'Missing parameters', 'missing': missing}), 400

    try:
        GameMode(data['gamemode_id'])
    except (ValueError, KeyError):
        return jsonify({'error': 'Unknown gamemode_id'}), 400

    # Paramètres obligatoires
    player_id = data['player_id']
    timestamp = data['timestamp']
    victory = data['victory']
    mmr_won = data['mmr_won']
    gamemode_id = data['gamemode_id']

    # Vérifier que le player_id dans le body correspond à celui authentifié
    if player_id != request.authenticated_player_id:
        return jsonify({'error': 'Player ID mismatch'}), 403

    # Paramètres optionnels (nouvelles stats) - rétrocompatibilité
    goals = data.get('goals')
    assists = data.get('assists')
    saves = data.get('saves')
    shots = data.get('shots')
    score = data.get('score')
    demos = data.get('demos')
    mvp = data.get('mvp')
    team_score = data.get('team_score')
    opponent_score = data.get('opponent_score')
    overtime = data.get('overtime')

    database.insert_history(
        player_id, timestamp, victory, mmr_won, gamemode_id,
        goals=goals, assists=assists, saves=saves, shots=shots,
        score=score, demos=demos, mvp=mvp,
        team_score=team_score, opponent_score=opponent_score, overtime=overtime
    )
    logger.debug("updateHistorique called for player_id=%s", str(player_id)[:64])
    return jsonify({'message': 'Historique mis a jour'}), 200


# ================================
# Endpoints de gestion de visibilité
# ================================

@app.route('/setVisibility', methods=['POST'])
@require_auth
def set_visibility():
    """
    Définit la visibilité du profil d'un joueur.
    Body: {"is_hidden": true/false}
    Retourne: {"is_hidden": bool, "access_token": string|null}
    """
    if 'is_hidden' not in request.json:
        return jsonify({'error': 'Missing is_hidden parameter'}), 400

    is_hidden = bool(request.json['is_hidden'])
    player_id = request.authenticated_player_id

    result = database.set_player_visibility(player_id, is_hidden)
    if result is None:
        return jsonify({'error': 'Player not found'}), 404

    return jsonify({
        'is_hidden': result['is_hidden'],
        'access_token': result['access_token']
    })


@app.route('/getVisibility', methods=['POST'])
@require_auth
def get_visibility():
    """
    Récupère l'état de visibilité du profil d'un joueur.
    Body: {} (vide ou avec player_id pour vérification)
    Retourne: {"is_hidden": bool, "access_token": string|null}
    """
    player_id = request.authenticated_player_id

    result = database.get_player_visibility(player_id)
    if result is None:
        return jsonify({'error': 'Player not found'}), 404

    return jsonify({
        'is_hidden': result['is_hidden'],
        'access_token': result['access_token']
    })


@app.route('/regenerateAccessToken', methods=['POST'])
@require_auth
def regenerate_access_token():
    """
    Régénère le token d'accès d'un joueur (invalide l'ancien lien).
    Retourne: {"access_token": string}
    """
    player_id = request.authenticated_player_id

    new_token = database.regenerate_access_token(player_id)
    if new_token is None:
        return jsonify({'error': 'Player not found'}), 404

    return jsonify({'access_token': new_token})


@app.route('/regenerateAuthSecret', methods=['POST'])
@require_auth
def regenerate_auth_secret():
    """
    Régénère le secret d'authentification d'un joueur.
    Attention: le plugin devra stocker le nouveau secret.
    Retourne: {"auth_secret": string}
    """
    player_id = request.authenticated_player_id

    new_secret = database.regenerate_auth_secret(player_id)
    if new_secret is None:
        return jsonify({'error': 'Player not found'}), 404

    return jsonify({'auth_secret': new_secret})


# --------
# FRONTEND
# --------

@app.route('/install')
def install_page():
    return render_template('install.html')


@app.route('/p/<token>')
def private_profile(token):
    """
    Accède à un profil privé via son token d'accès.
    Redirige vers le profil complet si le token est valide.
    """
    player = database.get_player_by_access_token(token)
    if not player:
        return render_template('erreur.html', error="Lien d'accès invalide ou expiré."), 404

    player_id = player['player_id']
    player_detail = database.get_player_details(player_id)

    historique = database.get_historique(player_id, 10)

    ranks = database.get_all_ranks(player_id)
    if not ranks:
        return render_template('user_no_data.html', player=player_detail)
    gamemode_ids = [rank['gamemode_id'] for rank in ranks]

    # Stats pour le dashboard amélioré
    player_stats = database.get_player_stats(player_id)
    session_stats = database.get_player_session_stats(player_id, hours=24)

    if player_stats and player_stats['total_games'] > 0:
        player_stats['win_rate'] = round((player_stats['wins'] / player_stats['total_games']) * 100, 1)
    else:
        player_stats = player_stats or {}
        player_stats['win_rate'] = 0

    for rank in ranks:
        rank['trend'] = database.get_mmr_trend(player_id, rank['gamemode_id'], last_n=5)
        if rank['max_mmr'] > 0:
            rank['peak_progress'] = round((rank['mmr'] / rank['max_mmr']) * 100, 1)
        else:
            rank['peak_progress'] = 100

    gamemode_id = gamemode_ids[0]
    user_data = database.get_data(player_id, gamemode_id)
    mmr_array = []
    date_array = []
    for row in user_data:
        mmr_array.append(row[0])
        datetime_object = datetime.datetime.fromtimestamp(int(row[1]))
        date_array.append(datetime_object.strftime("%Y-%m-%d %H:%M:%S"))

    return render_template(
        'user.html',
        player=player_detail,
        ranks=ranks,
        gamemode_ids=gamemode_ids,
        historique=historique,
        player_stats=player_stats,
        session_stats=session_stats,
        Gamemode=GameMode,
        datetime=datetime,
        mmr_array=mmr_array,
        date_array=date_array,
        is_private_access=True,
    )


@app.route('/user')
def user():
    player_id = request.args.get('id')
    if not player_id:
        return render_template('erreur.html', error="Paramètre 'id' manquant."), 400
    player_detail = database.get_player_details(player_id)
    if not player_detail:
        return render_template('erreur.html', error="Joueur introuvable."), 404

    # Vérifier si le profil est caché
    if database.is_player_hidden(player_id):
        return render_template('private_profile.html', player=player_detail)

    historique = database.get_historique(player_id, 10)

    ranks = database.get_all_ranks(player_detail['player_id'])
    if not ranks:
        return render_template('user_no_data.html', player=player_detail)
    gamemode_ids = [rank['gamemode_id'] for rank in ranks]

    # Stats pour le dashboard amélioré
    player_stats = database.get_player_stats(player_id)
    session_stats = database.get_player_session_stats(player_id, hours=24)

    if player_stats and player_stats['total_games'] > 0:
        player_stats['win_rate'] = round((player_stats['wins'] / player_stats['total_games']) * 100, 1)
    else:
        player_stats = player_stats or {}
        player_stats['win_rate'] = 0

    for rank in ranks:
        rank['trend'] = database.get_mmr_trend(player_id, rank['gamemode_id'], last_n=5)
        if rank['max_mmr'] > 0:
            rank['peak_progress'] = round((rank['mmr'] / rank['max_mmr']) * 100, 1)
        else:
            rank['peak_progress'] = 100

    gamemode_id = gamemode_ids[0]
    user_data = database.get_data(player_id, gamemode_id)
    mmr_array = []
    date_array = []
    for row in user_data:
        mmr_array.append(row[0])
        datetime_object = datetime.datetime.fromtimestamp(int(row[1]))
        date_array.append(datetime_object.strftime("%Y-%m-%d %H:%M:%S"))

    return render_template(
        'user.html',
        player=player_detail,
        ranks=ranks,
        gamemode_ids=gamemode_ids,
        historique=historique,
        player_stats=player_stats,
        session_stats=session_stats,
        Gamemode=GameMode,
        datetime=datetime,
        mmr_array=mmr_array,
        date_array=date_array,
    )


@app.route('/gamemode')
def load_user():
    player_id = request.args.get('id')
    if not player_id:
        return render_template('erreur.html', error="Paramètre 'id' manquant."), 400

    try:
        gamemode_id = int(request.args.get('gamemode', ''))
    except (ValueError, TypeError):
        return render_template('erreur.html', error="Paramètre 'gamemode' manquant ou invalide."), 400

    try:
        gamemode = GameMode(gamemode_id)
    except (ValueError, KeyError):
        return render_template('erreur.html', error="Mode de jeu inconnu."), 400

    dernieres_24_heures = datetime.timedelta(hours=24)
    maintenant = datetime.datetime.now()
    il_y_a_24_heures = maintenant - dernieres_24_heures
    user_data = database.get_data(player_id, gamemode_id)

    if not user_data:
        return render_template('erreur.html', error="Aucune donnée trouvée pour ce joueur."), 404

    mmr_array = []
    date_array = []
    i_array = []
    today_mmr_array = []
    today_date_array = []
    today_i_array = []
    for i in range(len(user_data)):
        mmr = user_data[i][0]
        timestamp = user_data[i][1]
        datetime_object = datetime.datetime.fromtimestamp(int(timestamp))
        datetime_str = datetime_object.strftime("%Y-%m-%d %H:%M")
        if il_y_a_24_heures <= datetime_object <= maintenant:
            today_mmr_array.append(mmr)
            today_date_array.append(datetime_str)
            today_i_array.append(i)
        else:
            mmr_array.append(mmr)
            date_array.append(datetime_str)
            i_array.append(i)

    object_mmr = {'i_array': i_array, 'date_array': date_array, 'mmr_array': mmr_array}
    object_mmr_today = {'i_array': today_i_array, 'date_array': today_date_array, 'mmr_array': today_mmr_array}

    player_detail = database.get_player_details(player_id)
    player_name = player_detail['player_name'] if player_detail else 'Joueur'
    previous_url = url_for('user', id=player_id)

    return render_template(
        'graph.html',
        previous_url=previous_url,
        object_mmr=object_mmr,
        object_mmr_today=object_mmr_today,
        gamemode_name=gamemode.str_value,
        player_name=player_name,
    )


@app.route('/historique')
def histo_user():
    player_id = request.args.get('id')
    if not player_id:
        return render_template('erreur.html', error="Paramètre 'id' manquant."), 400

    default_limit = 10
    try:
        limit = int(request.args.get('limit', default_limit))
        limit = max(1, min(limit, HISTORIQUE_MAX_LIMIT))
    except (ValueError, TypeError):
        limit = default_limit

    player_detail = database.get_player_details(player_id)
    if not player_detail:
        return render_template('erreur.html', error="Joueur introuvable."), 404

    historique = database.get_historique(player_id, len=limit + 1)
    has_more = len(historique) > limit
    historique = historique[:limit]

    if not historique:
        return render_template('erreur.html', error="Aucun historique trouvé pour ce joueur."), 404

    url_more_histo = url_for('histo_user', id=player_id, limit=limit + default_limit)
    previous_url = url_for('user', id=player_id)

    return render_template(
        'historique.html',
        previous_url=previous_url,
        player=player_detail,
        historique=historique,
        limit=limit,
        has_more=has_more,
        url_more_histo=url_more_histo,
        Gamemode=GameMode,
        datetime=datetime,
    )


@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/players')
def players():
    data = database.get_all_public_players()
    return render_template('players.html', data=data)

@app.route('/download')
def download():
    return render_template('download.html')

@app.errorhandler(404)
def not_found_error(error):
    return render_template('erreur.html', error="Page introuvable (404)."), 404

@app.errorhandler(500)
def internal_server_error(error):
    logger.exception("Internal server error: %s", error)
    return render_template('erreur.html', error="Une erreur interne est survenue. Veuillez réessayer."), 500

# Initialisation de la base au chargement du module (gunicorn --preload l'exécute une seule fois)
database.create_table()

if __name__ == '__main__':
    # Serveur de développement uniquement ; en production : gunicorn (voir Dockerfile)
    app.run(debug=False, port=5000, host='0.0.0.0')
