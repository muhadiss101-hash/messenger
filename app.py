import sqlite3
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, g
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'messenger-secret-key-2024'
DATABASE = 'messenger.db'


# ── База данных ──────────────────────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user TEXT NOT NULL,
            to_user   TEXT NOT NULL,
            text      TEXT NOT NULL DEFAULT '',
            image     TEXT,
            time      TEXT NOT NULL
        )
    ''')
    # Добавляем колонку image если её нет (для уже существующих БД)
    try:
        db.execute('ALTER TABLE messages ADD COLUMN image TEXT')
    except Exception:
        pass
    db.commit()
    db.close()


# ── Страницы ─────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('chat'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        name = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if not name or not password:
            error = 'Заполните все поля'
        else:
            db = get_db()
            user = db.execute(
                'SELECT * FROM users WHERE username = ? AND password = ?',
                (name, password)
            ).fetchone()
            if user is None:
                error = 'Неверное имя или пароль'
            else:
                session['username'] = name
                return redirect(url_for('chat'))
    return render_template('login.html', error=error, mode='login')


@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        name = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if not name or not password:
            error = 'Заполните все поля'
        elif len(password) < 3:
            error = 'Пароль слишком короткий (минимум 3 символа)'
        else:
            db = get_db()
            existing = db.execute(
                'SELECT id FROM users WHERE username = ?', (name,)
            ).fetchone()
            if existing:
                error = 'Такой пользователь уже существует'
            else:
                db.execute('INSERT INTO users (username, password) VALUES (?, ?)', (name, password))
                db.commit()
                session['username'] = name
                return redirect(url_for('chat'))
    return render_template('login.html', error=error, mode='register')


@app.route('/chat')
def chat():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('chat.html', current_user=session['username'])


@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))


# ── API ───────────────────────────────────────────────────────────────────────

@app.route('/api/contacts')
def api_contacts():
    if 'username' not in session:
        return jsonify({'error': 'Не авторизован'}), 401
    me = session['username']
    db = get_db()
    users = db.execute('SELECT username FROM users WHERE username != ?', (me,)).fetchall()
    return jsonify([u['username'] for u in users])


@app.route('/api/messages')
def api_messages():
    if 'username' not in session:
        return jsonify({'error': 'Не авторизован'}), 401
    me = session['username']
    with_user = request.args.get('with', '')
    if not with_user:
        return jsonify([])
    db = get_db()
    msgs = db.execute(
        '''SELECT from_user, to_user, text, image, time FROM messages
           WHERE (from_user = ? AND to_user = ?)
              OR (from_user = ? AND to_user = ?)
           ORDER BY id ASC''',
        (me, with_user, with_user, me)
    ).fetchall()
    return jsonify([{
        'from':  m['from_user'],
        'to':    m['to_user'],
        'text':  m['text'],
        'image': m['image'],
        'time':  m['time']
    } for m in msgs])


@app.route('/api/send', methods=['POST'])
def api_send():
    if 'username' not in session:
        return jsonify({'error': 'Не авторизован'}), 401
    me = session['username']
    data = request.get_json()
    to    = data.get('to', '').strip()
    text  = data.get('text', '').strip()
    image = data.get('image')  # base64 строка или None

    if not to or (not text and not image):
        return jsonify({'error': 'Пустое сообщение'}), 400

    db = get_db()
    if not db.execute('SELECT id FROM users WHERE username = ?', (to,)).fetchone():
        return jsonify({'error': 'Получатель не найден'}), 404

    # Ограничение размера картинки ~3 МБ в base64
    if image and len(image) > 4_000_000:
        return jsonify({'error': 'Картинка слишком большая (макс. 3 МБ)'}), 400

    time_now = datetime.now().strftime('%H:%M')
    db.execute(
        'INSERT INTO messages (from_user, to_user, text, image, time) VALUES (?, ?, ?, ?, ?)',
        (me, to, text, image, time_now)
    )
    db.commit()
    return jsonify({'ok': True})


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5001)


init_db()
