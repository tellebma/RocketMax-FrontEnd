from flask import Flask, request, jsonify, render_template
from functools import wraps
import datetime

import database
from gamemode import GameMode
from utils import get_platform_info

app = Flask(__name__)
app.config.from_pyfile("config.py", silent=True)

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

        print(f"[Auth] Endpoint: {request.endpoint}")
        print(f"[Auth] Player ID: {player_id}")
        print(f"[Auth] Signature: {signature[:16]}..." if signature else "[Auth] Signature: None")

        if not player_id or not signature:
            print(f"[Auth] FAILED - Missing headers")
            return jsonify({'error': 'Missing authentication headers'}), 401

        body = request.get_data(as_text=True)
        print(f"[Auth] Body length: {len(body)}")
        print(f"[Auth] Body: {body[:200]}..." if len(body) > 200 else f"[Auth] Body: {body}")

        if not database.verify_hmac_signature(player_id, body, signature):
            print(f"[Auth] FAILED - Invalid signature")
            return jsonify({'error': 'Invalid signature'}), 401

        print(f"[Auth] SUCCESS - Player {player_id} authenticated")
        # Stocker le player_id authentifié dans la requête
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
    print(f"initPlayer => {request.json}")
    # Vérifie si les paramètres requis sont présents
    if 'player_id' not in request.json or 'player_name' not in request.json:
        return jsonify({'error': 'Missing params'}), 400

    # Récupère les paramètres de la requête
    player_id = request.json['player_id']
    player_name = request.json['player_name']
    needs_auth_secret = request.json.get('needs_auth_secret', False)

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
        print(f"[initPlayer] New player - returning auth_secret")
    elif needs_auth_secret:
        response["auth_secret"] = auth_info['auth_secret']
        print(f"[initPlayer] Plugin requested auth_secret (migration) - returning it")
    else:
        print(f"[initPlayer] Existing player - NOT returning auth_secret")

    return jsonify(response)


@app.route('/updateMmr', methods=['POST'])
@require_auth
def updateMmr():
    """Met à jour le MMR d'un joueur. Requiert authentification HMAC."""
    print(f"updateMmr => {request.json}")
    requirements = [
        'player_id',
        'timestamp',
        'mmr',
        'gamemode_id'
    ]
    missing_param = False
    for r in requirements:
        if r not in request.json:
            print(f"missing params {r}")
            missing_param = True

    if missing_param:
        return jsonify({'error': 'Missing parameters'}), 400

    # Récupère les paramètres de la requête
    player_id = request.json['player_id']
    timestamp = request.json['timestamp']
    mmr = request.json['mmr']
    gamemode_id = request.json['gamemode_id']

    # Vérifier que le player_id dans le body correspond à celui authentifié
    if player_id != request.authenticated_player_id:
        return jsonify({'error': 'Player ID mismatch'}), 403

    if not GameMode(gamemode_id):
        return jsonify({'error': 'Invalid gamemode'}), 400

    # Insère les données dans la base de données
    database.insert_data(player_id, timestamp, gamemode_id, mmr)

    return jsonify({'message': 'Data received and stored successfully'}), 200

@app.route('/updateHistorique', methods=['POST'])
@require_auth
def updateHistorique():
    """Met à jour l'historique d'un joueur. Requiert authentification HMAC."""
    print(f"updateHistorique => {request.json}")
    requirements = [
        'player_id',
        'timestamp',
        'victory',
        'mmr_won',
        'gamemode_id'
    ]
    missing_param = False
    for r in requirements:
        if r not in request.json:
            print(f"missing params {r}")
            missing_param = True

    if missing_param:
        return jsonify({'error': 'Missing parameters'}), 400

    if not GameMode(request.json['gamemode_id']):
        return jsonify({'error': 'Invalid gamemode'}), 400

    # Paramètres obligatoires
    player_id = request.json['player_id']
    timestamp = request.json['timestamp']
    victory = request.json['victory']
    mmr_won = request.json['mmr_won']
    gamemode_id = request.json['gamemode_id']

    # Vérifier que le player_id dans le body correspond à celui authentifié
    if player_id != request.authenticated_player_id:
        return jsonify({'error': 'Player ID mismatch'}), 403

    # Paramètres optionnels (nouvelles stats) - rétrocompatibilité
    goals = request.json.get('goals')
    assists = request.json.get('assists')
    saves = request.json.get('saves')
    shots = request.json.get('shots')
    score = request.json.get('score')
    demos = request.json.get('demos')
    mvp = request.json.get('mvp')
    team_score = request.json.get('team_score')
    opponent_score = request.json.get('opponent_score')
    overtime = request.json.get('overtime')

    database.insert_history(
        player_id, timestamp, victory, mmr_won, gamemode_id,
        goals=goals, assists=assists, saves=saves, shots=shots,
        score=score, demos=demos, mvp=mvp,
        team_score=team_score, opponent_score=opponent_score, overtime=overtime
    )

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

@app.route('/p/<token>')
def private_profile(token):
    """
    Accède à un profil privé via son token d'accès.
    Redirige vers le profil complet si le token est valide.
    """
    player = database.get_player_by_access_token(token)
    if not player:
        return render_template('erreur.html', error="Lien d'accès invalide ou expiré."), 404

    # Afficher le profil complet (même logique que /user mais sans vérifier is_hidden)
    player_id = player['player_id']
    previous_url = request.referrer or None
    player_detail = database.get_player_details(player_id)

    historique = database.get_historique(player_id, 10)

    ranks = database.get_all_ranks(player_id)
    if not ranks:
        return render_template('user_no_data.html', player=player_detail)
    gamemode_ids = [rank['gamemode_id'] for rank in ranks]

    # Stats pour le dashboard amélioré
    player_stats = database.get_player_stats(player_id)
    session_stats = database.get_player_session_stats(player_id, hours=24)

    # Calculer le win rate
    if player_stats and player_stats['total_games'] > 0:
        player_stats['win_rate'] = round((player_stats['wins'] / player_stats['total_games']) * 100, 1)
    else:
        player_stats = player_stats or {}
        player_stats['win_rate'] = 0

    # Ajouter la tendance MMR pour chaque rank
    for rank in ranks:
        rank['trend'] = database.get_mmr_trend(player_id, rank['gamemode_id'], last_n=5)
        if rank['max_mmr'] > 0:
            rank['peak_progress'] = round((rank['mmr'] / rank['max_mmr']) * 100, 1)
        else:
            rank['peak_progress'] = 100

    # Données pour le graphique
    gamemode_id = gamemode_ids[0]
    user_data = database.get_data(player_id, gamemode_id)
    mmr_array = []
    date_array = []
    for data in user_data:
        mmr = data[0]
        mmr_array.append(mmr)
        timestamp = data[1]
        datetime_object = datetime.datetime.fromtimestamp(int(timestamp))
        date_array.append(datetime_object.strftime("%Y-%m-%d %H:%M:%S"))

    return render_template('user.html',
                           previous_url=previous_url,
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
                           is_private_access=True)


@app.route('/user')
def user():
    previous_url = request.referrer or None
    player_id = request.args.get('id')
    player_detail = database.get_player_details(player_id)
    if not player_detail:
        return "Utilisateur non trouvé dans la base de données."

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

    # Calculer le win rate
    if player_stats and player_stats['total_games'] > 0:
        player_stats['win_rate'] = round((player_stats['wins'] / player_stats['total_games']) * 100, 1)
    else:
        player_stats = player_stats or {}
        player_stats['win_rate'] = 0

    # Ajouter la tendance MMR pour chaque rank
    for rank in ranks:
        rank['trend'] = database.get_mmr_trend(player_id, rank['gamemode_id'], last_n=5)
        # Calculer le pourcentage vers le peak
        if rank['max_mmr'] > 0:
            rank['peak_progress'] = round((rank['mmr'] / rank['max_mmr']) * 100, 1)
        else:
            rank['peak_progress'] = 100

    # Données pour le graphique
    gamemode_id = gamemode_ids[0]
    user_data = database.get_data(player_id, gamemode_id)
    mmr_array = []
    date_array = []
    for data in user_data:
        mmr = data[0]
        mmr_array.append(mmr)
        timestamp = data[1]
        datetime_object = datetime.datetime.fromtimestamp(int(timestamp))
        date_array.append(datetime_object.strftime("%Y-%m-%d %H:%M:%S"))

    return render_template('user.html',
                           previous_url=previous_url,
                           player=player_detail,
                           ranks=ranks,
                           gamemode_ids=gamemode_ids,
                           historique=historique,
                           player_stats=player_stats,
                           session_stats=session_stats,
                           Gamemode=GameMode,
                           datetime=datetime,
                           mmr_array=mmr_array,
                           date_array=date_array)

# Route pour charger les données d'un utilisateur et afficher le graphique
@app.route('/gamemode')
def load_user():
    previous_url = request.referrer or None
    player_id = request.args.get('id')  # Récupérer l'ID de l'utilisateur depuis les paramètres de requête
    gamemode_id = int(request.args.get('gamemode'))
    if player_id:
        dernieres_24_heures = datetime.timedelta(hours=24)
        maintenant = datetime.datetime.now()
        il_y_a_24_heures = maintenant - dernieres_24_heures
        user_data = database.get_data(player_id, gamemode_id)
        print(user_data)
        mmr_array = []
        date_array = []
        i_array = []
        today_mmr_array = []
        today_date_array = []
        today_i_array = []
        for i in range(0,len(user_data)):
            mmr = user_data[i][0]
            
            timestamp = user_data[i][1]
            datetime_object = datetime.datetime.fromtimestamp(int(timestamp))
            datetime_str = datetime_object.strftime("%Y-%m-%d %H:%M")
            if datetime_object >= il_y_a_24_heures and datetime_object <= maintenant:
                today_mmr_array.append(mmr)
                today_date_array.append(datetime_str)
                today_i_array.append(i)
            else:
                mmr_array.append(mmr)
                date_array.append(datetime_str)
                i_array.append(i)


        object_mmr = {'i_array':i_array,'date_array':date_array,'mmr_array':mmr_array}
        object_mmr_today = {'i_array':today_i_array,'date_array':today_date_array,'mmr_array':today_mmr_array}

        if user_data:
            # Si des données utilisateur sont trouvées, les transmettre au template graph.html
            
            return render_template('graph.html',
                                    previous_url=previous_url,
                                    object_mmr=object_mmr,
                                    object_mmr_today=object_mmr_today,
                                    gamemode_name=GameMode(gamemode_id).str_value
                                  )
        else:
            return "Utilisateur non trouvé dans la base de données."
    else:
        return "ID de l'utilisateur non spécifié dans les paramètres de la requête."

# Route pour charger les données d'un utilisateur et afficher le graphique
@app.route('/historique')
def histo_user():
    previous_url = request.referrer or None
    player_id = request.args.get('id')  # Récupérer l'ID de l'utilisateur depuis les paramètres de requête
    default_limit = 10
    limit = int(request.args.get('limit', default_limit))
    print(limit)
    if player_id:
        player_detail = database.get_player_details(player_id)
        historique = database.get_historique(player_id, len=limit)
        if historique:
            url_more_histo = f"/historique?id={player_id}&limit={limit + default_limit}"
            previous_url = f"/user?id={player_id}"
            # Si des données utilisateur sont trouvées, les transmettre au template graph.html
            return render_template('historique.html',
                                    previous_url=previous_url,
                                    player=player_detail,
                                    historique=historique,
                                    limit=limit,
                                    url_more_histo=url_more_histo,
                                    Gamemode=GameMode,
                                    datetime=datetime,
                                    )
        else:
            return "Utilisateur non trouvé dans la base de données."
    else:
        return "ID de l'utilisateur non spécifié dans les paramètres de la requête."

@app.route('/')
def index():
    # N'afficher que les joueurs avec un profil public
    data = database.get_all_public_players()
    return render_template('index.html', data=data)

@app.route('/download')
def download():
    return render_template('download.html')

@app.errorhandler(404)
def internal_server_error(error):
    # Renvoyer le modèle d'erreur 404
    return render_template('erreur.html',error=error), 404

@app.errorhandler(500)
def internal_server_error(error):
    # Renvoyer le modèle d'erreur 500
    return render_template('erreur.html',error=error), 500

if __name__ == '__main__':
    # Creent les tables si elles n'existent pas
    database.create_table()
    app.run(debug=False, port=5000, host='0.0.0.0')
