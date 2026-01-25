# --------------
# 
# 
# --------------
import sqlite3
from utils import dict_factory

def create_table():
    create_table_mmr()
    create_table_player()
    create_table_historique()
    migrate_historique_table()



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


# Base de données des utilisateurs (ID, Nom)
def create_table_player():
    conn = sqlite3.connect('db/player_database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS info_player
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 player_id TEXT NOT NULL,
                 player_name TEXT NOT NULL,
                 UNIQUE(player_id))''')  # Définir player_id comme unique pour éviter les doublons
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


# Fonction pour insérer ou mettre à jour les données dans la base de données
def insert_or_update_player(player_id, player_name):
    conn = sqlite3.connect('db/player_database.db')
    c = conn.cursor()
    # Vérifier si l'ID du joueur existe déjà dans la base de données
    c.execute("SELECT * FROM info_player WHERE player_id=?", (player_id,))
    existing_player = c.fetchone()
    if existing_player:
        # Si l'ID existe déjà, mettre à jour le nom du joueur
        if existing_player[1] != player_name:  # Vérifier si le nom a changé
            c.execute("UPDATE info_player SET player_name=? WHERE player_id=?", (player_name, player_id))
    else:
        # Si l'ID n'existe pas, insérer un nouvel utilisateur
        c.execute("INSERT INTO info_player (player_id, player_name) VALUES (?, ?)", (player_id, player_name))
    conn.commit()
    conn.close()

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


