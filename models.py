from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """Model untuk pengguna (Admin dan Student)"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship dengan attendance
    attendances = db.relationship('Attendance', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Hash password sebelum simpan"""
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    
    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.full_name} ({self.role})>'

class Attendance(db.Model):
    """Model untuk rekod attendance"""
    __tablename__ = 'attendance'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    check_in = db.Column(db.DateTime, nullable=False)
    check_out = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='present')
    location = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Attendance User:{self.user_id} Date:{self.check_in.date()}>'
    
    @property
    def is_late(self):
        """Check jika check in lewat (selepas 9:00 AM)"""
        if self.check_in:
            return self.check_in.hour >= 9
        return False
    
    @property
    def duration(self):
        """Kira tempoh bekerja dalam format 'X jam Y minit'"""
        if self.check_in and self.check_out:
            duration = self.check_out - self.check_in
            total_minutes = int(duration.total_seconds() / 60)
            hours = total_minutes // 60
            minutes = total_minutes % 60
            
            if hours > 0 and minutes > 0:
                return f"{hours} jam {minutes} minit"
            elif hours > 0:
                return f"{hours} jam"
            else:
                return f"{minutes} minit"
        return "0 minit"
    
    @property
    def duration_hours(self):
        """Kira tempoh bekerja dalam jam (decimal)"""
        if self.check_in and self.check_out:
            duration = self.check_out - self.check_in
            hours = duration.total_seconds() / 3600
            return round(hours, 2)
        return 0