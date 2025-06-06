import os
import json
from datetime import datetime
from flask import Flask, redirect, request, session, url_for, render_template, jsonify
import requests

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'changeme')

# Discord OAuth2 configuration
CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID')
CLIENT_SECRET = os.environ.get('DISCORD_CLIENT_SECRET')
REDIRECT_URI = os.environ.get('DISCORD_REDIRECT_URI', 'http://localhost:5000/callback')
API_BASE_URL = 'https://discord.com/api'

# Load sample cards
with open(os.path.join(os.path.dirname(__file__), 'cards.json'), encoding='utf-8') as f:
    CARDS = json.load(f)

RARITY_WEIGHTS = {
    "Secrète": 0.005,
    "Fondateur": 0.01,
    "Historique": 0.02,
    "Maître": 0.06,
    "Black Hole": 0.06,
    "Architectes": 0.07,
    "Professeurs": 0.1167,
    "Autre": 0.2569,
    "Élèves": 0.4203,
}
ALL_CATEGORIES = list(RARITY_WEIGHTS.keys())

USERS_FILE = os.path.join(os.path.dirname(__file__), 'users.json')
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, 'w') as f:
        json.dump({}, f)


def load_users():
    with open(USERS_FILE, 'r') as f:
        return json.load(f)


def save_users(data):
    with open(USERS_FILE, 'w') as f:
        json.dump(data, f)


def draw_cards(n=3):
    import random
    drawn = []
    weights = [RARITY_WEIGHTS[c] for c in ALL_CATEGORIES]
    total = sum(weights)
    weights = [w / total for w in weights]
    for _ in range(n):
        cat = random.choices(ALL_CATEGORIES, weights=weights, k=1)[0]
        options = CARDS.get(cat, [])
        if not options:
            continue
        card = random.choice(options)
        drawn.append({'category': cat, 'name': card})
    return drawn


@app.route('/')
def index():
    user = session.get('user')
    return render_template('index.html', user=user)


@app.route('/login')
def login():
    discord_url = (
        f"{API_BASE_URL}/oauth2/authorize?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code&scope=identify"
    )
    return redirect(discord_url)


@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return 'Missing code', 400
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'scope': 'identify'
    }
    headers = { 'Content-Type': 'application/x-www-form-urlencoded' }
    token_res = requests.post(f'{API_BASE_URL}/oauth2/token', data=data, headers=headers)
    token_res.raise_for_status()
    tokens = token_res.json()
    user_res = requests.get(
        f'{API_BASE_URL}/users/@me',
        headers={'Authorization': f"Bearer {tokens['access_token']}"}
    )
    user_res.raise_for_status()
    user = user_res.json()
    session['user'] = {'id': user['id'], 'username': f"{user['username']}#{user['discriminator']}"}
    return redirect(url_for('index'))


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))


@app.route('/draw', methods=['POST'])
def draw():
    user = session.get('user')
    if not user:
        return jsonify({'error': 'not_logged_in'}), 401
    users = load_users()
    today = datetime.utcnow().date().isoformat()
    last = users.get(user['id'], {}).get('last_draw')
    if last == today:
        return jsonify({'error': 'already_drawn'})
    drawn = draw_cards()
    users[user['id']] = {'last_draw': today, 'cards': drawn}
    save_users(users)
    return jsonify({'cards': drawn})


if __name__ == '__main__':
    app.run(debug=True)
