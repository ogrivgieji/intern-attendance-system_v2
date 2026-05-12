import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'attendance-secret-key-2024'
    
    basedir = os.path.abspath(os.path.dirname(__file__))
    
    # Guna DATABASE_URL dari Render jika ada (PostgreSQL)
    database_url = os.environ.get('DATABASE_URL', '')
    
    if database_url:
        # Render PostgreSQL - tukar 'postgres://' ke 'postgresql://'
        SQLALCHEMY_DATABASE_URI = database_url.replace('postgres://', 'postgresql://', 1)
    else:
        # Local development - SQLite
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'database.db')
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
