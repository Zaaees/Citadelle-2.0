import os
import json
from datetime import datetime
from flask import Flask, redirect, request, session, url_for, render_template, jsonify
import requests
import gspread
from google.oauth2.service_account import Credentials

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

# Google Sheets configuration (shared with the Discord bot)
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def get_sheets():
    """Return (sheet_cards, sheet_daily_draw) using environment credentials."""
    if not hasattr(app, 'sheet_cards'):
        creds_info = os.environ.get('SERVICE_ACCOUNT_JSON')
        if not creds_info:
            raise RuntimeError('SERVICE_ACCOUNT_JSON is not configured')
        creds = Credentials.from_service_account_info(json.loads(creds_info), scopes=SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(os.environ['GOOGLE_SHEET_ID_CARTES'])
        app.sheet_cards = spreadsheet.sheet1
        try:
            app.sheet_daily_draw = spreadsheet.worksheet('Tirages Journaliers')
        except gspread.exceptions.WorksheetNotFound:
            app.sheet_daily_draw = spreadsheet.add_worksheet(title='Tirages Journaliers', rows='1000', cols='2')
    return app.sheet_cards, app.sheet_daily_draw
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


def _merge_cells(row):
    merged = {}
    for cell in row[2:]:
        cell = cell.strip()
        if not cell or ':' not in cell:
            continue
        uid, cnt = cell.split(':', 1)
        uid = uid.strip()
        try:
            cnt = int(cnt.strip())
        except ValueError:
            continue
        merged[uid] = merged.get(uid, 0) + cnt
    return row[:2] + [f"{uid}:{cnt}" for uid, cnt in merged.items()]


def add_card_to_user(user_id, category, name):
    sheet_cards, _ = get_sheets()
    rows = sheet_cards.get_all_values()
    for i, row in enumerate(rows):
        if len(row) < 2:
            continue
        if row[0] == category and row[1] == name:
            for j in range(2, len(row)):
                cell = row[j].strip()
                if cell.startswith(f"{user_id}:"):
                    uid, count = cell.split(':', 1)
                    uid = uid.strip()
                    row[j] = f"{uid}:{int(count) + 1}"
                    sheet_cards.update(f"A{i+1}", [_merge_cells(row)])
                    return
            row.append(f"{user_id}:1")
            sheet_cards.update(f"A{i+1}", [_merge_cells(row)])
            return
    new_row = [category, name, f"{user_id}:1"]
    sheet_cards.append_row(new_row)


def record_daily_draw(user_id):
    _, sheet_daily_draw = get_sheets()
    today = datetime.utcnow().date().isoformat()
    rows = sheet_daily_draw.get_all_values()
    row_idx = next((i for i, r in enumerate(rows) if r and r[0] == str(user_id)), None)
    if row_idx is not None and len(rows[row_idx]) > 1 and rows[row_idx][1] == today:
        return False
    if row_idx is None:
        sheet_daily_draw.append_row([str(user_id), today])
    else:
        sheet_daily_draw.update(f"B{row_idx+1}", [[today]])
    return True


def send_discord_message(user, cards):
    token = os.environ.get('DISCORD_TOKEN')
    channel_id = os.environ.get('DISCORD_CHANNEL_ID', '1361993326215172218')
    if not token:
        return
    content = f"{user['username']} a tir\u00e9 : " + \
        ', '.join(f"{c['name']} ({c['category']})" for c in cards)
    headers = {
        'Authorization': f'Bot {token}',
        'Content-Type': 'application/json'
    }
    requests.post(
        f"{API_BASE_URL}/channels/{channel_id}/messages",
        headers=headers,
        json={'content': content}
    )


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
    if not record_daily_draw(user['id']):
        return jsonify({'error': 'already_drawn'})
    drawn = draw_cards()
    for c in drawn:
        add_card_to_user(user['id'], c['category'], c['name'])
    send_discord_message(user, drawn)
    return jsonify({'cards': drawn})


if __name__ == '__main__':
    app.run(debug=True)
