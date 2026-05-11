"""
Import backdate attendance berdasarkan jadual
Run: python import_backdate.py
"""
from app import app, db
from models import User, Attendance
from datetime import datetime

def import_backdate():
    with app.app_context():
        # Tunjuk senarai pelajar
        print("\n=== SENARAI PELAJAR ===")
        students = User.query.filter_by(role='student').all()
        for s in students:
            print(f"ID: {s.id} | Nama: {s.full_name} | Email: {s.email}")
        
        # PILIH PELAJAR
        user_id = input("\nMasukkan User ID (tekan Enter untuk semua): ").strip()
        
        if user_id:
            user_ids = [int(user_id)]
        else:
            user_ids = [s.id for s in students]
        
        # ============================================
        # JADUAL KEHADIRAN (IKUT TABLE ANDA)
        # ============================================
        attendance_data = [
            # MAC 2026
            ('2026-03-16', 'Monday', '08:00', '17:00'),
            ('2026-03-17', 'Tuesday', '08:00', '17:00'),
            ('2026-03-18', 'Wednesday', '08:00', '17:00'),
            ('2026-03-19', 'Thursday', '08:00', '17:00'),
            # 20/03 Jumaat - CUTI (skip)
            # 21/03 Sabtu - Weekend
            # 22/03 Ahad - Weekend
            ('2026-03-23', 'Monday', '08:00', '17:00'),
            ('2026-03-24', 'Tuesday', '08:00', '17:00'),
            ('2026-03-25', 'Wednesday', '08:00', '17:00'),
            ('2026-03-26', 'Thursday', '08:00', '17:00'),
            ('2026-03-27', 'Friday', '08:00', '17:00'),
            # 28/03 Sabtu - Weekend
            # 29/03 Ahad - Weekend
            ('2026-03-30', 'Monday', '08:00', '17:00'),
            ('2026-03-31', 'Tuesday', '08:00', '17:00'),
            
            # APRIL 2026
            ('2026-04-01', 'Wednesday', '08:00', '17:00'),
            ('2026-04-02', 'Thursday', '08:00', '17:00'),
            # 03/04 Jumaat - CUTI (skip)
            # 04/04 Sabtu - Weekend
            # 05/04 Ahad - Weekend (tapi table ada 05/04 Jumaat? Check balik)
            # Kalau 05/04 memang ada:  (skip sebab table tunjuk Friday tapi 05/04/2026 adalah Ahad)
            # Saya ikut table: 05/04 ada, jadi tambah:
            ('2026-04-05', 'Friday', '08:00', '17:00'),  # Ikut table anda
            # 06/04 Sabtu - Weekend
            # 07/04 Ahad - Weekend
            ('2026-04-08', 'Monday', '08:00', '17:00'),
            ('2026-04-09', 'Tuesday', '08:00', '17:00'),
            # 10/04 Jumaat - CUTI (skip)
            ('2026-04-11', 'Wednesday', '08:00', '17:00'),  # Table tunjuk 11/04 tapi Wednesday? Check
            ('2026-04-12', 'Thursday', '08:00', '17:00'),
            ('2026-04-13', 'Friday', '08:00', '17:00'),
            ('2026-04-14', 'Monday', '08:00', '17:00'),
            ('2026-04-15', 'Tuesday', '08:00', '17:00'),
            # 16/04 - 17/04 CUTI (skip)
            ('2026-04-18', 'Wednesday', '08:00', '17:00'),  # Table tunjuk 18/04 Wednesday? Check
            ('2026-04-19', 'Thursday', '08:00', '17:00'),
            ('2026-04-20', 'Friday', '08:00', '17:00'),
        ]
        
        total = 0
        skip = 0
        
        for uid in user_ids:
            user = User.query.get(uid)
            if not user:
                print(f"[ERROR] User ID {uid} tidak wujud!")
                continue
            
            print(f"\n--- Import untuk: {user.full_name} ---")
            
            for date_str, day, time_in, time_out in attendance_data:
                check_in = datetime.strptime(f"{date_str} {time_in}", '%Y-%m-%d %H:%M')
                check_out = datetime.strptime(f"{date_str} {time_out}", '%Y-%m-%d %H:%M')
                
                # Check jika sudah wujud
                existing = Attendance.query.filter(
                    Attendance.user_id == uid,
                    db.func.date(Attendance.check_in) == date_str
                ).first()
                
                if existing:
                    print(f"  [SKIP] {date_str} ({day}) - sudah ada")
                    skip += 1
                    continue
                
                attendance = Attendance(
                    user_id=uid,
                    check_in=check_in,
                    check_out=check_out,
                    status='present',
                    location='Office'
                )
                db.session.add(attendance)
                total += 1
                print(f"  [OK] {date_str} ({day}) - {time_in} ~ {time_out}")
        
        db.session.commit()
        
        print(f"\n=== SELESAI! ===")
        print(f"Rekod ditambah: {total}")
        print(f"Rekod dilangkau: {skip}")

if __name__ == '__main__':
    import_backdate()