# --------------
#
#
# --------------
import sqlite3
import secrets
import hashlib
import hmac
from utils import dict_factory


def generate_token(length=64):
    """Génère un token hexadécimal sécurisé de la longueur spécifiée"""
    return secrets.token_hex(length // 2)

def create_table():
    create_table_mmr()
    create_table_player()
    create_table_historique()
    migrate_historique_table()
    migrate_player_table()



# Fonction pour créer la table dans la base de données
def create_table_mmr():
    conn = sqlite3.connect('db/player_database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS mmr_player
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 player_id TEXT NOT NULL,
                 timestamp INTEGER NOT NULL,
                 gamemode_id INT NOT NULL,
                 mmr INTEGER NOT NULL)''')
    
    conn.commit()
    conn.close()


# Base de données des utilisateurs (ID, Nom, Auth, Visibilité)
def create_table_player():
    conn = sqlite3.connect('db/player_database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS info_player
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 player_id TEXT NOT NULL,
                 player_name TEXT NOT NULL,
                 auth_secret TEXT DEFAULT NULL,
                 is_hidden BOOLEAN DEFAULT 0,
                 access_token TEXT DEFAULT NULL,
                 UNIQUE(player_id),
                 UNIQUE(access_token))''')
    conn.commit()
    conn.close()



# Base de données des utilisateurs (ID, Nom)
def create_table_historique():
    conn = sqlite3.connect('db/player_database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS historique_player
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 player_id TEXT NOT NULL,
                 timestamp INTEGER NOT NULL,
                 victory BOOL NOT NULL,
                 mmr_won INT NOT NULL,
                 gamemode_id INT NOT NULL,
                 goals INT DEFAULT NULL,
                 assists INT DEFAULT NULL,
                 saves INT DEFAULT NULL,
                 shots INT DEFAULT NULL,
                 score INT DEFAULT NULL,
                 demos INT DEFAULT NULL,
                 mvp BOOL DEFAULT NULL,
                 team_score INT DEFAULT NULL,
                 opponent_score INT DEFAULT NULL,
                 overtime BOOL DEFAULT NULL)''')
    conn.commit()
    conn.close()


def migrate_historique_table():
    """Ajoute les nouvelles colonnes si elles n'existent pas (pour rétrocompatibilité)"""
    conn = sqlite3.connect('db/player_database.db')
    c = conn.cursor()

    new_columns = [
        ('goals', 'INT DEFAULT NULL'),
        ('assists', 'INT DEFAULT NULL'),
        ('saves', 'INT DEFAULT NULL'),
        ('shots', 'INT DEFAULT NULL'),
        ('score', 'INT DEFAULT NULL'),
        ('demos', 'INT DEFAULT NULL'),
        ('mvp', 'BOOL DEFAULT NULL'),
        ('team_score', 'INT DEFAULT NULL'),
        ('opponent_score', 'INT DEFAULT NULL'),
        ('overtime', 'BOOL DEFAULT NULL'),
    ]

    for column_name, column_type in new_columns:
        try:
            c.execute(f'ALTER TABLE historique_player ADD COLUMN {column_name} {column_type}')
            print(f"[Migration] Colonne {column_name} ajoutée")
        except sqlite3.OperationalError:
            pass  # La colonne existe déjà

    conn.commit()
    conn.close()


def migrate_player_table():
    """Ajoute les colonnes d'authentification et de visibilité si elles n'existent pas"""
    conn = sqlite3.connect('db/player_database.db')
    c = conn.cursor()

    new_columns = [
        ('auth_secret', 'TEXT DEFAULT NULL'),
        ('is_hidden', 'BOOLEAN DEFAULT 0'),
        ('access_token', 'TEXT DEFAULT NULL'),
    ]

    for column_name, column_type in new_columns:
        try:
            c.execute(f'ALTER TABLE info_player ADD COLUMN {column_name} {column_type}')
            print(f"[Migration] Colonne {column_name} ajoutée à info_player")
        except sqlite3.OperationalError:
            pass  # La colonne existe déjà

    conn.commit()
    conn.close()


# Fonction pour insérer ou mettre à jour les données dans la base de données
def insert_or_update_player(player_id, player_name):
    """
    Insère ou met à jour un joueur dans la base de données.
    Génère un auth_secret pour les nouveaux joueurs.
    Retourne un dictionnaire avec auth_secret, is_hidden et access_token.
    """
    conn = sqlite3.connect('db/player_database.db')
    conn.row_factory = dict_factory
    c = conn.cursor()

    # Vérifier si l'ID du joueur existe déjà dans la base de données
    c.execute("SELECT player_id, player_name, auth_secret, is_hidden, access_token FROM info_player WHERE player_id=?", (player_id,))
    existing_player = c.fetchone()

    if existing_player:
        # Si l'ID existe déjà, mettre à jour le nom du joueur si nécessaire
        if existing_player['player_name'] != player_name:
            c.execute("UPDATE info_player SET player_name=? WHERE player_id=?", (player_name, player_id))
            conn.commit()

        # Si le joueur n'a pas encore d'auth_secret, en générer un
        if not existing_player['auth_secret']:
            auth_secret = generate_token(64)
            c.execute("UPDATE info_player SET auth_secret=? WHERE player_id=?", (auth_secret, player_id))
            conn.commit()
            existing_player['auth_secret'] = auth_secret

        conn.close()
        return {
            'auth_secret': existing_player['auth_secret'],
            'is_hidden': bool(existing_player['is_hidden']),
            'access_token': existing_player['access_token']
        }
    else:
        # Si l'ID n'existe pas, insérer un nouvel utilisateur avec un auth_secret
        auth_secret = generate_token(64)
        c.execute(
            "INSERT INTO info_player (player_id, player_name, auth_secret, is_hidden, access_token) VALUES (?, ?, ?, ?, ?)",
            (player_id, player_name, auth_secret, False, None)
        )
        conn.commit()
        conn.close()
        return {
            'auth_secret': auth_secret,
            'is_hidden': False,
            'access_token': None
        }

# Fonction pour insérer les données dans la base de données
def insert_data(player_id, timestamp, gamemode_id, mmr):
    conn = sqlite3.connect('db/player_database.db')
    c = conn.cursor()
    c.execute("INSERT INTO mmr_player (player_id, timestamp, gamemode_id, mmr) VALUES (?, ?, ?, ?)", (player_id, timestamp, gamemode_id, mmr))
    conn.commit()
    conn.close()

# Fonction pour insérer les données dans la base de données
def insert_history(player_id, timestamp, victory, mmr_won, gamemode_id,
                   goals=None, assists=None, saves=None, shots=None,
                   score=None, demos=None, mvp=None,
                   team_score=None, opponent_score=None, overtime=None):
    conn = sqlite3.connect('db/player_database.db')
    c = conn.cursor()
    c.execute("""INSERT INTO historique_player
                 (player_id, timestamp, victory, mmr_won, gamemode_id,
                  goals, assists, saves, shots, score, demos, mvp,
                  team_score, opponent_score, overtime)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (player_id, timestamp, victory, mmr_won, gamemode_id,
               goals, assists, saves, shots, score, demos, mvp,
               team_score, opponent_score, overtime))
    conn.commit()
    conn.close()


# Fonction pour récupérer les données de la base de données
def get_data(player_id, gamemode_id):
    conn = sqlite3.connect('db/player_database.db')
    c = conn.cursor()
    c.execute("SELECT mmr, timestamp FROM mmr_player WHERE player_id = ? AND gamemode_id = ? ORDER BY timestamp", (player_id, gamemode_id))
    data = c.fetchall()
    conn.close()
    return data

def get_historique(player_id, len=10):
    conn = sqlite3.connect('db/player_database.db')
    conn.row_factory = dict_factory
    c = conn.cursor()
    c.execute("""SELECT id, timestamp, victory, mmr_won, gamemode_id,
                        goals, assists, saves, shots, score, demos, mvp,
                        team_score, opponent_score, overtime
                 FROM historique_player
                 WHERE player_id = ?
                 ORDER BY timestamp DESC
                 LIMIT 0, ?""", (player_id, len))
    data = c.fetchall()
    conn.close()
    return data

# Fonction pour récupérer les données de la base de données
def get_all_player():
    conn = sqlite3.connect('db/player_database.db')
    c = conn.cursor()
    c.execute("SELECT player_id, player_name FROM info_player")
    data = c.fetchall()
    conn.close()
    return data

def get_player_details(player_id):
    conn = sqlite3.connect('db/player_database.db')
    conn.row_factory = dict_factory
    c = conn.cursor()
    c.execute("SELECT player_id, player_name FROM info_player WHERE player_id = ?", (player_id,))
    player_details = c.fetchone()
    conn.close()
    return player_details


def get_all_ranks(player_id):
    conn = sqlite3.connect('db/player_database.db')
    conn.row_factory = dict_factory
    c = conn.cursor()
    c.execute("SELECT gamemode_id, MAX(timestamp) as timestamp_atm_mmr, mmr  FROM mmr_player WHERE player_id = ? GROUP BY gamemode_id ", (player_id,))
    ranks_atm = c.fetchall()
    print(ranks_atm)
    c.execute("SELECT gamemode_id, MAX(mmr) as max_mmr, timestamp as max_mmr_timestamp FROM mmr_player WHERE player_id = ? GROUP BY gamemode_id", (player_id,))
    ranks_max = c.fetchall()
    print(ranks_max)

    mmr_dict = {entry['gamemode_id']: entry for entry in ranks_max}

    for entry in ranks_atm:
        gamemode_id = entry['gamemode_id']
        max_mmr_entry = mmr_dict.get(gamemode_id)
        if max_mmr_entry:
            entry.update(max_mmr_entry)

    print(ranks_atm)

    conn.close()
    return ranks_atm


def get_player_stats(player_id):
    """Récupère les statistiques globales d'un joueur"""
    conn = sqlite3.connect('db/player_database.db')
    conn.row_factory = dict_factory
    c = conn.cursor()

    # Stats globales
    c.execute("""
        SELECT
            COUNT(*) as total_games,
            SUM(CASE WHEN victory = 1 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN victory = 0 THEN 1 ELSE 0 END) as losses,
            SUM(mmr_won) as total_mmr_change,
            AVG(CASE WHEN goals IS NOT NULL THEN goals ELSE NULL END) as avg_goals,
            AVG(CASE WHEN assists IS NOT NULL THEN assists ELSE NULL END) as avg_assists,
            AVG(CASE WHEN saves IS NOT NULL THEN saves ELSE NULL END) as avg_saves,
            AVG(CASE WHEN shots IS NOT NULL THEN shots ELSE NULL END) as avg_shots,
            AVG(CASE WHEN score IS NOT NULL THEN score ELSE NULL END) as avg_score,
            AVG(CASE WHEN demos IS NOT NULL THEN demos ELSE NULL END) as avg_demos,
            SUM(CASE WHEN mvp = 1 THEN 1 ELSE 0 END) as mvp_count
        FROM historique_player
        WHERE player_id = ?
    """, (player_id,))
    stats = c.fetchone()

    conn.close()
    return stats


def get_player_session_stats(player_id, hours=24):
    """Récupère les stats de session (dernières X heures)"""
    import time
    conn = sqlite3.connect('db/player_database.db')
    conn.row_factory = dict_factory
    c = conn.cursor()

    # Timestamp il y a X heures
    cutoff = int(time.time()) - (hours * 3600)

    c.execute("""
        SELECT
            COUNT(*) as session_games,
            SUM(CASE WHEN victory = 1 THEN 1 ELSE 0 END) as session_wins,
            SUM(CASE WHEN victory = 0 THEN 1 ELSE 0 END) as session_losses,
            SUM(mmr_won) as session_mmr_change
        FROM historique_player
        WHERE player_id = ? AND timestamp >= ?
    """, (player_id, cutoff))
    session = c.fetchone()

    conn.close()
    return session


def get_mmr_trend(player_id, gamemode_id, last_n=5):
    """Récupère la tendance MMR (derniers N matchs)"""
    conn = sqlite3.connect('db/player_database.db')
    c = conn.cursor()

    c.execute("""
        SELECT mmr FROM mmr_player
        WHERE player_id = ? AND gamemode_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (player_id, gamemode_id, last_n + 1))

    data = c.fetchall()
    conn.close()

    if len(data) >= 2:
        current = data[0][0]
        oldest = data[-1][0]
        return current - oldest
    return 0


# ================================
# Fonctions d'authentification
# ================================

def get_player_auth_secret(player_id):
    """Récupère le secret d'authentification d'un joueur"""
    conn = sqlite3.connect('db/player_database.db')
    c = conn.cursor()
    c.execute("SELECT auth_secret FROM info_player WHERE player_id = ?", (player_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None


def verify_hmac_signature(player_id, body, signature):
    """
    Vérifie la signature HMAC-SHA256 d'une requête.
    Retourne True si la signature est valide, False sinon.
    """
    auth_secret = get_player_auth_secret(player_id)
    if not auth_secret:
        return False

    # Calculer la signature attendue
    expected = hmac.new(
        auth_secret.encode('utf-8'),
        body.encode('utf-8') if isinstance(body, str) else body,
        hashlib.sha256
    ).hexdigest()

    # Comparaison en temps constant pour éviter les attaques timing
    return hmac.compare_digest(expected, signature)


# ================================
# Fonctions de visibilité
# ================================

def get_player_visibility(player_id):
    """
    Récupère l'état de visibilité d'un joueur.
    Retourne un dictionnaire avec is_hidden et access_token.
    """
    conn = sqlite3.connect('db/player_database.db')
    conn.row_factory = dict_factory
    c = conn.cursor()
    c.execute("SELECT is_hidden, access_token FROM info_player WHERE player_id = ?", (player_id,))
    result = c.fetchone()
    conn.close()

    if result:
        return {
            'is_hidden': bool(result['is_hidden']),
            'access_token': result['access_token']
        }
    return None


def set_player_visibility(player_id, is_hidden):
    """
    Définit la visibilité d'un joueur.
    Si is_hidden=True et pas de token existant, génère un access_token.
    Retourne le dictionnaire avec is_hidden et access_token.
    """
    conn = sqlite3.connect('db/player_database.db')
    conn.row_factory = dict_factory
    c = conn.cursor()

    # Récupérer l'état actuel
    c.execute("SELECT access_token FROM info_player WHERE player_id = ?", (player_id,))
    result = c.fetchone()

    if not result:
        conn.close()
        return None

    access_token = result['access_token']

    # Si on cache le profil et qu'il n'y a pas de token, en générer un
    if is_hidden and not access_token:
        access_token = generate_token(64)

    c.execute(
        "UPDATE info_player SET is_hidden = ?, access_token = ? WHERE player_id = ?",
        (is_hidden, access_token if is_hidden else access_token, player_id)
    )
    conn.commit()
    conn.close()

    return {
        'is_hidden': is_hidden,
        'access_token': access_token
    }


def regenerate_access_token(player_id):
    """
    Régénère le token d'accès d'un joueur.
    Retourne le nouveau token ou None si le joueur n'existe pas.
    """
    conn = sqlite3.connect('db/player_database.db')
    c = conn.cursor()

    # Vérifier que le joueur existe
    c.execute("SELECT player_id FROM info_player WHERE player_id = ?", (player_id,))
    if not c.fetchone():
        conn.close()
        return None

    new_token = generate_token(64)
    c.execute("UPDATE info_player SET access_token = ? WHERE player_id = ?", (new_token, player_id))
    conn.commit()
    conn.close()

    return new_token


def regenerate_auth_secret(player_id):
    """
    Régénère le secret d'authentification d'un joueur.
    Retourne le nouveau secret ou None si le joueur n'existe pas.
    """
    conn = sqlite3.connect('db/player_database.db')
    c = conn.cursor()

    # Vérifier que le joueur existe
    c.execute("SELECT player_id FROM info_player WHERE player_id = ?", (player_id,))
    if not c.fetchone():
        conn.close()
        return None

    new_secret = generate_token(64)
    c.execute("UPDATE info_player SET auth_secret = ? WHERE player_id = ?", (new_secret, player_id))
    conn.commit()
    conn.close()

    return new_secret


def get_player_by_access_token(token):
    """
    Récupère les informations d'un joueur à partir de son token d'accès.
    Retourne un dictionnaire avec player_id, player_name, is_hidden ou None si non trouvé.
    """
    conn = sqlite3.connect('db/player_database.db')
    conn.row_factory = dict_factory
    c = conn.cursor()
    c.execute(
        "SELECT player_id, player_name, is_hidden FROM info_player WHERE access_token = ?",
        (token,)
    )
    result = c.fetchone()
    conn.close()

    if result:
        result['is_hidden'] = bool(result['is_hidden'])
    return result


def get_all_public_players():
    """
    Récupère tous les joueurs dont le profil est public (is_hidden = 0).
    Retourne une liste de tuples (player_id, player_name).
    """
    conn = sqlite3.connect('db/player_database.db')
    c = conn.cursor()
    c.execute("SELECT player_id, player_name FROM info_player WHERE is_hidden = 0 OR is_hidden IS NULL")
    data = c.fetchall()
    conn.close()
    return data


def is_player_hidden(player_id):
    """
    Vérifie si un joueur a un profil caché.
    Retourne True si caché, False sinon.
    """
    conn = sqlite3.connect('db/player_database.db')
    c = conn.cursor()
    c.execute("SELECT is_hidden FROM info_player WHERE player_id = ?", (player_id,))
    result = c.fetchone()
    conn.close()
    return bool(result[0]) if result and result[0] else False
