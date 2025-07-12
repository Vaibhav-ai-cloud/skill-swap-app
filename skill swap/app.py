from flask import Flask, render_template, request, redirect, url_for, session, g
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['DATABASE'] = 'instance/skill_swap.db'
app.secret_key = 'your_secret_key'

# ------------------------
# DATABASE CONNECTION
# ------------------------
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(app.config['DATABASE'])
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# ------------------------
# HOME PAGE
# ------------------------
@app.route('/')
def index():
    return render_template("index.html")

# ------------------------
# REGISTER
# ------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        hashed_password = generate_password_hash(password)

        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                (name, email, hashed_password)
            )
            db.commit()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            return "Email already exists. Please try another email."

    return render_template("register.html")

# ------------------------
# LOGIN
# ------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()

        if user:
            stored_password = user[3]
            if check_password_hash(stored_password, password):
                session['user_id'] = user[0]
                session['user_name'] = user[1]
                return redirect(url_for('dashboard'))
            else:
                return "Invalid password. Try again."
        else:
            return "No user found with that email."

    return render_template("login.html")

# ------------------------
# LOGOUT
# ------------------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ------------------------
# DASHBOARD
# ------------------------
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()
    user_id = session['user_id']
    name = session['user_name']

    # User's own skills
    skills = db.execute(
        "SELECT * FROM skills WHERE user_id = ?",
        (user_id,)
    ).fetchall()

    # Outgoing swap requests
    swap_requests = db.execute('''
        SELECT s.skill_name, u.name, sr.status
        FROM swap_requests sr
        JOIN skills s ON sr.skill_id = s.id
        JOIN users u ON sr.to_user = u.id
        WHERE sr.from_user = ?
    ''', (user_id,)).fetchall()

    # Incoming swap requests
    received_requests = db.execute('''
        SELECT sr.id, s.skill_name, u.name, sr.status
        FROM swap_requests sr
        JOIN skills s ON sr.skill_id = s.id
        JOIN users u ON sr.from_user = u.id
        WHERE sr.to_user = ?
    ''', (user_id,)).fetchall()

    return render_template("dashboard.html", name=name, skills=skills, 
                           swap_requests=swap_requests,
                           received_requests=received_requests)

# ------------------------
# PROFILE
# ------------------------
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()
    user_id = session['user_id']

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        location = request.form['location']

        try:
            db.execute(
                "UPDATE users SET name = ?, email = ?, location = ? WHERE id = ?",
                (name, email, location, user_id)
            )
            db.commit()
            session['user_name'] = name
            return redirect(url_for('dashboard'))
        except sqlite3.IntegrityError:
            return "Email already exists. Please try another email."

    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    return render_template("profile.html", name=user[1], email=user[2], location=user[5] if user[5] else "")

# ------------------------
# ADD SKILL
# ------------------------
@app.route('/add_skill', methods=['GET', 'POST'])
def add_skill():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        skill_name = request.form['skill_name']
        user_id = session['user_id']

        db = get_db()
        db.execute(
            "INSERT INTO skills (user_id, skill_name) VALUES (?, ?)",
            (user_id, skill_name)
        )
        db.commit()
        return redirect(url_for('dashboard'))

    return render_template("add_skill.html")

# ------------------------
# DELETE SKILL
# ------------------------
@app.route('/delete_skill/<int:skill_id>')
def delete_skill(skill_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()
    user_id = session['user_id']

    skill = db.execute(
        "SELECT * FROM skills WHERE id = ? AND user_id = ?",
        (skill_id, user_id)
    ).fetchone()

    if skill:
        db.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
        db.commit()

    return redirect(url_for('dashboard'))

# ------------------------
# EDIT SKILL
# ------------------------
@app.route('/edit_skill/<int:skill_id>', methods=['GET', 'POST'])
def edit_skill(skill_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()
    user_id = session['user_id']

    skill = db.execute(
        "SELECT * FROM skills WHERE id = ? AND user_id = ?",
        (skill_id, user_id)
    ).fetchone()

    if not skill:
        return "Skill not found or unauthorized."

    if request.method == 'POST':
        new_skill_name = request.form['skill_name']
        db.execute(
            "UPDATE skills SET skill_name = ? WHERE id = ? AND user_id = ?",
            (new_skill_name, skill_id, user_id)
        )
        db.commit()
        return redirect(url_for('dashboard'))

    return render_template("edit_skill.html", skill={
        "id": skill[0],
        "skill_name": skill[2]
    })

# ------------------------
# EXPLORE OTHER USERS
# ------------------------
@app.route('/explore')
def explore():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()
    current_user_id = session['user_id']

    users = db.execute(
        "SELECT id, name FROM users WHERE id != ?",
        (current_user_id,)
    ).fetchall()

    user_skills = []

    for user in users:
        skills = db.execute(
            "SELECT id, skill_name FROM skills WHERE user_id = ?",
            (user[0],)
        ).fetchall()

        user_skills.append({
            "user_id": user[0],
            "user_name": user[1],
            "skills": skills
        })

    return render_template("explore.html", user_skills=user_skills)

# ------------------------
# REQUEST SWAP
# ------------------------
@app.route('/request_swap/<int:to_user>/<int:skill_id>')
def request_swap(to_user, skill_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    from_user = session['user_id']

    db = get_db()
    db.execute(
        "INSERT INTO swap_requests (from_user, to_user, skill_id, status) VALUES (?, ?, ?, ?)",
        (from_user, to_user, skill_id, 'Pending')
    )
    db.commit()

    print("✅ Swap request saved.")
    return redirect(url_for('dashboard'))

# ------------------------
# ACCEPT SWAP
# ------------------------
@app.route('/swap_request/accept/<int:request_id>')
def accept_swap(request_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()

    db.execute(
        "UPDATE swap_requests SET status = ? WHERE id = ?",
        ('Accepted', request_id)
    )
    db.commit()

    print(f"✅ Swap request {request_id} accepted.")
    return redirect(url_for('dashboard'))

# ------------------------
# REJECT SWAP
# ------------------------
@app.route('/swap_request/reject/<int:request_id>')
def reject_swap(request_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()

    db.execute(
        "UPDATE swap_requests SET status = ? WHERE id = ?",
        ('Rejected', request_id)
    )
    db.commit()

    print(f"❌ Swap request {request_id} rejected.")
    return redirect(url_for('dashboard'))

# ------------------------
# INIT DB
# ------------------------
def init_db():
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            photo TEXT,
            location TEXT
        );
    ''')

    db.execute('''
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            skill_name TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    ''')

    db.execute('''
        CREATE TABLE IF NOT EXISTS swap_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user INTEGER,
            to_user INTEGER,
            skill_id INTEGER,
            status TEXT,
            FOREIGN KEY (from_user) REFERENCES users(id),
            FOREIGN KEY (to_user) REFERENCES users(id),
            FOREIGN KEY (skill_id) REFERENCES skills(id)
        );
    ''')

    db.commit()
    print("Database initialized.")

# ------------------------
# RUN APP
# ------------------------
if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(debug=True)
