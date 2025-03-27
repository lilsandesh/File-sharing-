import os
import sqlite3
import time
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, after_this_request
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import zipfile
import io
from functools import wraps

# Create necessary directories
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
TEMP_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TEMP_FOLDER'] = TEMP_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    
    # Create users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin BOOLEAN NOT NULL DEFAULT 0
        )
    ''')
    
    # Create files table
    c.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            encrypted_path TEXT NOT NULL,
            uploaded_by TEXT NOT NULL,
            FOREIGN KEY (uploaded_by) REFERENCES users(username)
        )
    ''')
    
    # Create default admin user if not exists
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        admin_password = generate_password_hash('admin123')
        c.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
                 ('admin', admin_password, True))
        conn.commit()
    
    conn.close()

def cleanup_temp_files():
    """Clean up temporary files older than 1 hour"""
    try:
        current_time = time.time()
        for filename in os.listdir(TEMP_FOLDER):
            filepath = os.path.join(TEMP_FOLDER, filename)
            if os.path.isfile(filepath):
                # If file is older than 1 hour, delete it
                if current_time - os.path.getmtime(filepath) > 3600:
                    os.remove(filepath)
    except Exception as e:
        app.logger.error(f"Error cleaning up temp files: {e}")

@app.before_request
def before_request():
    cleanup_temp_files()

# Initialize database on startup
init_db()

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in first.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in first.', 'danger')
            return redirect(url_for('login'))
        
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("SELECT is_admin FROM users WHERE username=?", (session['username'],))
        user = c.fetchone()
        conn.close()
        
        if not user or not user[0]:
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
            
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user[2], password):
            session['username'] = username
            session['is_admin'] = bool(user[3])
            flash('Login successful!', 'success')
            
            if session['is_admin']:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password!', 'danger')
            
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        
        # Check if username already exists
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        if c.fetchone():
            flash('Username already exists!', 'danger')
            conn.close()
            return redirect(url_for('signup'))
            
        # Hash password before storing
        hashed_password = generate_password_hash(password)
        
        try:
            c.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
                     (username, hashed_password, 0))
            conn.commit()
            flash('Account created successfully!', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash('Error creating account!', 'danger')
            app.logger.error(f"Signup error: {str(e)}")
        finally:
            conn.close()
            
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM files")
    files = c.fetchall()
    conn.close()
    return render_template('dashboard.html', files=files)

@app.route('/admin_dashboard')
@admin_required
def admin_dashboard():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    
    # Get all files
    c.execute("SELECT * FROM files")
    files = c.fetchall()
    
    # Get all users
    c.execute("SELECT * FROM users")
    users = c.fetchall()
    
    conn.close()
    return render_template('admin.html', files=files, users=users)

@app.route('/download/<int:file_id>')
@login_required
def download_file(file_id):
    try:
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("SELECT * FROM files WHERE id=?", (file_id,))
        file_data = c.fetchone()
        conn.close()

        if not file_data:
            flash('File not found!', 'danger')
            return redirect(url_for('dashboard'))

        original_filename = file_data[1]
        file_path = file_data[2]

        if not os.path.exists(file_path):
            flash('File not found on server!', 'danger')
            return redirect(url_for('dashboard'))

        # Create a temporary directory for ZIP files if it doesn't exist
        temp_dir = app.config['TEMP_FOLDER']
        os.makedirs(temp_dir, exist_ok=True)

        # Create a ZIP file
        zip_filename = f"{os.path.splitext(original_filename)[0]}.zip"
        zip_path = os.path.join(temp_dir, zip_filename)

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add the file to the ZIP archive with its original name
            zipf.write(file_path, original_filename)

        @after_this_request
        def remove_file(response):
            try:
                # Delete the temporary ZIP file after sending
                os.remove(zip_path)
            except Exception as e:
                app.logger.error(f"Error removing temporary file: {e}")
            return response

        return send_file(
            zip_path,
            as_attachment=True,
            download_name=zip_filename,
            mimetype='application/zip'
        )

    except Exception as e:
        app.logger.error(f"Download error: {str(e)}")
        flash('Error downloading file!', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/upload', methods=['POST'])
@admin_required
def upload_file():
    if 'file' not in request.files:
        flash('No file selected!', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No file selected!', 'danger')
        return redirect(url_for('admin_dashboard'))

    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        try:
            # Create uploads directory if it doesn't exist
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            
            # Save the file
            file.save(file_path)
            
            # Store file info in database
            conn = sqlite3.connect("database.db")
            c = conn.cursor()
            c.execute("""
                INSERT INTO files (filename, encrypted_path, uploaded_by) 
                VALUES (?, ?, ?)
            """, (filename, file_path, session['username']))
            conn.commit()
            conn.close()
            
            flash('File uploaded successfully!', 'success')
        except Exception as e:
            app.logger.error(f"Upload error: {str(e)}")
            flash('Error uploading file!', 'danger')
            if os.path.exists(file_path):
                os.remove(file_path)
                
    return redirect(url_for('admin_dashboard'))

@app.route('/remove_file/<int:file_id>')
@admin_required
def remove_file(file_id):
    try:
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        
        # Get file path before deleting from database
        c.execute("SELECT encrypted_path FROM files WHERE id=?", (file_id,))
        file_data = c.fetchone()
        
        if file_data:
            file_path = file_data[0]
            
            # Delete from database first
            c.execute("DELETE FROM files WHERE id=?", (file_id,))
            conn.commit()
            
            # Then try to delete the actual file
            if os.path.exists(file_path):
                os.remove(file_path)
                
            flash("File removed successfully!", "success")
        else:
            flash("File not found!", "danger")
            
    except Exception as e:
        app.logger.error(f"Remove file error: {str(e)}")
        flash("Error removing file!", "danger")
    finally:
        conn.close()
        
    return redirect(url_for('admin_dashboard'))

@app.route('/remove_user/<username>')
@admin_required
def remove_user(username):
    if username == 'admin':
        flash("Cannot remove admin user!", "danger")
        return redirect(url_for('admin_dashboard'))
    
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE username=? AND is_admin != 1", (username,))
    conn.commit()
    conn.close()
    
    flash(f"User {username} removed successfully!", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/add_admin', methods=['POST'])
@admin_required
def add_admin():
    username = request.form.get('username')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    
    if password != confirm_password:
        flash("Passwords do not match!", "danger")
        return redirect(url_for('admin_dashboard'))
    
    if not username or not password:
        flash("Username and password are required!", "danger")
        return redirect(url_for('admin_dashboard'))
    
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    try:
        hashed_password = generate_password_hash(password)
        c.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
                  (username, hashed_password, 1))
        conn.commit()
        flash(f"Admin user {username} added successfully!", "success")
    except sqlite3.IntegrityError:
        flash("Username already exists!", "danger")
    finally:
        conn.close()
    
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    # Ensure database and upload folder exist
    init_db()
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['TEMP_FOLDER'], exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)