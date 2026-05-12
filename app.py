import os
import pytz
from flask import Flask, render_template, redirect, url_for, flash, request, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime, date, timedelta
from functools import wraps
import pandas as pd
from io import BytesIO

from config import Config
from models import db, User, Attendance

def get_malaysia_time():
    """Dapatkan waktu Malaysia (UTC+8)"""
    malaysia_tz = pytz.timezone('Asia/Kuala_Lumpur')
    return datetime.now(malaysia_tz)

def create_app():
    """Factory function untuk create Flask app"""
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Initialize extensions
    db.init_app(app)
    
    # Setup Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Sila log masuk untuk akses halaman ini.'
    login_manager.login_message_category = 'warning'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Create database tables
    with app.app_context():
        # Pastikan folder instance wujud
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        db.create_all()
        print('[INFO] Database tables created successfully!')
        
        # Create default admin if not exists
        create_default_admin()
    
    return app

def create_default_admin():
    """Create default admin account jika tiada"""
    admin = User.query.filter_by(email='admin@intern.com').first()
    if not admin:
        admin = User(
            full_name='System Admin',
            email='admin@intern.com',
            role='admin',
            created_at=get_malaysia_time()
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print('[SUCCESS] Default admin created: admin@intern.com / admin123')

app = create_app()

# =============== DECORATORS ===============
def admin_required(f):
    """Decorator untuk restrict access kepada admin sahaja"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role != 'admin':
            flash('Akses ditolak. Anda tidak mempunyai kebenaran.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# =============== AUTH ROUTES ===============
@app.route('/')
def index():
    """Redirect ke login atau dashboard"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page untuk semua pengguna"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        if not email or not password:
            flash('Sila isi email dan password.', 'danger')
            return render_template('login.html')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user, remember=True)
            flash(f'Selamat datang, {user.full_name}!', 'success')
            
            # Redirect berdasarkan role
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        else:
            flash('Email atau password tidak sah.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Logout user"""
    logout_user()
    flash('Anda telah berjaya log keluar.', 'info')
    return redirect(url_for('login'))

# =============== DASHBOARD ROUTES ===============
@app.route('/dashboard')
@login_required
def dashboard():
    """Route dashboard berdasarkan role"""
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('student_dashboard'))

# =============== STUDENT ROUTES ===============
@app.route('/student/dashboard')
@login_required
def student_dashboard():
    """Dashboard untuk pelajar"""
    if current_user.role != 'student':
        return redirect(url_for('admin_dashboard'))
    
    # Check if already checked in today
    today = date.today()
    attendance_today = Attendance.query.filter(
        Attendance.user_id == current_user.id,
        db.func.date(Attendance.check_in) == today
    ).first()
    
    # Get recent attendance
    recent_attendances = Attendance.query.filter_by(user_id=current_user.id)\
        .order_by(Attendance.check_in.desc()).limit(10).all()
    
    # Calculate statistics
    total_attendance = Attendance.query.filter_by(user_id=current_user.id).count()
    late_count = Attendance.query.filter_by(user_id=current_user.id, status='late').count()
    
    return render_template('student/dashboard.html',
                         attendance_today=attendance_today,
                         recent_attendances=recent_attendances,
                         total_attendance=total_attendance,
                         late_count=late_count)

@app.route('/student/check-in', methods=['POST'])
@login_required
def check_in():
    """Check in untuk pelajar"""
    if current_user.role != 'student':
        return redirect(url_for('admin_dashboard'))
    
    today = date.today()
    
    # Check jika sudah check in hari ini
    existing = Attendance.query.filter(
        Attendance.user_id == current_user.id,
        db.func.date(Attendance.check_in) == today
    ).first()
    
    if existing:
        flash('Anda sudah check in hari ini.', 'warning')
        return redirect(url_for('student_dashboard'))
    
    # Guna waktu Malaysia
    now = get_malaysia_time()
    
    # Determine status (late after 9:00 AM)
    status = 'present'
    if now.hour >= 9:
        status = 'late'
    
    # Get location (optional)
    location = request.form.get('location', 'Not provided')
    
    # Create attendance record
    attendance = Attendance(
        user_id=current_user.id,
        check_in=now,
        status=status,
        location=location
    )
    
    db.session.add(attendance)
    db.session.commit()
    
    flash(f'Check in berjaya pada {now.strftime("%I:%M %p")}!', 'success')
    return redirect(url_for('student_dashboard'))

@app.route('/student/check-out', methods=['POST'])
@login_required
def check_out():
    """Check out untuk pelajar"""
    if current_user.role != 'student':
        return redirect(url_for('admin_dashboard'))
    
    today = date.today()
    
    # Cari attendance yang belum check out
    attendance = Attendance.query.filter(
        Attendance.user_id == current_user.id,
        db.func.date(Attendance.check_in) == today,
        Attendance.check_out == None
    ).first()
    
    if not attendance:
        flash('Tiada rekod check in ditemui untuk hari ini.', 'warning')
        return redirect(url_for('student_dashboard'))
    
    # Update check out time guna waktu Malaysia
    attendance.check_out = get_malaysia_time()
    db.session.commit()
    
    # Calculate hours
    duration = attendance.duration
    flash(f'Check out berjaya! Tempoh bekerja: {duration}.', 'success')
    return redirect(url_for('student_dashboard'))

@app.route('/student/history')
@login_required
def student_history():
    """Attendance history untuk pelajar"""
    if current_user.role != 'student':
        return redirect(url_for('admin_dashboard'))
    
    # Get filter parameters
    month = request.args.get('month', get_malaysia_time().month, type=int)
    year = request.args.get('year', get_malaysia_time().year, type=int)
    
    # Get attendance for selected month
    attendances = Attendance.query.filter(
        Attendance.user_id == current_user.id,
        db.extract('month', Attendance.check_in) == month,
        db.extract('year', Attendance.check_in) == year
    ).order_by(Attendance.check_in.desc()).all()
    
    return render_template('student/history.html',
                         attendances=attendances,
                         selected_month=month,
                         selected_year=year)

@app.route('/student/profile')
@login_required
def student_profile():
    """Profile page untuk pelajar"""
    if current_user.role != 'student':
        return redirect(url_for('admin_dashboard'))
    
    return render_template('student/profile.html')

# =============== ADMIN ROUTES ===============
@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    """Admin dashboard dengan statistik"""
    today = date.today()
    
    # Get statistics
    total_students = User.query.filter_by(role='student').count()
    
    # Get today's attendance
    today_attendance = Attendance.query.filter(
        db.func.date(Attendance.check_in) == today
    ).count()
    
    # Get late students today
    late_today = Attendance.query.filter(
        db.func.date(Attendance.check_in) == today,
        Attendance.status == 'late'
    ).count()
    
    # Get total attendance this month
    total_attendance_month = Attendance.query.filter(
        db.extract('month', Attendance.check_in) == today.month,
        db.extract('year', Attendance.check_in) == today.year
    ).count()
    
    # Get recent attendances
    recent_attendances = db.session.query(Attendance, User)\
    .join(User, Attendance.user_id == User.id)\
    .filter(User.role == 'student')\
    .filter(db.func.date(Attendance.check_in) == today)\
    .order_by(Attendance.check_in.desc())\
    .all()
    
    return render_template('admin/dashboard.html',
                         total_students=total_students,
                         today_attendance=today_attendance,
                         late_today=late_today,
                         total_attendance_month=total_attendance_month,
                         recent_attendances=recent_attendances,
                         today=today)

@app.route('/admin/attendance')
@login_required
@admin_required
def admin_attendance():
    """View all attendance records - grouped by student"""
    search = request.args.get('search', '').strip()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    status_filter = request.args.get('status', '')
    
    # Build query
    query = db.session.query(Attendance, User)\
        .join(User, Attendance.user_id == User.id)\
        .filter(User.role == 'student')
    
    if search:
        query = query.filter(User.full_name.ilike(f'%{search}%'))
    
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Attendance.check_in >= from_date)
        except ValueError:
            flash('Format tarikh mula tidak sah.', 'danger')
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(Attendance.check_in < to_date)
        except ValueError:
            flash('Format tarikh tamat tidak sah.', 'danger')
    
    if status_filter:
        query = query.filter(Attendance.status == status_filter)
    
    query = query.order_by(Attendance.check_in.desc())
    results = query.all()
    
    # Group by user
    from collections import OrderedDict
    grouped = OrderedDict()
    for attendance, user in results:
        if user not in grouped:
            grouped[user] = []
        grouped[user].append(attendance)
    
    return render_template('admin/attendance.html',
                         grouped=grouped,
                         search=search,
                         date_from=date_from,
                         date_to=date_to,
                         status_filter=status_filter)

@app.route('/admin/students')
@login_required
@admin_required
def admin_students():
    """Manage students"""
    students = User.query.filter_by(role='student').order_by(User.full_name).all()
    return render_template('admin/students.html', students=students)

@app.route('/admin/student/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_student():
    """Add new student"""
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        # Validation
        if not full_name or not email or not password:
            flash('Sila isi semua maklumat yang diperlukan.', 'danger')
            return render_template('admin/add_student.html')
        
        if len(password) < 6:
            flash('Password mesti sekurang-kurangnya 6 aksara.', 'danger')
            return render_template('admin/add_student.html')
        
        # Check if email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email telah digunakan.', 'danger')
            return render_template('admin/add_student.html')
        
        # Create new student
        new_student = User(
            full_name=full_name,
            email=email,
            role='student',
            created_at=get_malaysia_time()
        )
        new_student.set_password(password)
        
        db.session.add(new_student)
        db.session.commit()
        
        flash(f'Pelajar {full_name} berjaya didaftarkan!', 'success')
        return redirect(url_for('admin_students'))
    
    return render_template('admin/add_student.html')

@app.route('/admin/student/edit/<int:student_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_student(student_id):
    """Edit student details"""
    student = User.query.get_or_404(student_id)
    
    if student.role != 'student':
        flash('Hanya pelajar boleh diedit.', 'danger')
        return redirect(url_for('admin_students'))
    
    if request.method == 'POST':
        student.full_name = request.form.get('full_name', '').strip()
        student.email = request.form.get('email', '').strip()
        
        # Check if email already exists (except current student)
        existing = User.query.filter(User.email == student.email, User.id != student.id).first()
        if existing:
            flash('Email telah digunakan oleh pengguna lain.', 'danger')
            return render_template('admin/edit_student.html', student=student)
        
        # Optional password reset
        new_password = request.form.get('password', '')
        if new_password:
            if len(new_password) < 6:
                flash('Password mesti sekurang-kurangnya 6 aksara.', 'danger')
                return render_template('admin/edit_student.html', student=student)
            student.set_password(new_password)
        
        db.session.commit()
        flash(f'Maklumat {student.full_name} berjaya dikemaskini!', 'success')
        return redirect(url_for('admin_students'))
    
    return render_template('admin/edit_student.html', student=student)

@app.route('/admin/student/delete/<int:student_id>', methods=['POST'])
@login_required
@admin_required
def delete_student(student_id):
    """Delete student"""
    student = User.query.get_or_404(student_id)
    
    if student.role != 'student':
        flash('Hanya pelajar boleh dipadam.', 'danger')
        return redirect(url_for('admin_students'))
    
    student_name = student.full_name
    
    # Delete all attendance records first
    Attendance.query.filter_by(user_id=student.id).delete()
    db.session.delete(student)
    db.session.commit()
    
    flash(f'Pelajar {student_name} berjaya dipadam!', 'success')
    return redirect(url_for('admin_students'))

@app.route('/admin/reset-password/<int:student_id>', methods=['POST'])
@login_required
@admin_required
def reset_password(student_id):
    """Reset student password to default"""
    student = User.query.get_or_404(student_id)
    
    if student.role != 'student':
        flash('Hanya pelajar boleh reset password.', 'danger')
        return redirect(url_for('admin_students'))
    
    default_password = 'student123'
    student.set_password(default_password)
    db.session.commit()
    
    flash(f'Password untuk {student.full_name} telah direset ke: {default_password}', 'success')
    return redirect(url_for('admin_students'))

@app.route('/admin/export')
@login_required
@admin_required
def export_page():
    """Export attendance page"""
    return render_template('admin/export.html')

@app.route('/admin/export/excel')
@login_required
@admin_required
def export_excel():
    """Export attendance data to Excel"""
    # Get filter parameters
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Build query
    query = db.session.query(
        User.full_name,
        User.email,
        Attendance.check_in,
        Attendance.check_out,
        Attendance.status,
        Attendance.location
    ).join(User, Attendance.user_id == User.id)\
     .filter(User.role == 'student')
    
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Attendance.check_in >= from_date)
        except ValueError:
            flash('Format tarikh mula tidak sah.', 'danger')
            return redirect(url_for('export_page'))
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(Attendance.check_in < to_date)
        except ValueError:
            flash('Format tarikh tamat tidak sah.', 'danger')
            return redirect(url_for('export_page'))
    
    # Execute query
    results = query.order_by(Attendance.check_in.desc()).all()
    
    # Create DataFrame
    data = []
    for result in results:
        data.append({
            'Nama': result.full_name,
            'Email': result.email,
            'Check In': result.check_in.strftime('%Y-%m-%d %H:%M:%S') if result.check_in else '',
            'Check Out': result.check_out.strftime('%Y-%m-%d %H:%M:%S') if result.check_out else '',
            'Status': result.status.upper(),
            'Lokasi': result.location or 'N/A'
        })
    
    df = pd.DataFrame(data)
    
    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Attendance', index=False)
    
    output.seek(0)
    
    # Generate filename with timestamp
    filename = f'attendance_report_{get_malaysia_time().strftime("%Y%m%d_%H%M%S")}.xlsx'
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

@app.route('/admin/export/student/<int:user_id>/excel')
@login_required
@admin_required
def export_student_excel(user_id):
    """Export attendance untuk seorang pelajar sahaja (Excel)"""
    student = User.query.get_or_404(user_id)
    
    # Get filter parameters
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Build query untuk pelajar ini sahaja
    query = Attendance.query.filter_by(user_id=user_id)
    
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Attendance.check_in >= from_date)
        except ValueError:
            flash('Format tarikh mula tidak sah.', 'danger')
            return redirect(url_for('admin_attendance'))
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(Attendance.check_in < to_date)
        except ValueError:
            flash('Format tarikh tamat tidak sah.', 'danger')
            return redirect(url_for('admin_attendance'))
    
    results = query.order_by(Attendance.check_in.desc()).all()
    
    # Create DataFrame
    data = []
    for attendance in results:
        data.append({
            'Nama': student.full_name,
            'Email': student.email,
            'Tarikh': attendance.check_in.strftime('%d-%m-%Y') if attendance.check_in else '',
            'Check In': attendance.check_in.strftime('%H:%M:%S') if attendance.check_in else '',
            'Check Out': attendance.check_out.strftime('%H:%M:%S') if attendance.check_out else 'Belum',
            'Status': attendance.status.upper(),
            'Tempoh': attendance.duration,
            'Lokasi': attendance.location or 'N/A'
        })
    
    df = pd.DataFrame(data)
    
    # Create Excel file
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=f'Attendance_{student.full_name}', index=False)
    
    output.seek(0)
    
    filename = f'attendance_{student.full_name}_{get_malaysia_time().strftime("%Y%m%d")}.xlsx'
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

@app.route('/admin/export/student/<int:user_id>/csv')
@login_required
@admin_required
def export_student_csv(user_id):
    """Export attendance untuk seorang pelajar sahaja (CSV)"""
    import csv
    
    student = User.query.get_or_404(user_id)
    
    # Get all attendance for this student
    results = Attendance.query.filter_by(user_id=user_id)\
        .order_by(Attendance.check_in.desc()).all()
    
    # Create CSV
    output = BytesIO()
    output.write('\ufeff'.encode('utf-8'))  # BOM
    
    writer = csv.writer(output)
    writer.writerow(['Nama', 'Email', 'Tarikh', 'Check In', 'Check Out', 'Status', 'Tempoh', 'Lokasi'])
    
    for attendance in results:
        writer.writerow([
            student.full_name,
            student.email,
            attendance.check_in.strftime('%d-%m-%Y') if attendance.check_in else '',
            attendance.check_in.strftime('%H:%M:%S') if attendance.check_in else '',
            attendance.check_out.strftime('%H:%M:%S') if attendance.check_out else 'Belum',
            attendance.status.upper(),
            attendance.duration,
            attendance.location or 'N/A'
        ])
    
    output.seek(0)
    
    filename = f'attendance_{student.full_name}_{get_malaysia_time().strftime("%Y%m%d")}.csv'
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )    
@app.route('/admin/change-password', methods=['GET', 'POST'])
@login_required
@admin_required
def change_password():
    """Admin tukar password sendiri"""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validation
        if not current_password or not new_password or not confirm_password:
            flash('Sila isi semua maklumat.', 'danger')
            return redirect(url_for('change_password'))
        
        # Check current password
        if not current_user.check_password(current_password):
            flash('Password semasa tidak sah.', 'danger')
            return redirect(url_for('change_password'))
        
        # Check new password length
        if len(new_password) < 6:
            flash('Password baru mesti sekurang-kurangnya 6 aksara.', 'danger')
            return redirect(url_for('change_password'))
        
        # Check confirmation
        if new_password != confirm_password:
            flash('Pengesahan password tidak sepadan.', 'danger')
            return redirect(url_for('change_password'))
        
        # Update password
        current_user.set_password(new_password)
        db.session.commit()
        
        flash('Password berjaya ditukar! Sila login semula.', 'success')
        return redirect(url_for('login'))

    return render_template('admin/change_password.html')
    
@app.route('/admin/import-backdate')
@login_required
@admin_required
def import_backdate_page():
    """Halaman pilih pelajar untuk import backdate"""
    students = User.query.filter_by(role='student').order_by(User.full_name).all()
    
    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Import Backdate</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="bg-light">
        <div class="container mt-5">
            <div class="card shadow">
                <div class="card-header bg-primary text-white">
                    <h3>Import Backdate Attendance</h3>
                </div>
                <div class="card-body">
                    <p>Pilih pelajar untuk import data backdate (16 Mac - 11 Mei 2026).</p>
                    <div class="list-group">
    '''
    
    for s in students:
        html += f'''
            <a href="/admin/import-backdate/{s.id}" class="list-group-item list-group-item-action">
                <strong>{s.full_name}</strong> - {s.email}
            </a>
        '''
    
    html += '''
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    '''
    
    return html

@app.route('/admin/import-backdate/<int:user_id>')
@login_required
@admin_required
def import_backdate_run(user_id):
    """Run import backdate untuk satu pelajar"""
    import random
    
    def random_time_in():
        hour = random.choice([7, 7, 7, 7, 7, 8])
        minute = random.choice([55, 56, 57, 58, 59]) if hour == 7 else 0
        return f"{hour:02d}:{minute:02d}"
    
    def random_time_out():
        return f"17:{random.choice([0, 1, 2, 3, 4, 5]):02d}"
    
    attendance_dates = [
        '2026-03-16','2026-03-17','2026-03-18','2026-03-19',
        '2026-03-23','2026-03-24','2026-03-25','2026-03-26','2026-03-27',
        '2026-03-30','2026-03-31',
        '2026-04-01','2026-04-02',
        '2026-04-06','2026-04-07','2026-04-08','2026-04-09','2026-04-10',
        '2026-04-13','2026-04-14','2026-04-15','2026-04-16','2026-04-17',
        '2026-04-20','2026-04-21','2026-04-22','2026-04-23','2026-04-24',
        '2026-04-27','2026-04-28','2026-04-29','2026-04-30',
        '2026-05-04','2026-05-05','2026-05-06','2026-05-07','2026-05-08',
        '2026-05-11',
    ]
    
    total = 0
    skip = 0
    
    for date_str in attendance_dates:
        time_in = random_time_in()
        time_out = random_time_out()
        
        check_in = datetime.strptime(f"{date_str} {time_in}", '%Y-%m-%d %H:%M')
        check_out = datetime.strptime(f"{date_str} {time_out}", '%Y-%m-%d %H:%M')
        
        status = 'present'
        if check_in.hour >= 8 and check_in.minute > 0:
            status = 'late'
        
        existing = Attendance.query.filter(
            Attendance.user_id == user_id,
            db.func.date(Attendance.check_in) == date_str
        ).first()
        
        if existing:
            skip += 1
            continue
        
        attendance = Attendance(
            user_id=user_id,
            check_in=check_in,
            check_out=check_out,
            status=status,
            location='Office'
        )
        db.session.add(attendance)
        total += 1
    
    db.session.commit()
    flash(f'{total} rekod berjaya diimport! ({skip} dilangkau)', 'success')
    return redirect(url_for('admin_attendance'))
    @app.route('/admin/import-custom', methods=['GET', 'POST'])
@login_required
@admin_required
def import_custom():
    """Form import custom - pilih pelajar & taip tarikh"""
    import random
    
    if request.method == 'POST':
        user_id = request.form.get('user_id', type=int)
        dates_text = request.form.get('dates', '')
        
        if not user_id or not dates_text:
            flash('Sila pilih pelajar dan isi tarikh!', 'danger')
            return redirect(url_for('import_custom'))
        
        user = User.query.get(user_id)
        if not user:
            flash('Pelajar tidak dijumpai!', 'danger')
            return redirect(url_for('import_custom'))
        
        # Parse tarikh dari textarea (satu tarikh per line)
        attendance_dates = []
        for line in dates_text.strip().split('\n'):
            line = line.strip()
            if line:
                attendance_dates.append(line)
        
        def random_time_in():
            hour = random.choice([7, 7, 7, 7, 7, 8])
            minute = random.choice([55, 56, 57, 58, 59]) if hour == 7 else 0
            return f"{hour:02d}:{minute:02d}"
        
        def random_time_out():
            return f"17:{random.choice([0, 1, 2, 3, 4, 5]):02d}"
        
        total = 0
        skip = 0
        
        for date_str in attendance_dates:
            try:
                time_in = random_time_in()
                time_out = random_time_out()
                
                check_in = datetime.strptime(f"{date_str} {time_in}", '%Y-%m-%d %H:%M')
                check_out = datetime.strptime(f"{date_str} {time_out}", '%Y-%m-%d %H:%M')
                
                status = 'present'
                if check_in.hour >= 8 and check_in.minute > 0:
                    status = 'late'
                
                existing = Attendance.query.filter(
                    Attendance.user_id == user_id,
                    db.func.date(Attendance.check_in) == date_str
                ).first()
                
                if existing:
                    skip += 1
                    continue
                
                attendance = Attendance(
                    user_id=user_id,
                    check_in=check_in,
                    check_out=check_out,
                    status=status,
                    location='Office'
                )
                db.session.add(attendance)
                total += 1
            except:
                continue
        
        db.session.commit()
        flash(f'{total} rekod diimport untuk {user.full_name}! ({skip} dilangkau)', 'success')
        return redirect(url_for('admin_attendance'))
    
    students = User.query.filter_by(role='student').order_by(User.full_name).all()
    return render_template('admin/import_custom.html', students=students)
# =============== ERROR HANDLERS ===============
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# =============== MAIN ===============
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
