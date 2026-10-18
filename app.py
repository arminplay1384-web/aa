import sqlite3
from flask import Flask, request, jsonify, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'super_secret_flashcard_key_change_in_prod'
DB_NAME = 'vocab.db'

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        # جدول کاربران
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # جدول کلمات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL,
                phonetic TEXT NOT NULL,
                meaning TEXT NOT NULL,
                example TEXT NOT NULL
            )
        ''')
        # جدول وضعیت یادگیری هر کاربر (رابطه‌ای)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_progress (
                user_id INTEGER,
                card_id INTEGER,
                is_learned INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, card_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (card_id) REFERENCES cards(id)
            )
        ''')

        # افزودن کلمات پیش‌فرض در صورت خالی بودن دیتابیس
        cursor.execute('SELECT COUNT(*) as count FROM cards')
        if cursor.fetchone()['count'] == 0:
            initial_cards = [
                ("Persevere", "/ˌpɜː.sɪˈvɪər/", "استقامت کردن، دست نکشیدن از تلاش", "If you persevere, you will overcome any obstacle."),
                ("Resilient", "/rɪˈzɪl.jənt/", "سرسخت، دارای قدرت بازیابی پس از سختی", "He remained resilient even during financial crises."),
                ("Eloquent", "/ˈel.ə.kwənt/", "فصیح، شیوا و تأثیرگذار در سخن", "She delivered an eloquent argument in court."),
                ("Compassion", "/kəmˈpæʃ.ən/", "همدلی و محبت عمیق نسبت به دیگران", "True leadership requires empathy and compassion."),
                ("Pragmatic", "/præɡˈmæt.ɪk/", "عمل‌گرا، واقع‌بینانه و منطقی", "We need a pragmatic approach to solve this bug."),
                ("Inevitable", "/ɪnˈev.ɪ.tə.bəl/", "اجتناب‌ناپذیر، حتمی‌الوقوع", "Change is inevitable in the tech industry."),
                ("Ambiguous", "/æmˈbɪɡ.ju.əs/", "مبهم، دوپهلو و نامشخص", "The contract terms were too ambiguous to sign."),
                ("Meticulous", "/məˈtɪk.jə.ləs/", "بسیار دقیق، موشکافانه و تمیز", "He is meticulous about his code structure.")
            ]
            cursor.executemany(
                'INSERT INTO cards (word, phonetic, meaning, example) VALUES (?, ?, ?, ?)',
                initial_cards
            )
        conn.commit()

# سرو کردن صفحه رابط کاربری
@app.route('/')
def home():
    return send_from_directory('.', 'index.html')

# ثبت‌نام
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'error': 'نام کاربری و رمز عبور الزامی است'}), 400

    if len(password) < 4:
        return jsonify({'error': 'رمز عبور باید حداقل ۴ کاراکتر باشد'}), 400

    hash_pw = generate_password_hash(password)

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, hash_pw))
            user_id = cursor.lastrowid
            conn.commit()
            
            session['user_id'] = user_id
            session['username'] = username
            return jsonify({'message': 'ثبت‌نام با موفقیت انجام شد', 'username': username})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'این نام کاربری قبلاً ثبت شده است'}), 409

# ورود
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()

        if not user or not check_password_hash(user['password_hash'], password):
            return jsonify({'error': 'نام کاربری یا رمز عبور اشتباه است'}), 401

        session['user_id'] = user['id']
        session['username'] = user['username']
        return jsonify({'message': 'ورود موفقیت‌آمیز بود', 'username': user['username']})

# خروج
@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'خروج با موفقیت انجام شد'})

# بررسی وضعیت لاگین
@app.route('/api/me', methods=['GET'])
def me():
    if 'user_id' in session:
        return jsonify({'logged_in': True, 'username': session['username']})
    return jsonify({'logged_in': False})

# دریافت کلمات همراه با وضعیت پیشرفت کاربر از دیتابیس
@app.route('/api/cards', methods=['GET'])
def get_cards():
    if 'user_id' not in session:
        return jsonify({'error': 'عدم دسترسی، لطفاً ابتدا وارد شوید'}), 401

    user_id = session['user_id']
    with get_db() as conn:
        cursor = conn.cursor()
        # خواندن کارت‌ها و اتصال به جدول وضعیت کاربر
        cursor.execute('''
            SELECT c.id, c.word, c.phonetic, c.meaning, c.example,
                   COALESCE(up.is_learned, 0) as is_learned
            FROM cards c
            LEFT JOIN user_progress up ON c.id = up.card_id AND up.user_id = ?
            ORDER BY c.id ASC
        ''', (user_id,))
        rows = cursor.fetchall()

        cards = [dict(row) for row in rows]
        return jsonify({'cards': cards})

# تغییر وضعیت یادگیری کارت در دیتابیس
@app.route('/api/cards/<int:card_id>/toggle', methods=['POST'])
def toggle_learned(card_id):
    if 'user_id' not in session:
        return jsonify({'error': 'عدم دسترسی'}), 401

    user_id = session['user_id']
    data = request.get_json() or {}
    is_learned = 1 if data.get('is_learned') else 0

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO user_progress (user_id, card_id, is_learned)
            VALUES (?, ?, ?)
        ''', (user_id, card_id, is_learned))
        conn.commit()

    return jsonify({'status': 'ok', 'is_learned': is_learned})

if __name__ == '__main__':
    init_db()
    print("🚀 سرور در آدرس http://127.0.0.1:5000 فعال شد.")
    app.run(debug=True, port=5000)