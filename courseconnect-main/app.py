# ========================================
# CourseConnect - Social Network per Corsisti  
# app.py - Backend Flask con Sistema Completo + Video Fix + ENDPOINT CORSI FISSI + FIX is_private
# ========================================

from flask import Flask, render_template, request, jsonify, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os, json

# ========================================
# FLASK APP & CONFIG
# ========================================

app = Flask(__name__)

# Secret key (in produzione sovrascrivi con env var)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'courseconnect-secret-key-2024')

# --- DATABASE_URL ---
# Default: SQLite in path ASSOLUTO nella working dir (evita "readonly database" su Render)
default_sqlite_path = os.path.join(os.getcwd(), 'courseconnect.db')
db_url = os.environ.get('DATABASE_URL', f'sqlite:///{default_sqlite_path}')

# Render Postgres spesso usa "postgres://", SQLAlchemy vuole "postgresql+psycopg2://"
if db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://', 'postgresql+psycopg2://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Engine options (pool, keep-alive)
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {})
app.config['SQLALCHEMY_ENGINE_OPTIONS'].update({
    'pool_pre_ping': True,
    'pool_recycle': 300,
})

# SQLite + worker async: disabilita check_same_thread
if db_url.startswith('sqlite'):
    app.config['SQLALCHEMY_ENGINE_OPTIONS'].setdefault('connect_args', {})['check_same_thread'] = False

# Cookie di sessione più sicuri (su Render è HTTPS)
app.config.setdefault('SESSION_COOKIE_SAMESITE', 'Lax')
app.config.setdefault('SESSION_COOKIE_SECURE', True)

# Uploads (immagini + video) - FIX COMPLETO
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(os.getcwd(), 'static', 'uploads'))
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm'}
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max file size
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
# Crea anche la cartella video
VIDEO_FOLDER = os.path.join(UPLOAD_FOLDER, 'videos')
os.makedirs(VIDEO_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

print(f"📁 Upload folder: {UPLOAD_FOLDER}")
print(f"🎥 Video folder: {VIDEO_FOLDER}")

db = SQLAlchemy(app)

# ========================================
# MODELLI DATABASE
# ========================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    cognome = db.Column(db.String(100), nullable=False)
    corso = db.Column(db.String(200), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    bio = db.Column(db.Text, default='')
    avatar_url = db.Column(db.String(500), default='')
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    posts = db.relationship('Post', backref='author', lazy='dynamic', cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='author', lazy='dynamic', cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    reviews = db.relationship('Review', backref='author', lazy='dynamic', cascade='all, delete-orphan')
    
    # Course relationships
    taught_courses = db.relationship('Course', backref='instructor', lazy='dynamic')
    enrollments = db.relationship('Enrollment', backref='student', lazy='dynamic', cascade='all, delete-orphan')
    lesson_progress = db.relationship('LessonProgress', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def get_avatar_color(self):
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F']
        return colors[len(self.username) % len(colors)]

    def get_initials(self):
        return f"{self.nome[0]}{self.cognome[0]}".upper() if self.nome and self.cognome else self.username[0].upper()

    def to_dict(self):
        # Calcola statistiche corsi
        enrolled_courses = self.enrollments.count()
        taught_courses = self.taught_courses.count()
        
        # Calcola progresso medio dei corsi iscritti
        total_progress = 0
        active_enrollments = self.enrollments.filter_by(is_active=True).all()
        
        if active_enrollments:
            for enrollment in active_enrollments:
                course_progress = enrollment.course.get_user_progress(self.id)
                total_progress += course_progress
            avg_progress = total_progress / len(active_enrollments)
        else:
            avg_progress = 0
        
        return {
            'id': self.id,
            'username': self.username,
            'nome': self.nome,
            'cognome': self.cognome,
            'corso': self.corso,
            'bio': self.bio,
            'avatar_url': self.avatar_url,
            'avatar_color': self.get_avatar_color(),
            'initials': self.get_initials(),
            'is_admin': self.is_admin,
            'enrolled_courses': enrolled_courses,
            'taught_courses': taught_courses,
            'avg_progress': round(avg_progress, 1),
            'created_at': (self.created_at or datetime.utcnow()).isoformat()
        }


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    image_filename = db.Column(db.String(255))
    video_filename = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    comments = db.relationship('Comment', backref='post', lazy='dynamic', cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='post', lazy='dynamic', cascade='all, delete-orphan')

    def get_likes_count(self):
        return self.likes.count()

    def is_liked_by(self, user):
        if not user:
            return False
        return self.likes.filter_by(user_id=user.id).first() is not None

    def to_dict(self, current_user=None):
        return {
            'id': self.id,
            'content': self.content,
            'image_filename': self.image_filename,
            'video_filename': self.video_filename,
            'created_at': (self.created_at or datetime.utcnow()).isoformat(),
            'author': self.author.to_dict() if self.author else {},
            'likes_count': self.get_likes_count(),
            'is_liked': self.is_liked_by(current_user),
            'comments_count': self.comments.count(),
            'user_can_delete': current_user and (current_user.id == self.user_id or current_user.is_admin)
        }


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'content': self.content,
            'created_at': (self.created_at or datetime.utcnow()).isoformat(),
            'author': self.author.to_dict() if self.author else {},
            'post_id': self.post_id,
            'user_can_delete': True  # Will be updated by frontend logic
        }


class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='unique_user_post_like'),)


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stelle
    photo_url = db.Column(db.String(500), nullable=False)
    location = db.Column(db.String(100), default='')
    is_approved = db.Column(db.Boolean, default=True)  # Per moderazione futura
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'name': f"{self.author.nome} {self.author.cognome}",
            'course': f"{self.author.corso}{' • ' + self.location if self.location else ''}",
            'text': self.text,
            'rating': self.rating,
            'photo': self.photo_url,
            'created_at': (self.created_at or datetime.utcnow()).isoformat(),
            'isStatic': False
        }


# ========================================
# MODELLI CORSI E SISTEMA APPRENDIMENTO
# ========================================

class Course(db.Model):
    """Modello per i corsi"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(100), nullable=False)  # Web Design, SEO, WordPress, etc.
    course_type = db.Column(db.String(50), default='CORSI')  # CORSI, TRAINING
    thumbnail_url = db.Column(db.String(500))
    is_private = db.Column(db.Boolean, default=False)
    price = db.Column(db.Float, default=0.0)
    duration_hours = db.Column(db.Integer, default=0)
    skill_level = db.Column(db.String(50), default='Beginner')  # Beginner, Intermediate, Advanced
    instructor_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    lessons = db.relationship('Lesson', backref='course', lazy='dynamic', cascade='all, delete-orphan')
    enrollments = db.relationship('Enrollment', backref='course', lazy='dynamic', cascade='all, delete-orphan')
    
    def get_total_lessons(self):
        return self.lessons.count()
    
    def get_user_progress(self, user_id):
        if not user_id:
            return 0
        enrollment = Enrollment.query.filter_by(user_id=user_id, course_id=self.id).first()
        if not enrollment:
            return 0
        
        total_lessons = self.get_total_lessons()
        if total_lessons == 0:
            return 0
            
        completed_lessons = LessonProgress.query.join(Lesson).filter(
            Lesson.course_id == self.id,
            LessonProgress.user_id == user_id,
            LessonProgress.is_completed == True
        ).count()
        
        return round((completed_lessons / total_lessons) * 100)
    
    def to_dict(self, current_user=None):
        user_progress = 0
        is_enrolled = False
        
        if current_user:
            user_progress = self.get_user_progress(current_user.id)
            is_enrolled = Enrollment.query.filter_by(
                user_id=current_user.id, 
                course_id=self.id
            ).first() is not None
        
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'category': self.category,
            'course_type': self.course_type,
            'thumbnail_url': self.thumbnail_url,
            'is_private': self.is_private,
            'price': self.price,
            'duration_hours': self.duration_hours,
            'skill_level': self.skill_level,
            'total_lessons': self.get_total_lessons(),
            'user_progress': user_progress,
            'is_enrolled': is_enrolled,
            'instructor': self.instructor.to_dict() if self.instructor else None,
            'created_at': (self.created_at or datetime.utcnow()).isoformat()
        }


class Lesson(db.Model):
    """Lezioni di un corso"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    content = db.Column(db.Text)  # Contenuto markdown
    video_url = db.Column(db.String(500))
    order_index = db.Column(db.Integer, default=0)
    duration_minutes = db.Column(db.Integer, default=0)
    is_free = db.Column(db.Boolean, default=False)  # Lezione gratuita
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships  
    progress = db.relationship('LessonProgress', backref='lesson', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self, current_user=None):
        user_completed = False
        if current_user:
            progress = LessonProgress.query.filter_by(
                user_id=current_user.id,
                lesson_id=self.id
            ).first()
            user_completed = progress.is_completed if progress else False
        
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'content': self.content,
            'video_url': self.video_url,
            'order_index': self.order_index,
            'duration_minutes': self.duration_minutes,
            'duration': self.duration_minutes,  # Alias per compatibilità frontend
            'is_free': self.is_free,
            'course_id': self.course_id,
            'user_completed': user_completed,
            'is_completed': user_completed,  # Alias per compatibilità frontend
            'created_at': (self.created_at or datetime.utcnow()).isoformat()
        }


class Enrollment(db.Model):
    """Iscrizioni degli utenti ai corsi"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'course_id', name='unique_user_course_enrollment'),)


class LessonProgress(db.Model):
    """Progresso delle lezioni"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lesson.id'), nullable=False)
    is_completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime)
    watch_time_seconds = db.Column(db.Integer, default=0)
    last_position_seconds = db.Column(db.Integer, default=0)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'lesson_id', name='unique_user_lesson_progress'),)
    

class DeletedAccount(db.Model):
    """Modello per tracciare account eliminati e feedback"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    deletion_reason = db.Column(db.String(500))
    feedback = db.Column(db.Text)
    deleted_at = db.Column(db.DateTime, default=datetime.utcnow)


# ========================================
# UTILITY
# ========================================

def get_current_user():
    """Ottieni utente corrente dalla sessione"""
    uid = session.get('user_id')
    if not uid:
        return None
    return db.session.get(User, uid)


def _seed_data():
    """Popola dati essenziali + corsi demo"""
    # Crea admin se non esiste
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@courseconnect.it',
            nome='Amministratore',
            cognome='CourseConnect',
            corso='Gestione Piattaforma',
            is_admin=True,
            bio='Gestisco la piattaforma CourseConnect per garantire la migliore esperienza a tutti i corsisti.'
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        
        # Post di benvenuto dell'admin
        if Post.query.count() == 0:
            welcome_post = Post(
                content='''🎉 **Benvenuti in CourseConnect!**

Il social network dedicato ai corsisti è finalmente online! 🚀

✨ **Cosa puoi fare:**
- 👥 **Connetterti** con altri corsisti da tutta Italia
- 📝 **Condividere** progetti, esperienze e successi
- 💡 **Scambiare** consigli, risorse e opportunità
- 📸 **Caricare immagini e video** nei tuoi post
- ❤️ **Mettere like** e commentare
- 🔗 **Creare collegamenti** con la community
- ⭐ **Lasciare recensioni** per aiutare altri corsisti
- 📚 **Accedere ai corsi** e tracciare i tuoi progressi

**Inizia subito a condividere la tua esperienza di apprendimento!**

*Insieme possiamo crescere più velocemente!* 📚✨

*Buon studio a tutti!*
**- Team CourseConnect**''',
                user_id=admin.id
            )
            db.session.add(welcome_post)
            db.session.commit()
            print("✅ Post di benvenuto creato!")
    
    # Crea corsi demo se non esistono
    if Course.query.count() == 0:
        demo_courses = [
            {
                'title': 'Fondamenti di Web Design Moderno',
                'description': 'Impara le basi del web design moderno con HTML5, CSS3 e JavaScript. Dalla teoria alla pratica con progetti reali e responsive design.',
                'category': 'Web Design',
                'course_type': 'CORSI',
                'thumbnail_url': 'https://images.unsplash.com/photo-1467232004584-a241de8bcf5d?w=400',
                'duration_hours': 40,
                'skill_level': 'Beginner',
                'instructor_id': admin.id
            },
            {
                'title': 'SEO e Posizionamento Avanzato',
                'description': 'Strategie professionali per posizionare il tuo sito web ai primi posti sui motori di ricerca. SEO tecnica, content marketing e link building.',
                'category': 'SEO e Marketing',
                'course_type': 'CORSI', 
                'thumbnail_url': 'https://images.unsplash.com/photo-1432888622747-4eb9a8efeb07?w=400',
                'duration_hours': 25,
                'skill_level': 'Intermediate',
                'instructor_id': admin.id
            },
            {
                'title': 'Sviluppo CMS e E-commerce',
                'description': 'Creazione completa di siti web dinamici e negozi online. Content Management Systems, database e sistemi di pagamento.',
                'category': 'Sviluppo Web',
                'course_type': 'CORSI',
                'thumbnail_url': 'https://images.unsplash.com/photo-1504384308090-c894fdcc538d?w=400',
                'duration_hours': 35,
                'skill_level': 'Intermediate',
                'instructor_id': admin.id
            },
            {
                'title': 'Business Digital e Acquisizione Clienti',
                'description': 'Strategie avanzate di marketing digitale per freelancer e agenzie. Sales funnel, automation e conversion optimization.',
                'category': 'Business e Marketing',
                'course_type': 'TRAINING',
                'thumbnail_url': 'https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=400',
                'duration_hours': 20,
                'skill_level': 'Advanced',
                'instructor_id': admin.id,
                'is_private': True
            }
        ]
        
        for course_data in demo_courses:
            course = Course(**course_data)
            db.session.add(course)
        
        db.session.commit()
        print("✅ Corsi demo creati!")
        
        # Aggiungi alcune lezioni demo
        courses = Course.query.all()
        for course in courses:
            for i in range(5):
                lesson = Lesson(
                    title=f'Lezione {i+1}: Introduzione a {course.category}',
                    description=f'In questa lezione imparerai i fondamenti di {course.category}',
                    content=f'''# Lezione {i+1}: {course.title}

## Obiettivi della lezione
- Comprendere i concetti base
- Applicare le tecniche apprese
- Completare gli esercizi pratici

## Contenuto
Questa è una lezione demo per il corso **{course.title}**.

### Argomenti trattati:
1. Introduzione teorica
2. Esempi pratici
3. Esercizi guidati
4. Verifica finale

*Durata stimata: 30 minuti*''',
                    order_index=i,
                    duration_minutes=30,
                    is_free=(i == 0),  # Prima lezione gratuita
                    course_id=course.id
                )
                db.session.add(lesson)
        
        db.session.commit()
        print("✅ Lezioni demo create!")


def create_tables():
    """Crea tabelle database e fa seed minimo (solo admin)."""
    db.create_all()
    _seed_data()


def _payload():
    """
    Estrae i dati sia da JSON che da form-data/x-www-form-urlencoded
    e normalizza chiavi alternative dal frontend.
    """
    if request.is_json:
        data = request.get_json(silent=True) or {}
    elif request.form:
        data = request.form.to_dict()
    else:
        try:
            data = json.loads((request.data or b'').decode('utf-8') or '{}')
        except Exception:
            data = {}

    # Alias comuni (inglese -> italiano)
    alias = {
        'firstName': 'nome',
        'lastName': 'cognome',
        'course': 'corso',
        'bioText': 'bio',
        'password1': 'password',
        'password_confirm': 'password',
    }
    for k, v in list(data.items()):
        if k in alias and alias[k] not in data:
            data[alias[k]] = v

    # Trim stringhe
    for k, v in list(data.items()):
        if isinstance(v, str):
            data[k] = v.strip()

    return data


def _allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_type(filename):
    """Determina se un file è immagine o video"""
    if not filename:
        return None
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in {'png', 'jpg', 'jpeg', 'gif', 'webp'}:
        return 'image'
    elif ext in {'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm'}:
        return 'video'
    return None

# ========================================
# API ROUTES
# ========================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check per monitoring"""
    try:
        db.session.execute(text('SELECT 1'))
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'users_count': User.query.count(),
            'posts_count': Post.query.count(),
            'comments_count': Comment.query.count(),
            'reviews_count': Review.query.count(),
            'courses_count': Course.query.count(),
            'enrollments_count': Enrollment.query.count(),
            'upload_folder': UPLOAD_FOLDER,
            'video_folder': VIDEO_FOLDER,
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e), 'timestamp': datetime.utcnow().isoformat()}), 500


@app.route('/api/register', methods=['POST'])
def register():
    """Registrazione nuovo utente (accetta JSON o form, con alias)"""
    try:
        data = _payload()
        required = ['username', 'email', 'nome', 'cognome', 'corso', 'password']
        missing = [k for k in required if not (data.get(k) or '').strip()]
        if missing:
            return jsonify({'error': 'Tutti i campi sono obbligatori', 'missing_fields': missing}), 400
        if len(data['password']) < 6:
            return jsonify({'error': 'La password deve avere almeno 6 caratteri'}), 400

        if User.query.filter_by(username=data['username']).first():
            return jsonify({'error': 'Username già in uso'}), 400
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email già registrata'}), 400

        user = User(
            username=data['username'],
            email=data['email'],
            nome=data['nome'],
            cognome=data['cognome'],
            corso=data['corso'],
            bio=(data.get('bio') or '')
        )
        user.set_password(data['password'])
        db.session.add(user)
        db.session.commit()

        session['user_id'] = user.id
        return jsonify({'message': 'Registrazione completata', 'user': user.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Errore registrazione: {str(e)}'}), 500


@app.route('/api/login', methods=['POST'])
def login():
    """Login utente (accetta JSON o form)"""
    try:
        data = _payload()
        username = (data.get('username') or '')
        password = (data.get('password') or '')
        if not username or not password:
            return jsonify({'error': 'Username e password richiesti'}), 400

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            return jsonify({'error': 'Credenziali non valide'}), 401

        session['user_id'] = user.id
        return jsonify({'message': 'Login effettuato', 'user': user.to_dict()})
    except Exception as e:
        return jsonify({'error': f'Errore login: {str(e)}'}), 500


@app.route('/api/logout', methods=['POST'])
def logout():
    """Logout utente"""
    session.pop('user_id', None)
    return jsonify({'message': 'Logout effettuato'})


@app.route('/api/me', methods=['GET'])
def get_current_user_info():
    """
    Informazioni utente corrente.
    Evitiamo 401 in console: se non autenticato, 200 con authenticated:false.
    """
    user = get_current_user()
    if not user:
        return jsonify({'authenticated': False, 'user': None})
    return jsonify({'authenticated': True, 'user': user.to_dict()})


# ======= USERS API =======
@app.route('/api/users', methods=['GET'])
def list_users():
    """Elenco ultimi utenti attivi (per sidebar)."""
    try:
        limit = request.args.get('limit', 20, type=int)
        q = (request.args.get('q') or '').strip()

        query = User.query.filter_by(is_active=True)
        if q:
            like = f"%{q.lower()}%"
            query = query.filter(
                db.or_(
                    db.func.lower(User.nome).like(like),
                    db.func.lower(User.cognome).like(like),
                    db.func.lower(User.username).like(like),
                )
            )
        users = query.order_by(User.created_at.desc()).limit(limit).all()
        return jsonify({'users': [u.to_dict() for u in users]})
    except Exception as e:
        return jsonify({'error': f'Errore caricamento utenti: {str(e)}'}), 500


# ======= POSTS =======

@app.route('/api/posts', methods=['GET'])
def get_posts():
    """Ottieni feed post (pubblico)"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        posts = Post.query.order_by(Post.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        current_user = get_current_user()
        return jsonify({
            'posts': [post.to_dict(current_user) for post in posts.items],
            'has_next': posts.has_next,
            'has_prev': posts.has_prev,
            'page': page,
            'total': posts.total
        })
    except Exception as e:
        return jsonify({'error': f'Errore caricamento post: {str(e)}'}), 500


@app.route('/api/posts', methods=['POST'])
def create_post():
    """Crea nuovo post (richiede login) - FIX VIDEO COMPLETO"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Login richiesto'}), 401

        # Log della richiesta
        print(f"🔍 POST Request - Content-Type: {request.content_type}")
        print(f"🔍 Form data: {dict(request.form)}")
        print(f"🔍 Files: {list(request.files.keys())}")

        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
            content = (data.get('content') or '').strip()
            file = None
            print("🔍 JSON request detected")
        else:
            content = request.form.get('content', '').strip()
            file = request.files.get('file')
            print(f"🔍 Form request detected - Content: {len(content)} chars")
            if file:
                print(f"🔍 File detected: {file.filename}, Size: {len(file.read())} bytes")
                file.seek(0)  # Reset file pointer dopo la lettura

        if not content:
            return jsonify({'error': 'Contenuto post richiesto'}), 400
        if len(content) > 4000:
            return jsonify({'error': 'Post troppo lungo (max 4000 caratteri)'}), 400

        post = Post(content=content, user_id=user.id)
        
        # Handle file upload con LOG COMPLETO
        if file and file.filename:
            print(f"🔍 Processing file: {file.filename}")
            print(f"🔍 File content type: {file.content_type}")
            print(f"🔍 File size: {len(file.read())} bytes")
            file.seek(0)  # Reset file pointer
            
            file_type = get_file_type(file.filename)
            print(f"🔍 File type detected: {file_type}")
            
            if file_type and _allowed_file(file.filename):
                import uuid
                filename = str(uuid.uuid4()) + '.' + file.filename.rsplit('.', 1)[1].lower()
                print(f"🔍 Generated filename: {filename}")
                
                if file_type == 'video':
                    # Save in videos subfolder
                    video_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'videos')
                    os.makedirs(video_folder, exist_ok=True)
                    filepath = os.path.join(video_folder, filename)
                    post.video_filename = f'videos/{filename}'
                    print(f"🎥 Saving video to: {filepath}")
                    print(f"🎥 Video filename in DB: {post.video_filename}")
                else:
                    # Save image in main folder
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    post.image_filename = filename
                    print(f"🖼️ Saving image to: {filepath}")
                    print(f"🖼️ Image filename in DB: {post.image_filename}")
                
                # Salva il file
                file.save(filepath)
                
                # Verifica che il file sia stato salvato
                if os.path.exists(filepath):
                    file_size = os.path.getsize(filepath)
                    print(f"✅ File saved successfully: {filepath} ({file_size} bytes)")
                else:
                    print(f"❌ File NOT saved: {filepath}")
                    return jsonify({'error': 'Errore salvataggio file'}), 500
            else:
                print(f"❌ File type not allowed: {file.filename}, type: {file_type}")
                return jsonify({'error': 'Formato file non supportato'}), 400

        # Salva nel database
        db.session.add(post)
        db.session.commit()
        print(f"✅ Post created successfully with ID: {post.id}")
        
        # Log del post creato
        post_dict = post.to_dict(user)
        print(f"✅ Post data: {post_dict}")

        return jsonify({'message': 'Post creato', 'post': post_dict})
    except Exception as e:
        print(f"💥 Error creating post: {str(e)}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'error': f'Errore creazione post: {str(e)}'}), 500


@app.route('/api/posts/<int:post_id>/like', methods=['POST'])
def toggle_like(post_id):
    """Metti/Togli like a post (richiede login)"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Login richiesto'}), 401

        post = db.session.get(Post, post_id)
        if not post:
            return jsonify({'error': 'Post non trovato'}), 404

        existing_like = Like.query.filter_by(user_id=user.id, post_id=post_id).first()
        if existing_like:
            db.session.delete(existing_like)
            action = 'removed'
        else:
            db.session.add(Like(user_id=user.id, post_id=post_id))
            action = 'added'

        db.session.commit()
        return jsonify({
            'action': action,
            'likes_count': post.get_likes_count(),
            'is_liked': post.is_liked_by(user)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Errore like: {str(e)}'}), 500


@app.route('/api/posts/<int:post_id>', methods=['DELETE'])
def delete_post(post_id):
    """Elimina post (solo l'autore può eliminare)"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Login richiesto'}), 401

        post = db.session.get(Post, post_id)
        if not post:
            return jsonify({'error': 'Post non trovato'}), 404

        # Solo l'autore o admin possono eliminare
        if post.user_id != user.id and not user.is_admin:
            return jsonify({'error': 'Non hai i permessi per eliminare questo post'}), 403

        # Elimina file se esistono
        if post.image_filename:
            try:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], post.image_filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"🗑️ Deleted image: {file_path}")
            except Exception as e:
                print(f"Could not delete image file: {e}")

        if post.video_filename:
            try:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], post.video_filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"🗑️ Deleted video: {file_path}")
            except Exception as e:
                print(f"Could not delete video file: {e}")

        # Elimina il post (cascade eliminerà automaticamente like e commenti)
        db.session.delete(post)
        db.session.commit()

        return jsonify({
            'message': 'Post eliminato con successo',
            'deleted_post_id': post_id
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Errore eliminazione post: {str(e)}'}), 500


# ======= COMMENTI API =======

@app.route('/api/posts/<int:post_id>/comments', methods=['GET'])
def get_comments(post_id):
    """Ottieni tutti i commenti di un post specifico"""
    try:
        post = db.session.get(Post, post_id)
        if not post:
            return jsonify({'error': 'Post non trovato'}), 404

        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)  # Molti commenti per pagina
        
        # Ordina commenti dal più vecchio al più nuovo (conversazione cronologica)
        comments_query = Comment.query.filter_by(post_id=post_id).order_by(Comment.created_at.asc())
        
        # Paginazione per post con molti commenti
        comments = comments_query.paginate(page=page, per_page=per_page, error_out=False)
        
        return jsonify({
            'comments': [comment.to_dict() for comment in comments.items],
            'total': comments.total,
            'page': page,
            'has_next': comments.has_next,
            'has_prev': comments.has_prev,
            'post_id': post_id
        })
    except Exception as e:
        return jsonify({'error': f'Errore caricamento commenti: {str(e)}'}), 500


@app.route('/api/posts/<int:post_id>/comments', methods=['POST'])
def create_comment(post_id):
    """Crea nuovo commento su un post (richiede login)"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Login richiesto per commentare'}), 401

        post = db.session.get(Post, post_id)
        if not post:
            return jsonify({'error': 'Post non trovato'}), 404

        data = _payload()
        content = (data.get('content') or '').strip()
        
        if not content:
            return jsonify({'error': 'Contenuto del commento richiesto'}), 400
        if len(content) > 1000:
            return jsonify({'error': 'Commento troppo lungo (max 1000 caratteri)'}), 400

        comment = Comment(
            content=content,
            user_id=user.id,
            post_id=post_id
        )
        db.session.add(comment)
        db.session.commit()

        return jsonify({
            'message': 'Commento aggiunto con successo',
            'comment': comment.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Errore creazione commento: {str(e)}'}), 500


@app.route('/api/comments/<int:comment_id>', methods=['DELETE'])
def delete_comment(comment_id):
    """Elimina commento (solo l'autore o admin può eliminare)"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Login richiesto'}), 401

        comment = db.session.get(Comment, comment_id)
        if not comment:
            return jsonify({'error': 'Commento non trovato'}), 404

        # Solo l'autore del commento o admin possono eliminare
        if comment.user_id != user.id and not user.is_admin:
            return jsonify({'error': 'Non hai i permessi per eliminare questo commento'}), 403

        # Elimina il commento
        db.session.delete(comment)
        db.session.commit()

        return jsonify({
            'message': 'Commento eliminato con successo',
            'deleted_comment_id': comment_id
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Errore eliminazione commento: {str(e)}'}), 500


# ======= RECENSIONI API =======
@app.route('/api/reviews', methods=['GET'])
def get_reviews():
    """Ottieni tutte le recensioni approvate"""
    try:
        reviews = Review.query.filter_by(is_approved=True).order_by(Review.created_at.desc()).all()
        return jsonify({
            'reviews': [review.to_dict() for review in reviews],
            'total': len(reviews)
        })
    except Exception as e:
        return jsonify({'error': f'Errore caricamento recensioni: {str(e)}'}), 500


@app.route('/api/reviews', methods=['POST'])
def create_review():
    """Crea nuova recensione (richiede login)"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Login richiesto'}), 401

        data = _payload()
        required = ['text', 'rating', 'photo_url']
        missing = [k for k in required if not data.get(k)]
        if missing:
            return jsonify({'error': 'Tutti i campi obbligatori richiesti', 'missing_fields': missing}), 400

        text = data['text'].strip()
        rating = int(data['rating'])
        photo_url = data['photo_url']
        location = (data.get('location') or '').strip()

        if not text or len(text) > 500:
            return jsonify({'error': 'Testo recensione richiesto (max 500 caratteri)'}), 400
        if rating < 1 or rating > 5:
            return jsonify({'error': 'Rating deve essere tra 1 e 5 stelle'}), 400

        # Controlla se l'utente ha già lasciato una recensione
        existing_review = Review.query.filter_by(user_id=user.id).first()
        if existing_review:
            return jsonify({'error': 'Hai già lasciato una recensione'}), 400

        review = Review(
            text=text,
            rating=rating,
            photo_url=photo_url,
            location=location,
            user_id=user.id
        )
        db.session.add(review)
        db.session.commit()

        return jsonify({
            'message': 'Recensione pubblicata con successo!',
            'review': review.to_dict()
        })
    except ValueError:
        return jsonify({'error': 'Rating deve essere un numero valido'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Errore creazione recensione: {str(e)}'}), 500


# ======= UPLOADS =======
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Serve file caricati"""
    print(f"📁 Serving file: /uploads/{filename}")
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=False)

@app.route('/static/uploads/<path:filename>')
def static_uploaded_file(filename):
    """Serve file caricati (route alternativa)"""
    print(f"📁 Serving static file: /static/uploads/{filename}")
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=False)


@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload generico per immagini (usato per recensioni, avatar, etc.)"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Login richiesto'}), 401

    if 'file' not in request.files:
        return jsonify({'error': 'Nessun file nel payload (campo "file")'}), 400

    f = request.files['file']
    if f.filename == '':
        return jsonify({'error': 'Filename vuoto'}), 400

    if not _allowed_file(f.filename):
        return jsonify({'error': 'Estensione non permessa'}), 400

    base = secure_filename(f.filename)
    name, ext = os.path.splitext(base)
    ts = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
    final_name = f"{user.id}_{ts}{ext.lower()}"

    save_path = os.path.join(app.config['UPLOAD_FOLDER'], final_name)
    f.save(save_path)

    file_url = f"/uploads/{final_name}"
    print(f"✅ File uploaded: {file_url}")
    return jsonify({'url': file_url, 'filename': base})


# ========================================
# ACCOUNT DELETION API
# ========================================

@app.route('/api/delete-account', methods=['POST'])
def delete_account():
    """Elimina account utente con feedback"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Non autorizzato'}), 401
        
        data = _payload()
        
        # Salva feedback sull'eliminazione
        deleted_account = DeletedAccount(
            username=user.username,
            email=user.email,
            deletion_reason=data.get('reason', ''),
            feedback=data.get('feedback', '')
        )
        db.session.add(deleted_account)
        
        # Elimina l'utente (cascade eliminerà post, commenti, like)
        db.session.delete(user)
        db.session.commit()
        
        # Pulisci sessione
        session.clear()
        
        print(f"Account deleted: {user.username}, Reason: {data.get('reason', 'No reason')}")
        
        return jsonify({
            'success': True,
            'message': 'Account eliminato con successo'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Account deletion error: {e}")
        return jsonify({'error': 'Errore durante l\'eliminazione dell\'account'}), 500


# ========================================
# API ROUTES CORSI
# ========================================

@app.route('/api/courses', methods=['GET'])
def get_courses():
    """Ottieni tutti i corsi"""
    try:
        category = request.args.get('category', '')
        course_type = request.args.get('type', '')
        skill_level = request.args.get('skill_level', '')
        free_only = request.args.get('free_only', '').lower() == 'true'
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 12, type=int)
        
        query = Course.query.filter_by(is_active=True)
        
        # Filtri
        if category:
            query = query.filter(Course.category.ilike(f'%{category}%'))
        if course_type:
            query = query.filter_by(course_type=course_type)
        if skill_level:
            query = query.filter_by(skill_level=skill_level)
        if free_only:
            query = query.filter_by(price=0.0)
        
        # Per utenti non loggati, mostra solo corsi pubblici
        current_user = get_current_user()
        if not current_user:
            query = query.filter_by(is_private=False)
        
        courses = query.order_by(Course.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        courses_data = []
        for course in courses.items:
            course_dict = course.to_dict(current_user)
            # Aggiungi conteggio iscritti
            course_dict['enrolled_count'] = Enrollment.query.filter_by(course_id=course.id, is_active=True).count()
            course_dict['lessons_count'] = course.get_total_lessons()
            courses_data.append(course_dict)
        
        return jsonify({
            'courses': courses_data,
            'total': courses.total,
            'page': page,
            'has_next': courses.has_next,
            'has_prev': courses.has_prev
        })
    except Exception as e:
        print(f"Errore get_courses: {e}")
        return jsonify({'error': f'Errore caricamento corsi: {str(e)}'}), 500


@app.route('/api/courses/<int:course_id>', methods=['GET'])
def get_course(course_id):
    """Ottieni dettagli di un singolo corso"""
    try:
        user = get_current_user()
        
        course = db.session.get(Course, course_id)
        if not course or not course.is_active:
            return jsonify({'error': 'Corso non trovato'}), 404
        
        # Per utenti non loggati, mostra solo corsi pubblici
        if not user and course.is_private:
            return jsonify({'error': 'Corso privato - accesso negato'}), 403
        
        # Conta iscrizioni
        enrolled_count = Enrollment.query.filter_by(course_id=course_id, is_active=True).count()
        
        course_data = course.to_dict(user)
        course_data['enrolled_count'] = enrolled_count
        course_data['lessons_count'] = course.get_total_lessons()
        
        return jsonify({
            'course': course_data,
            'message': 'Corso caricato con successo'
        })
    except Exception as e:
        print(f"Errore get_course: {e}")
        return jsonify({'error': f'Errore caricamento corso: {str(e)}'}), 500


@app.route('/api/courses', methods=['POST'])
def create_course():
    """Crea nuovo corso (solo admin/instructor) - CON UPLOAD IMMAGINE + FIX is_private"""
    try:
        user = get_current_user()
        if not user or not user.is_admin:
            return jsonify({'error': 'Solo gli amministratori possono creare corsi'}), 403
        
        # Gestisce sia JSON che form-data (come per i post)
        if request.is_json:
            data = request.get_json()
            file = None
            print("🔍 JSON request for course creation")
        else:
            data = request.form.to_dict()
            file = request.files.get('thumbnail')  # Campo per l'immagine del corso
            print("🔍 Form request for course creation")
        
        required = ['title', 'category', 'description']
        missing = [k for k in required if not data.get(k)]
        if missing:
            return jsonify({'error': 'Campi obbligatori mancanti', 'missing': missing}), 400
        
        thumbnail_url = data.get('thumbnail_url', '')
        
        # Gestione upload immagine
        if file and file.filename:
            print(f"🖼️ Processing course thumbnail: {file.filename}")
            
            if _allowed_file(file.filename) and get_file_type(file.filename) == 'image':
                import uuid
                filename = str(uuid.uuid4()) + '.' + file.filename.rsplit('.', 1)[1].lower()
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                
                file.save(filepath)
                
                if os.path.exists(filepath):
                    thumbnail_url = f"/uploads/{filename}"
                    print(f"✅ Course thumbnail saved: {thumbnail_url}")
                else:
                    return jsonify({'error': 'Errore salvataggio immagine'}), 500
            else:
                return jsonify({'error': 'Formato immagine non supportato per il corso'}), 400
        
        course = Course(
            title=data['title'],
            description=data['description'],
            category=data['category'],
            course_type=data.get('course_type', 'CORSI'),
            thumbnail_url=thumbnail_url,
            is_private=bool(data.get('is_private', False)),  # ← FIX: gestisce sia boolean che string
            price=float(data.get('price', 0)),
            duration_hours=int(data.get('duration_hours', 0)),
            skill_level=data.get('skill_level', 'Beginner'),
            instructor_id=user.id
        )
        
        db.session.add(course)
        db.session.commit()
        
        return jsonify({
            'message': 'Corso creato con successo',
            'course': course.to_dict(user)
        })
    except Exception as e:
        db.session.rollback()
        print(f"Errore create_course: {e}")
        return jsonify({'error': f'Errore creazione corso: {str(e)}'}), 500


@app.route('/api/courses/<int:course_id>/enroll', methods=['POST'])
def enroll_course(course_id):
    """Iscriviti a un corso"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Login richiesto'}), 401
        
        course = db.session.get(Course, course_id)
        if not course:
            return jsonify({'error': 'Corso non trovato'}), 404
        
        # Controlla se già iscritto
        existing = Enrollment.query.filter_by(user_id=user.id, course_id=course_id).first()
        if existing:
            return jsonify({'error': 'Già iscritto a questo corso'}), 400
        
        # Crea iscrizione
        enrollment = Enrollment(user_id=user.id, course_id=course_id)
        db.session.add(enrollment)
        db.session.commit()
        
        return jsonify({
            'message': 'Iscrizione completata con successo!',
            'course': course.to_dict(user)
        })
    except Exception as e:
        db.session.rollback()
        print(f"Errore enroll_course: {e}")
        return jsonify({'error': f'Errore iscrizione: {str(e)}'}), 500


@app.route('/api/courses/<int:course_id>/lessons', methods=['GET'])
def get_course_lessons(course_id):
    """Ottieni le lezioni di un corso - VERSIONE MIGLIORATA"""
    try:
        user = get_current_user()
        
        course = db.session.get(Course, course_id)
        if not course or not course.is_active:
            return jsonify({'error': 'Corso non trovato'}), 404
        
        # Controlla se l'utente può accedere al corso
        can_access = False
        enrollment = None
        if user:
            enrollment = Enrollment.query.filter_by(user_id=user.id, course_id=course_id).first()
            can_access = (enrollment and enrollment.is_active) or course.instructor_id == user.id or user.is_admin
        
        # Query delle lezioni
        query = Lesson.query.filter_by(course_id=course_id).order_by(Lesson.order_index)
        
        # Se non può accedere, mostra solo lezioni gratuite
        if not can_access:
            query = query.filter_by(is_free=True)
        
        lessons = query.all()
        
        return jsonify({
            'lessons': [lesson.to_dict(user) for lesson in lessons],
            'course': course.to_dict(user),
            'can_access_full_course': can_access,
            'total_lessons': len(lessons),
            'message': 'Lezioni caricate con successo'
        })
    except Exception as e:
        print(f"Errore get_course_lessons: {e}")
        return jsonify({'error': f'Errore caricamento lezioni: {str(e)}'}), 500


@app.route('/api/lessons/<int:lesson_id>', methods=['GET'])
def get_lesson(lesson_id):
    """Ottieni dettagli di una singola lezione"""
    try:
        user = get_current_user()
        
        lesson = db.session.get(Lesson, lesson_id)
        if not lesson:
            return jsonify({'error': 'Lezione non trovata'}), 404
        
        course = lesson.course
        if not course or not course.is_active:
            return jsonify({'error': 'Corso associato non trovato'}), 404
        
        # Controlla se l'utente può accedere alla lezione
        can_access = False
        if user:
            # Se è iscritto al corso o è l'instructore o è admin
            enrollment = Enrollment.query.filter_by(user_id=user.id, course_id=course.id).first()
            can_access = (enrollment and enrollment.is_active) or course.instructor_id == user.id or user.is_admin
        
        # Se non può accedere e la lezione non è gratuita
        if not can_access and not lesson.is_free:
            return jsonify({'error': 'Accesso negato - iscriviti al corso per accedere a questa lezione'}), 403
        
        lesson_data = lesson.to_dict(user)
        
        return jsonify({
            'lesson': lesson_data,
            'course': course.to_dict(user),
            'can_access': can_access,
            'message': 'Lezione caricata con successo'
        })
    except Exception as e:
        print(f"Errore get_lesson: {e}")
        return jsonify({'error': f'Errore caricamento lezione: {str(e)}'}), 500


@app.route('/api/lessons/<int:lesson_id>/complete', methods=['POST'])
def complete_lesson(lesson_id):
    """Segna lezione come completata"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Login richiesto'}), 401
        
        lesson = db.session.get(Lesson, lesson_id)
        if not lesson:
            return jsonify({'error': 'Lezione non trovata'}), 404
        
        # Controlla se l'utente è iscritto al corso
        enrollment = Enrollment.query.filter_by(
            user_id=user.id, 
            course_id=lesson.course_id
        ).first()
        if not enrollment:
            return jsonify({'error': 'Non sei iscritto a questo corso'}), 403
        
        # Trova o crea progress
        progress = LessonProgress.query.filter_by(
            user_id=user.id,
            lesson_id=lesson_id
        ).first()
        
        if not progress:
            progress = LessonProgress(user_id=user.id, lesson_id=lesson_id)
        
        progress.is_completed = True
        progress.completed_at = datetime.utcnow()
        
        db.session.add(progress)
        db.session.commit()
        
        # Calcola nuovo progresso del corso
        course_progress = lesson.course.get_user_progress(user.id)
        
        return jsonify({
            'message': 'Lezione completata!',
            'lesson_completed': True,
            'course_progress': course_progress
        })
    except Exception as e:
        db.session.rollback()
        print(f"Errore complete_lesson: {e}")
        return jsonify({'error': f'Errore completamento lezione: {str(e)}'}), 500


@app.route('/api/courses/<int:course_id>', methods=['DELETE'])
def delete_course(course_id):
    """Elimina corso (solo admin/instructor)"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Login richiesto'}), 401
        
        course = db.session.get(Course, course_id)
        if not course:
            return jsonify({'error': 'Corso non trovato'}), 404
        
        # Solo admin o instructore del corso possono eliminare
        if not user.is_admin and course.instructor_id != user.id:
            return jsonify({'error': 'Non hai i permessi per eliminare questo corso'}), 403
        
        # Elimina il corso (cascade eliminerà lezioni, iscrizioni, progressi)
        db.session.delete(course)
        db.session.commit()
        
        return jsonify({
            'message': 'Corso eliminato con successo',
            'deleted_course_id': course_id
        })
    except Exception as e:
        db.session.rollback()
        print(f"Errore delete_course: {e}")
        return jsonify({'error': f'Errore eliminazione corso: {str(e)}'}), 500


@app.route('/api/courses/<int:course_id>/progress', methods=['GET'])
def get_course_progress(course_id):
    """Ottieni progresso corso dell'utente"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Login richiesto'}), 401
        
        course = db.session.get(Course, course_id)
        if not course:
            return jsonify({'error': 'Corso non trovato'}), 404
        
        # Ottieni progresso dettagliato
        total_lessons = course.get_total_lessons()
        completed_lessons = LessonProgress.query.join(Lesson).filter(
            Lesson.course_id == course_id,
            LessonProgress.user_id == user.id,
            LessonProgress.is_completed == True
        ).count()
        
        progress_percentage = round((completed_lessons / total_lessons) * 100) if total_lessons > 0 else 0
        
        # Lezioni completate
        completed_lesson_ids = [
            p.lesson_id for p in LessonProgress.query.filter_by(
                user_id=user.id, is_completed=True
            ).all()
        ]
        
        return jsonify({
            'course_id': course_id,
            'progress_percentage': progress_percentage,
            'completed_lessons': completed_lessons,
            'total_lessons': total_lessons,
            'completed_lesson_ids': completed_lesson_ids,
            'course': course.to_dict(user)
        })
    except Exception as e:
        print(f"Errore get_course_progress: {e}")
        return jsonify({'error': f'Errore caricamento progresso: {str(e)}'}), 500


# ========================================
# API I MIEI CORSI
# ========================================

@app.route('/api/me/courses', methods=['GET'])
def get_my_courses():
    """Ottieni tutti i corsi a cui l'utente è iscritto"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Login richiesto'}), 401
        
        # Ottieni tutte le iscrizioni attive dell'utente
        enrollments = Enrollment.query.filter_by(
            user_id=user.id, 
            is_active=True
        ).all()
        
        enrolled_courses = []
        for enrollment in enrollments:
            course = enrollment.course
            if course and course.is_active:
                course_data = course.to_dict(user)
                
                # Aggiungi informazioni specifiche per l'iscrizione
                course_data.update({
                    'enrollment_date': enrollment.enrolled_at.isoformat() if enrollment.enrolled_at else None,
                    'is_completed': enrollment.completed_at is not None,
                    'completed_date': enrollment.completed_at.isoformat() if enrollment.completed_at else None,
                    'enrolled_count': Enrollment.query.filter_by(course_id=course.id, is_active=True).count(),
                    
                    # Link diretti per accedere al corso
                    'course_url': f'/courses/{course.id}',
                    'lessons_url': f'/courses/{course.id}/lessons',
                    'api_lessons_url': f'/api/courses/{course.id}/lessons',
                    'api_progress_url': f'/api/courses/{course.id}/progress',
                    
                    # Status utente
                    'can_access': True,
                    'enrollment_status': 'active'
                })
                
                enrolled_courses.append(course_data)
        
        # Aggiungi anche i corsi che l'utente insegna (se è admin)
        taught_courses = []
        if user.is_admin:
            instructor_courses = Course.query.filter_by(
                instructor_id=user.id, 
                is_active=True
            ).all()
            
            for course in instructor_courses:
                course_data = course.to_dict(user)
                course_data.update({
                    'role': 'instructor',
                    'enrolled_count': Enrollment.query.filter_by(course_id=course.id, is_active=True).count(),
                    'course_url': f'/courses/{course.id}',
                    'lessons_url': f'/courses/{course.id}/lessons',
                    'manage_url': f'/admin/courses/{course.id}',
                    'can_access': True,
                    'enrollment_status': 'instructor'
                })
                taught_courses.append(course_data)
        
        return jsonify({
            'enrolled_courses': enrolled_courses,
            'taught_courses': taught_courses,
            'total_enrolled': len(enrolled_courses),
            'total_taught': len(taught_courses),
            'user': user.to_dict(),
            'message': 'Corsi caricati con successo'
        })
        
    except Exception as e:
        print(f"Errore get_my_courses: {e}")
        return jsonify({'error': f'Errore caricamento corsi utente: {str(e)}'}), 500


@app.route('/api/me/enrollments', methods=['GET'])
def get_my_enrollments():
    """Ottieni statistiche dettagliate delle iscrizioni dell'utente"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Login richiesto'}), 401
        
        # Iscrizioni attive
        active_enrollments = Enrollment.query.filter_by(
            user_id=user.id, 
            is_active=True
        ).join(Course).filter(Course.is_active == True).all()
        
        # Statistiche generali
        total_progress = 0
        courses_data = []
        
        for enrollment in active_enrollments:
            course = enrollment.course
            progress = course.get_user_progress(user.id)
            total_progress += progress
            
            # Lezioni completate
            completed_lessons = LessonProgress.query.join(Lesson).filter(
                Lesson.course_id == course.id,
                LessonProgress.user_id == user.id,
                LessonProgress.is_completed == True
            ).count()
            
            course_info = {
                'id': course.id,
                'title': course.title,
                'category': course.category,
                'course_type': course.course_type,
                'thumbnail_url': course.thumbnail_url,
                'instructor': course.instructor.to_dict() if course.instructor else None,
                'progress_percentage': progress,
                'completed_lessons': completed_lessons,
                'total_lessons': course.get_total_lessons(),
                'enrolled_date': enrollment.enrolled_at.isoformat(),
                'is_completed': enrollment.completed_at is not None,
                'price': course.price,
                'duration_hours': course.duration_hours,
                
                # Link di accesso diretto
                'access_links': {
                    'course_page': f'/courses/{course.id}',
                    'lessons': f'/courses/{course.id}/lessons',
                    'continue_learning': f'/courses/{course.id}/lessons',
                    'certificate': f'/courses/{course.id}/certificate' if enrollment.completed_at else None
                }
            }
            courses_data.append(course_info)
        
        avg_progress = total_progress / len(active_enrollments) if active_enrollments else 0
        
        return jsonify({
            'enrollments': courses_data,
            'statistics': {
                'total_enrolled_courses': len(active_enrollments),
                'average_progress': round(avg_progress, 1),
                'completed_courses': len([e for e in active_enrollments if e.completed_at]),
                'in_progress_courses': len([e for e in active_enrollments if not e.completed_at])
            },
            'quick_access': {
                'continue_learning': [c for c in courses_data if c['progress_percentage'] > 0 and c['progress_percentage'] < 100],
                'new_courses': [c for c in courses_data if c['progress_percentage'] == 0],
                'completed_courses': [c for c in courses_data if c['progress_percentage'] == 100]
            }
        })
        
    except Exception as e:
        print(f"Errore get_my_enrollments: {e}")
        return jsonify({'error': f'Errore caricamento iscrizioni: {str(e)}'}), 500


# ========================================
# WEB ROUTES
# ========================================

@app.route('/')
def home():
    """Homepage"""
    return render_template('index.html')


# ========================================
# STARTUP: crea tabelle anche con gunicorn
# ========================================

with app.app_context():
    create_tables()


# ========================================
# DEV ENTRYPOINT (esecuzione locale)
# ========================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    print(f"🚀 CourseConnect avviato su porta {port}")
    print(f"📊 Admin: admin / admin123")
    print(f"⭐ Sistema recensioni: attivo")
    print(f"💬 Sistema commenti: attivo")
    print(f"🎥 Upload video: ATTIVO con DEBUG")
    print(f"🖼️ Upload immagini corso: ATTIVO")
    print(f"📚 I MIEI CORSI API: ATTIVI")
    print(f"🗑️ Eliminazione account: attivo")
    print(f"📁 Upload folder: {UPLOAD_FOLDER}")
    print(f"🎥 Video folder: {VIDEO_FOLDER}")
    print(f"🔧 ENDPOINT CORSI: FIXED - get_course() e get_lesson() aggiunti!")
    print(f"✅ FIX is_private: RISOLTO - gestisce boolean e string")
    app.run(host='0.0.0.0', port=port, debug=debug)
