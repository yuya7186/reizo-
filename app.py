import os
import hashlib
import base64
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, g
import anthropic

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'reizo-secret-key-2026')

DATABASE_URL = os.environ.get('DATABASE_URL', '')
USE_PG = bool(DATABASE_URL)

# PostgreSQLのURLをpsycopg2用に変換
if USE_PG and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)


def get_db():
    if 'db' not in g:
        if USE_PG:
            import psycopg2
            import psycopg2.extras
            g.db = psycopg2.connect(DATABASE_URL)
            g.db.autocommit = False
        else:
            import sqlite3
            DB_PATH = os.path.join(os.path.dirname(__file__), 'reizo.db')
            g.db = sqlite3.connect(DB_PATH)
            g.db.row_factory = sqlite3.Row
    return g.db


def q(sql):
    """SQLiteの?をPostgreSQLの%sに変換"""
    if USE_PG:
        return sql.replace('?', '%s')
    return sql


def fetchall(cursor):
    if USE_PG:
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
    return cursor.fetchall()


def fetchone(cursor):
    if USE_PG:
        row = cursor.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row))
    return cursor.fetchone()


def execute(db, sql, params=()):
    cur = db.cursor()
    cur.execute(q(sql), params)
    return cur


def commit(db):
    if USE_PG:
        db.commit()
    else:
        db.commit()


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db:
        db.close()


def init_db():
    if USE_PG:
        import psycopg2
        db = psycopg2.connect(DATABASE_URL)
        cur = db.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'staff'
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS storages (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                storage_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                quantity TEXT,
                note TEXT,
                updated_by INTEGER,
                updated_at TEXT,
                low_stock INTEGER DEFAULT 0
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS essentials (
                id SERIAL PRIMARY KEY,
                storage_id INTEGER NOT NULL,
                name TEXT NOT NULL
            )
        ''')
    else:
        import sqlite3
        DB_PATH = os.path.join(os.path.dirname(__file__), 'reizo.db')
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'staff'
            );
            CREATE TABLE IF NOT EXISTS storages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                storage_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                quantity TEXT,
                note TEXT,
                updated_by INTEGER,
                updated_at TEXT,
                low_stock INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS essentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                storage_id INTEGER NOT NULL,
                name TEXT NOT NULL
            );
        ''')
        cur = db.cursor()

    # マイグレーション: カラムがなければ追加
    for migration in [
        "ALTER TABLE items ADD COLUMN low_stock INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'staff'",
    ]:
        try:
            cur.execute(migration)
            db.commit()
        except Exception:
            pass  # すでに存在する場合は無視

    # 初期データ
    cur.execute('SELECT COUNT(*) FROM users')
    if cur.fetchone()[0] == 0:
        def h(pw): return hashlib.sha256(pw.encode()).hexdigest()
        for row in [('admin', h('admin1234'), '管理者', 'admin'),
                    ('staff1', h('pass1234'), '職員1', 'staff'),
                    ('staff2', h('pass1234'), '職員2', 'staff'),
                    ('staff3', h('pass1234'), '職員3', 'staff')]:
            cur.execute(q('INSERT INTO users (username, password, display_name, role) VALUES (?,?,?,?)'), row)

    cur.execute('SELECT COUNT(*) FROM storages')
    if cur.fetchone()[0] == 0:
        for row in [('冷蔵庫①', 'fridge'), ('冷蔵庫②', 'fridge'),
                    ('冷蔵庫③', 'fridge'), ('食材庫', 'pantry')]:
            cur.execute(q('INSERT INTO storages (name, type) VALUES (?,?)'), row)

    db.commit()
    db.close()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


# ─── 認証 ────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = hash_password(request.form['password'])
        db = get_db()
        cur = execute(db, 'SELECT * FROM users WHERE username=? AND password=?', (username, password))
        user = fetchone(cur)
        if user:
            session['user_id'] = user['id']
            session['display_name'] = user['display_name']
            session['role'] = user['role']
            return redirect(url_for('index'))
        error = 'IDまたはパスワードが違います'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ─── メイン ──────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    db = get_db()
    cur = execute(db, 'SELECT * FROM storages')
    storages = fetchall(cur)
    storage_info = []
    for s in storages:
        cur = execute(db, 'SELECT COUNT(*) FROM items WHERE storage_id=?', (s['id'],))
        count = cur.fetchone()[0]
        shortage = get_shortage_count(db, s['id'])
        cur = execute(db, 'SELECT COUNT(*) FROM items WHERE storage_id=? AND low_stock=1', (s['id'],))
        low_stock_count = cur.fetchone()[0]
        storage_info.append({'storage': s, 'count': count, 'shortage': shortage, 'low_stock': low_stock_count})
    return render_template('index.html', storage_info=storage_info)


def get_shortage_count(db, storage_id):
    cur = execute(db, 'SELECT name FROM essentials WHERE storage_id=?', (storage_id,))
    essentials = fetchall(cur)
    shortage = 0
    for e in essentials:
        cur2 = execute(db, 'SELECT id FROM items WHERE storage_id=? AND name=?', (storage_id, e['name']))
        if not fetchone(cur2):
            shortage += 1
    return shortage


# ─── 在庫 ────────────────────────────────────────────────

@app.route('/storage/<int:storage_id>')
@login_required
def storage(storage_id):
    db = get_db()
    cur = execute(db, 'SELECT * FROM storages WHERE id=?', (storage_id,))
    s = fetchone(cur)
    cur = execute(db, '''
        SELECT i.*, u.display_name as updater
        FROM items i LEFT JOIN users u ON i.updated_by = u.id
        WHERE i.storage_id=? ORDER BY i.name
    ''', (storage_id,))
    items = fetchall(cur)
    cur = execute(db, 'SELECT * FROM essentials WHERE storage_id=?', (storage_id,))
    essentials = fetchall(cur)
    essential_names = {e['name'] for e in essentials}
    item_names = {i['name'] for i in items}
    shortages = [e for e in essentials if e['name'] not in item_names]
    return render_template('storage.html', storage=s, items=items,
                           essentials=essentials, shortages=shortages,
                           essential_names=essential_names)


@app.route('/storage/<int:storage_id>/add', methods=['POST'])
@login_required
def add_item(storage_id):
    name = request.form['name'].strip()
    quantity = request.form.get('quantity', '').strip()
    note = request.form.get('note', '').strip()
    if name:
        db = get_db()
        execute(db, 'INSERT INTO items (storage_id, name, quantity, note, updated_by, updated_at) VALUES (?,?,?,?,?,?)',
                (storage_id, name, quantity, note, session['user_id'], datetime.now().strftime('%Y-%m-%d %H:%M')))
        commit(db)
    return redirect(url_for('storage', storage_id=storage_id))


@app.route('/item/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_item(item_id):
    db = get_db()
    cur = execute(db, 'SELECT storage_id FROM items WHERE id=?', (item_id,))
    item = fetchone(cur)
    storage_id = item['storage_id'] if item else 1
    execute(db, 'DELETE FROM items WHERE id=?', (item_id,))
    commit(db)
    return redirect(url_for('storage', storage_id=storage_id))


@app.route('/item/<int:item_id>/low_stock', methods=['POST'])
@login_required
def toggle_low_stock(item_id):
    db = get_db()
    cur = execute(db, 'SELECT low_stock, storage_id FROM items WHERE id=?', (item_id,))
    item = fetchone(cur)
    if item:
        new_val = 0 if item['low_stock'] else 1
        execute(db, 'UPDATE items SET low_stock=? WHERE id=?', (new_val, item_id))
        commit(db)
    return redirect(url_for('storage', storage_id=item['storage_id']))


@app.route('/item/<int:item_id>/edit', methods=['POST'])
@login_required
def edit_item(item_id):
    db = get_db()
    name = request.form['name'].strip()
    quantity = request.form.get('quantity', '').strip()
    note = request.form.get('note', '').strip()
    execute(db, 'UPDATE items SET name=?, quantity=?, note=?, updated_by=?, updated_at=? WHERE id=?',
            (name, quantity, note, session['user_id'], datetime.now().strftime('%Y-%m-%d %H:%M'), item_id))
    commit(db)
    cur = execute(db, 'SELECT storage_id FROM items WHERE id=?', (item_id,))
    item = fetchone(cur)
    return redirect(url_for('storage', storage_id=item['storage_id']))


# ─── 写真認識 ─────────────────────────────────────────────

@app.route('/storage/<int:storage_id>/scan', methods=['GET', 'POST'])
@login_required
def scan(storage_id):
    db = get_db()
    cur = execute(db, 'SELECT * FROM storages WHERE id=?', (storage_id,))
    s = fetchone(cur)
    recognized = None
    error = None

    if request.method == 'POST':
        file = request.files.get('photo')
        if file and file.filename:
            img_bytes = file.read()
            img_b64 = base64.standard_b64encode(img_bytes).decode()
            media_type = file.content_type or 'image/jpeg'
            try:
                api_key = os.environ.get('ANTHROPIC_API_KEY', '')
                client = anthropic.Anthropic(api_key=api_key if api_key else None)
                msg = client.messages.create(
                    model='claude-haiku-4-5-20251001',
                    max_tokens=1024,
                    messages=[{
                        'role': 'user',
                        'content': [
                            {'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': img_b64}},
                            {'type': 'text', 'text': (
                                'この画像に写っている食品・飲料・食材をすべてリストアップしてください。'
                                '1行に1品目、品名のみ（数量・説明不要）で答えてください。'
                                '例:\n牛乳\n卵\n納豆\nジュース'
                            )}
                        ]
                    }]
                )
                text = msg.content[0].text
                recognized = [line.strip() for line in text.strip().splitlines() if line.strip()]
            except Exception as e:
                import traceback
                print(traceback.format_exc())
                error = f'認識エラー: {e}'

    return render_template('scan.html', storage=s, recognized=recognized, error=error)


@app.route('/storage/<int:storage_id>/scan/save', methods=['POST'])
@login_required
def scan_save(storage_id):
    db = get_db()
    items = request.form.getlist('items')
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    for name in items:
        name = name.strip()
        if name:
            execute(db, 'INSERT INTO items (storage_id, name, quantity, note, updated_by, updated_at) VALUES (?,?,?,?,?,?)',
                    (storage_id, name, '', '', session['user_id'], now))
    commit(db)
    return redirect(url_for('storage', storage_id=storage_id))


# ─── 必需品リスト ──────────────────────────────────────────

@app.route('/storage/<int:storage_id>/essentials', methods=['GET', 'POST'])
@login_required
def essentials(storage_id):
    db = get_db()
    cur = execute(db, 'SELECT * FROM storages WHERE id=?', (storage_id,))
    s = fetchone(cur)
    if request.method == 'POST':
        name = request.form['name'].strip()
        if name:
            execute(db, 'INSERT INTO essentials (storage_id, name) VALUES (?,?)', (storage_id, name))
            commit(db)
    cur = execute(db, 'SELECT * FROM essentials WHERE storage_id=? ORDER BY name', (storage_id,))
    items = fetchall(cur)
    return render_template('essentials.html', storage=s, essentials=items)


@app.route('/essential/<int:essential_id>/delete', methods=['POST'])
@login_required
def delete_essential(essential_id):
    db = get_db()
    cur = execute(db, 'SELECT storage_id FROM essentials WHERE id=?', (essential_id,))
    e = fetchone(cur)
    storage_id = e['storage_id'] if e else 1
    execute(db, 'DELETE FROM essentials WHERE id=?', (essential_id,))
    commit(db)
    return redirect(url_for('essentials', storage_id=storage_id))


# ─── 買い物リスト ──────────────────────────────────────────

@app.route('/shopping')
@login_required
def shopping():
    db = get_db()
    cur = execute(db, 'SELECT * FROM storages')
    storages = fetchall(cur)
    shopping_list = []
    added = set()
    for s in storages:
        cur = execute(db, 'SELECT name FROM essentials WHERE storage_id=?', (s['id'],))
        essentials_list = fetchall(cur)
        for e in essentials_list:
            cur2 = execute(db, 'SELECT id FROM items WHERE storage_id=? AND name=?', (s['id'], e['name']))
            if not fetchone(cur2):
                key = (s['name'], e['name'])
                if key not in added:
                    shopping_list.append({'storage': s['name'], 'name': e['name'], 'reason': 'missing'})
                    added.add(key)
        cur = execute(db, 'SELECT name FROM items WHERE storage_id=? AND low_stock=1', (s['id'],))
        low_items = fetchall(cur)
        for item in low_items:
            key = (s['name'], item['name'])
            if key not in added:
                shopping_list.append({'storage': s['name'], 'name': item['name'], 'reason': 'low'})
                added.add(key)
    return render_template('shopping.html', shopping_list=shopping_list)


# ─── 管理画面 ─────────────────────────────────────────────

@app.route('/admin')
@admin_required
def admin():
    db = get_db()
    cur = execute(db, "SELECT id, username, display_name, role FROM users ORDER BY role, username")
    users = fetchall(cur)
    cur = execute(db, 'SELECT * FROM storages ORDER BY id')
    storages = fetchall(cur)
    return render_template('admin.html', users=users, storages=storages)


@app.route('/admin/user/add', methods=['POST'])
@admin_required
def admin_add_user():
    username = request.form['username'].strip()
    display_name = request.form['display_name'].strip()
    password = request.form['password'].strip()
    role = request.form.get('role', 'staff')
    if username and password:
        db = get_db()
        try:
            execute(db, 'INSERT INTO users (username, password, display_name, role) VALUES (?,?,?,?)',
                    (username, hash_password(password), display_name or username, role))
            commit(db)
        except Exception:
            pass  # 重複ユーザー名は無視
    return redirect(url_for('admin'))


@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    if user_id != session['user_id']:  # 自分自身は削除不可
        db = get_db()
        execute(db, 'DELETE FROM users WHERE id=?', (user_id,))
        commit(db)
    return redirect(url_for('admin'))


@app.route('/admin/user/<int:user_id>/password', methods=['POST'])
@admin_required
def admin_change_password(user_id):
    password = request.form['password'].strip()
    if password:
        db = get_db()
        execute(db, 'UPDATE users SET password=? WHERE id=?', (hash_password(password), user_id))
        commit(db)
    return redirect(url_for('admin'))


@app.route('/admin/storage/add', methods=['POST'])
@admin_required
def admin_add_storage():
    name = request.form['name'].strip()
    stype = request.form.get('type', 'fridge')
    if name:
        db = get_db()
        execute(db, 'INSERT INTO storages (name, type) VALUES (?,?)', (name, stype))
        commit(db)
    return redirect(url_for('admin'))


@app.route('/admin/storage/<int:storage_id>/delete', methods=['POST'])
@admin_required
def admin_delete_storage(storage_id):
    db = get_db()
    execute(db, 'DELETE FROM items WHERE storage_id=?', (storage_id,))
    execute(db, 'DELETE FROM essentials WHERE storage_id=?', (storage_id,))
    execute(db, 'DELETE FROM storages WHERE id=?', (storage_id,))
    commit(db)
    return redirect(url_for('admin'))


# アプリ起動時に必ずDB初期化
with app.app_context():
    try:
        init_db()
    except Exception as e:
        print(f'init_db error: {e}')

if __name__ == '__main__':
    app.run(debug=True, port=5002)
