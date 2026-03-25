"""
QR Attendance System v4
Flow:
  1. Admin opens /show-qr  → sees beautiful unique QR on screen
  2. User scans QR         → lands on /  (start page)
  3. New user?             → /register (enter name) → OTP verify → attendance
  4. Existing user?        → OTP verify → attendance (check-in / check-out)

OTP Rules:
  - Real OTP sent via SMS (fast2sms / Twilio)
  - Master OTP = 786786  → works for ANY phone, ANY time (mod/admin override)
  - If SMS fails          → show OTP on screen in DEBUG_MODE
"""

from flask import Flask, request, render_template, redirect, url_for, session, send_file, jsonify, Response
import gspread
from google.oauth2.service_account import Credentials
import sqlite3, random, os, json, io, base64
from datetime import datetime, timedelta
import requests, qrcode, threading
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
from qrcode.image.styles.colormasks import RadialGradiantColorMask
from PIL import Image, ImageDraw
from io import BytesIO

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-secret-key')
app.permanent_session_lifetime = timedelta(days=365)

# ── CONFIG ─────────────────────────────────────────────────────
APP_URL      = os.environ.get('APP_URL', 'http://localhost:5000')
SHEET_NAME   = os.environ.get('SHEET_NAME', 'Attendance System')
SMS_PROVIDER = os.environ.get('SMS_PROVIDER', 'fast2sms')
FAST2SMS_KEY = os.environ.get('FAST2SMS_KEY', '')
TWILIO_SID   = os.environ.get('TWILIO_SID', '')
TWILIO_TOKEN = os.environ.get('TWILIO_TOKEN', '')
TWILIO_FROM  = os.environ.get('TWILIO_FROM', '')
DEBUG_MODE   = os.environ.get('DEBUG_MODE', 'false').lower() == 'true'
PORT         = int(os.environ.get('PORT', 5000))
_GCREDS_RAW  = os.environ.get('GOOGLE_CREDS_JSON', '')
_GCREDS_FILE = os.environ.get('GOOGLE_CREDS_FILE', 'credentials.json')
DB_PATH      = os.environ.get('DB_PATH', 'attendance.db')

MASTER_OTP   = '786786'   # ← works for every phone always

# ── SQLITE ─────────────────────────────────────────────────────
def get_db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with get_db() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                phone TEXT PRIMARY KEY,
                name  TEXT NOT NULL,
                registered_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS otp_store (
                phone      TEXT PRIMARY KEY,
                otp        TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS att_cache (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                phone     TEXT NOT NULL,
                name      TEXT NOT NULL,
                date      TEXT NOT NULL,
                check_in  TEXT,
                check_out TEXT,
                sheet_row INTEGER DEFAULT 0
            );
        ''')
        db.commit()

# ── GOOGLE SHEETS ───────────────────────────────────────────────
def _creds():
    scope = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    if _GCREDS_RAW:
        return Credentials.from_service_account_info(json.loads(_GCREDS_RAW), scopes=scope)
    return Credentials.from_service_account_file(_GCREDS_FILE, scopes=scope)

def gs_open():
    return gspread.authorize(_creds()).open(SHEET_NAME)

def ensure_sheets():
    """Create master sheets if they don't exist."""
    try:
        wb     = gs_open()
        titles = [ws.title for ws in wb.worksheets()]
        if 'Users' not in titles:
            ws = wb.add_worksheet('Users', 2000, 5)
            ws.append_row(['Phone', 'Name', 'Registered At', 'Total Days', 'Personal Sheet'])
            ws.format('A1:E1', {
                'textFormat': {'bold': True, 'foregroundColor': {'red':1,'green':1,'blue':1}},
                'backgroundColor': {'red':0.13,'green':0.37,'blue':0.13}
            })
        if 'All Attendance' not in titles:
            ws = wb.add_worksheet('All Attendance', 10000, 7)
            ws.append_row(['Phone', 'Name', 'Date',
                           'Check-In Time', 'Check-Out Time',
                           'Total Duration', 'Status'])
            ws.format('A1:G1', {
                'textFormat': {'bold': True, 'foregroundColor': {'red':1,'green':1,'blue':1}},
                'backgroundColor': {'red':0.13,'green':0.27,'blue':0.53}
            })
        print("[Sheets] ✅ Ready")
    except Exception as e:
        print(f"[Sheets] ensure_sheets: {e}")


def personal_sheet_name(name, phone):
    """Generate tab name like: Rahul - 9876 """
    short = phone[-4:] if len(phone) >= 4 else phone
    # Sheet title max 100 chars, no special chars
    safe_name = name[:30].replace('/', '-').replace(':', '-').replace('*', '')
    return f"{safe_name} - {short}"


def create_personal_sheet(wb, name, phone):
    """Create a personal attendance sheet tab for this user."""
    tab_name = personal_sheet_name(name, phone)
    titles   = [ws.title for ws in wb.worksheets()]
    if tab_name in titles:
        return tab_name   # already exists
    try:
        ws = wb.add_worksheet(tab_name, 2000, 6)
        # Header row with user info
        ws.update('A1', [[f'Attendance Record — {name}  ({phone})']])
        ws.update('A2', [['Date', 'Check-In Time', 'Check-Out Time',
                           'Total Duration', 'Status', 'Day']])
        # Style header
        ws.format('A1', {
            'textFormat': {'bold': True, 'fontSize': 13,
                           'foregroundColor': {'red':0.07,'green':0.24,'blue':0.37}},
            'backgroundColor': {'red':0.85,'green':0.93,'blue':0.98}
        })
        ws.format('A2:F2', {
            'textFormat': {'bold': True, 'foregroundColor': {'red':1,'green':1,'blue':1}},
            'backgroundColor': {'red':0.13,'green':0.37,'blue':0.13}
        })
        # Freeze header rows
        ws.freeze(rows=2)
        print(f"[Sheets] Created personal sheet: {tab_name}")
    except Exception as e:
        print(f"[Sheets] create_personal_sheet error: {e}")
    return tab_name


# ── USER HELPERS ────────────────────────────────────────────────
def user_exists(phone):
    """Check local SQLite ONLY — never hit Sheets on every request."""
    with get_db() as db:
        row = db.execute('SELECT name FROM users WHERE phone=?', (phone,)).fetchone()
    if row:
        return True, row['name']
    return False, None

def get_name(phone):
    _, name = user_exists(phone)
    return name

def add_user(phone, name):
    """
    Register new user — writes ONCE only.
    Checks Users sheet before inserting to prevent duplicates.
    """
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # Local cache
    with get_db() as db:
        db.execute('INSERT OR REPLACE INTO users VALUES (?,?,?)', (phone, name, now))
        db.commit()
    # Google Sheets — only if phone not already there
    # Google Sheets in BACKGROUND
    def write_sheets():
        try:
            wb         = gs_open()
            users_ws   = wb.worksheet('Users')
            all_phones = users_ws.col_values(1)[1:]
            if phone in all_phones:
                return
            tab_name = create_personal_sheet(wb, name, phone)
            users_ws.append_row([phone, name, now, '0', tab_name])
            print(f"[Sheets] Registered: {name} ({phone})")
        except Exception as e:
            print(f"[Sheets BG add_user] {e}")
    threading.Thread(target=write_sheets, daemon=True).start()

    
# ── ATTENDANCE HELPERS ──────────────────────────────────────────
def today_record(phone):
    today = datetime.now().strftime('%Y-%m-%d')
    with get_db() as db:
        row = db.execute(
            'SELECT * FROM att_cache WHERE phone=? AND date=? ORDER BY id DESC LIMIT 1',
            (phone, today)).fetchone()
    if row:
        return dict(row)
    # Sheets fallback — check personal sheet
    try:
        name     = get_name(phone)
        wb       = gs_open()
        tab_name = personal_sheet_name(name, phone)
        titles   = [ws.title for ws in wb.worksheets()]
        if tab_name in titles:
            data = wb.worksheet(tab_name).get_all_values()
            for i, row in enumerate(data[2:], start=3):   # skip 2 header rows
                if row and row[0] == today:
                    return {
                        'phone':     phone,
                        'name':      name,
                        'date':      row[0],
                        'check_in':  row[1] if len(row) > 1 and row[1] else None,
                        'check_out': row[2] if len(row) > 2 and row[2] else None,
                        'sheet_row': i,
                        'personal_tab': tab_name,
                    }
    except Exception as e:
        print(f"[Sheets] today_record personal: {e}")
    return None


def do_checkin(phone, name):
    today    = datetime.now().strftime('%Y-%m-%d')
    now      = datetime.now().strftime('%H:%M:%S')
    day_name = datetime.now().strftime('%A')

    # ✅ Save to local cache INSTANTLY (no delay)
    with get_db() as db:
        existing = db.execute(
            'SELECT id FROM att_cache WHERE phone=? AND date=? AND check_in IS NOT NULL',
            (phone, today)).fetchone()
        if not existing:
            db.execute(
                'INSERT INTO att_cache (phone,name,date,check_in,sheet_row) VALUES (?,?,?,?,?)',
                (phone, name, today, now, 0))
            db.commit()

    # ✅ Write to Google Sheets in BACKGROUND (user doesn't wait)
    def write_sheets():
        try:
            wb       = gs_open()
            tab_name = personal_sheet_name(name, phone)
            titles   = [ws.title for ws in wb.worksheets()]
            if tab_name not in titles:
                create_personal_sheet(wb, name, phone)
            personal_ws = wb.worksheet(tab_name)
            all_rows    = personal_ws.get_all_values()
            if not any(r and r[0] == today for r in all_rows[2:]):
                personal_ws.append_row([today, now, '', '', 'Checked In', day_name])
            master_ws   = wb.worksheet('All Attendance')
            master_rows = master_ws.get_all_values()
            if not any(len(r)>=3 and r[0]==phone and r[2]==today for r in master_rows[1:]):
                master_ws.append_row([phone, name, today, now, '', '', 'Checked In'])
        except Exception as e:
            print(f"[Sheets BG checkin] {e}")
    threading.Thread(target=write_sheets, daemon=True).start()
    return now


def do_checkout(phone, record):
    now  = datetime.now().strftime('%H:%M:%S')
    fmt  = '%H:%M:%S'
    try:
        dur = str(datetime.strptime(now, fmt) -
                  datetime.strptime(record['check_in'], fmt)).split('.')[0]
    except:
        dur = '--'
    today    = datetime.now().strftime('%Y-%m-%d')
    name     = record.get('name', get_name(phone))
    tab_name = personal_sheet_name(name, phone)

    # ✅ Update local cache INSTANTLY
    with get_db() as db:
        db.execute(
            'UPDATE att_cache SET check_out=? WHERE phone=? AND date=? AND check_out IS NULL',
            (now, phone, today))
        db.commit()

    # ✅ Update Google Sheets in BACKGROUND
    def write_sheets():
        try:
            wb     = gs_open()
            titles = [ws.title for ws in wb.worksheets()]
            if tab_name in titles:
                pws  = wb.worksheet(tab_name)
                srow = record.get('sheet_row', 0)
                if not srow or srow < 3:
                    data = pws.get_all_values()
                    for i, row in enumerate(data[2:], start=3):
                        if row and row[0] == today and row[1] == record['check_in']:
                            srow = i; break
                if srow >= 3:
                    pws.update_cell(srow, 3, now)
                    pws.update_cell(srow, 4, dur)
                    pws.update_cell(srow, 5, 'Checked Out')
            mws  = wb.worksheet('All Attendance')
            data = mws.get_all_values()
            for i, row in enumerate(data[1:], start=2):
                if len(row)>=4 and row[0]==phone and row[2]==today and row[3]==record['check_in']:
                    mws.update_cell(i, 5, now)
                    mws.update_cell(i, 6, dur)
                    mws.update_cell(i, 7, 'Checked Out')
                    break
        except Exception as e:
            print(f"[Sheets BG checkout] {e}")
    threading.Thread(target=write_sheets, daemon=True).start()
    return now, dur

def history(phone, limit=40):
    """Read history from personal sheet tab first, then cache."""
    # Local cache
    with get_db() as db:
        rows = db.execute(
            'SELECT * FROM att_cache WHERE phone=? ORDER BY date DESC LIMIT ?',
            (phone, limit)).fetchall()
    if rows:
        return [dict(r) for r in rows]
    # Personal sheet fallback
    try:
        name     = get_name(phone)
        wb       = gs_open()
        tab_name = personal_sheet_name(name, phone)
        titles   = [ws.title for ws in wb.worksheets()]
        result   = []
        if tab_name in titles:
            data = wb.worksheet(tab_name).get_all_values()
            for row in reversed(data[2:]):    # skip 2 header rows
                if row and row[0]:
                    result.append({
                        'date':      row[0],
                        'check_in':  row[1] if len(row) > 1 else '',
                        'check_out': row[2] if len(row) > 2 else '',
                    })
                    if len(result) >= limit: break
        return result
    except Exception as e:
        print(f"[Sheets] history: {e}")

    try:
        data = gs_open().worksheet('All Attendance').get_all_values()
        result = []
        for row in reversed(data[1:]):
            if row and row[0] == phone:
                result.append({
                    'date':      row[2] if len(row) > 2 else '',
                    'check_in':  row[3] if len(row) > 3 else '',
                    'check_out': row[4] if len(row) > 4 else '',
                })
                if len(result) >= limit: break
        return result
    except Exception as e:
        print(f"[Sheets] history: {e}"); return []

# ── OTP ─────────────────────────────────────────────────────────
def make_otp():
    return str(random.randint(100000, 999999))

def save_otp(phone, otp):
    exp = (datetime.now() + timedelta(minutes=10)).isoformat()
    with get_db() as db:
        db.execute('INSERT OR REPLACE INTO otp_store VALUES (?,?,?)', (phone, otp, exp))
        db.commit()

def validate_otp(phone, otp_input):
    otp_input = otp_input.strip()
    # MASTER OTP — always works
    if otp_input == MASTER_OTP:
        return True, 'OK'
    with get_db() as db:
        row = db.execute(
            'SELECT otp, expires_at FROM otp_store WHERE phone=?', (phone,)).fetchone()
    if not row:
        return False, 'No OTP found. Please resend.'
    if datetime.fromisoformat(row['expires_at']) < datetime.now():
        return False, 'OTP expired. Please resend.'
    if row['otp'] != otp_input:
        return False, 'Wrong OTP. Try again.'
    with get_db() as db:
        db.execute('DELETE FROM otp_store WHERE phone=?', (phone,))
        db.commit()
    return True, 'OK'

def send_sms(phone, otp):
    if DEBUG_MODE:
        print(f"[DEBUG] OTP for {phone}: {otp}")
        return True, otp
    if SMS_PROVIDER == 'twilio':
        try:
            from twilio.rest import Client
            Client(TWILIO_SID, TWILIO_TOKEN).messages.create(
                body=f"Your Attendance OTP: {otp}  (valid 10 min)",
                from_=TWILIO_FROM, to=f"+{phone}")
            return True, None
        except Exception as e:
            print(f"[Twilio] {e}"); return False, None
    else:
        try:
            r = requests.post(
                'https://www.fast2sms.com/dev/bulkV2',
                json={"route": "otp", "variables_values": otp,
                      "numbers": phone, "flash": 0},
                headers={"authorization": FAST2SMS_KEY}, timeout=10)
            return r.json().get('return', False), None
        except Exception as e:
            print(f"[fast2sms] {e}"); return False, None

# ── QR CODE GENERATOR ───────────────────────────────────────────
def make_qr_image(url):
    """Generate a styled, unique QR code with rounded modules and gradient."""
    qr = qrcode.QRCode(
        version=3,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=3,
    )
    qr.add_data(url)
    qr.make(fit=True)

    try:
        img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=RoundedModuleDrawer(),
            color_mask=RadialGradiantColorMask(
                back_color=(255, 255, 255),
                center_color=(15, 52, 96),
                edge_color=(6, 214, 160),
            )
        )
    except Exception:
        # Fallback to plain QR if styled fails
        img = qr.make_image(fill_color="#0f3460", back_color="white")

    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf

def qr_as_base64(url):
    buf = make_qr_image(url)
    return base64.b64encode(buf.read()).decode()

# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════


def _auto_mark(phone, name):
    """
    Core auto-logic:
    - Not checked in today  → check IN  immediately
    - Checked in, not out   → check OUT immediately
    - Both done             → return 'done' status
    Returns (action, time, duration)
    """
    record = today_record(phone)
    if not record or not record.get('check_in'):
        t = do_checkin(phone, name)
        return 'checkin', t, None, record
    elif not record.get('check_out'):
        t, dur = do_checkout(phone, record)
        return 'checkout', t, dur, record
    else:
        return 'done', record['check_in'], None, record


# ── ROOT = QR Display (show on screen / print / share) ──────────
@app.route('/')
def index():
    """
    This page SHOWS the QR code.
    Put this on a screen at the entrance OR screenshot/print it.
    The QR points to /scan
    """
    scan_url = APP_URL.rstrip('/') + '/scan'
    qr_b64   = qr_as_base64(scan_url)
    return render_template('show_qr.html', qr_b64=qr_b64, app_url=APP_URL)

@app.route('/show-qr')
def show_qr():
    return redirect(url_for('index'))

@app.route('/qr-image')
def qr_image():
    """Download the QR PNG to print or share on WhatsApp."""
    scan_url = APP_URL.rstrip('/') + '/scan'
    buf = make_qr_image(scan_url)
    return send_file(buf, mimetype='image/png',
                     as_attachment=True, download_name='attendance_qr.png')


# ── /scan — QR points here ───────────────────────────────────────
@app.route('/scan')
def scan():
    """
    User scans QR and lands here.
    IF session exists (phone known) → AUTO check-in or check-out RIGHT NOW.
    No buttons, no clicks.
    IF no session → go to phone entry.
    """
    phone = session.get('phone')
    if phone:
        exists, name = user_exists(phone)
        if exists:
            # ✅ AUTO MARK immediately
            action, t, dur, record = _auto_mark(phone, name)
            now_str = datetime.now().strftime('%H:%M:%S')
            today   = datetime.now().strftime('%A, %d %B %Y')
            return render_template('done.html',
                                   name=name, phone=phone,
                                   action=action, time=t,
                                   duration=dur, today=today,
                                   record=today_record(phone))
        session.clear()
    # No session → ask for phone
    return redirect(url_for('start'))


# ── /start — phone number entry ──────────────────────────────────
@app.route('/start', methods=['GET', 'POST'])
def start():
    """
    Enter phone number.
    Existing user → AUTO check-in/out immediately (no OTP needed).
    New user      → go to register (name + OTP required once).
    """
    if request.method == 'POST':
        phone = (request.form.get('phone', '')
                 .strip().lstrip('+')
                 .replace(' ', '').replace('-', ''))
        if not phone or not phone.isdigit() or len(phone) < 7:
            return render_template('start.html',
                                   error='Please enter a valid phone number.')

        exists, name = user_exists(phone)

        if exists:
            # ✅ EXISTING USER — auto mark attendance, no OTP
            session['phone'] = phone
            session.permanent = True
            action, t, dur, record = _auto_mark(phone, name)
            today = datetime.now().strftime('%A, %d %B %Y')
            return render_template('done.html',
                                   name=name, phone=phone,
                                   action=action, time=t,
                                   duration=dur, today=today,
                                   record=today_record(phone))
        else:
            # NEW USER — needs name + OTP (one time only)
            session['pending_phone'] = phone
            return redirect(url_for('register'))

    return render_template('start.html')


# ── /register — new users only (once in lifetime) ────────────────
@app.route('/register', methods=['GET', 'POST'])
def register():
    phone = session.get('pending_phone')
    if not phone:
        return redirect(url_for('start'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            return render_template('register.html',
                                   phone=phone, error='Please enter your full name.')
        session['reg_name'] = name
        otp = make_otp(); save_otp(phone, otp)
        ok, dbg = send_sms(phone, otp)
        return render_template('verify_otp.html',
                               phone=phone, name=name,
                               purpose='register',
                               sms_ok=ok,
                               debug_otp=dbg if DEBUG_MODE else None,
                               error=None)
    return render_template('register.html', phone=phone)


# ── /verify-otp — only for NEW user registration ─────────────────
@app.route('/verify-otp', methods=['POST'])
def verify_otp():
    phone   = request.form.get('phone', '').strip()
    otp_in  = request.form.get('otp', '').strip()
    purpose = request.form.get('purpose', 'register')
    name    = request.form.get('name', session.get('reg_name', '')).strip()

    ok, msg = validate_otp(phone, otp_in)
    if not ok:
        return render_template('verify_otp.html',
                               phone=phone, name=name, purpose=purpose,
                               sms_ok=True, debug_otp=None, error=msg)

    # Register the new user
    add_user(phone, name)

    # Set session
    session['phone'] = phone
    session.permanent = True
    session.pop('pending_phone', None)
    session.pop('reg_name', None)

    # ✅ NEW USER — always CHECK IN only, never checkout
    # Clear any old test records for today first
    today = datetime.now().strftime('%Y-%m-%d')
    with get_db() as db:
        db.execute('DELETE FROM att_cache WHERE phone=? AND date=?', (phone, today))
        db.commit()

    t = do_checkin(phone, name)
    return render_template('done.html',
                           name=name, phone=phone,
                           action='checkin', time=t,
                           duration=None, today=datetime.now().strftime('%A, %d %B %Y'),
                           record=today_record(phone))


# ── /resend-otp ───────────────────────────────────────────────────
@app.route('/resend-otp', methods=['POST'])
def resend_otp():
    phone   = request.form.get('phone', '').strip()
    name    = request.form.get('name', '').strip()
    purpose = request.form.get('purpose', 'register')
    otp = make_otp(); save_otp(phone, otp)
    ok, dbg = send_sms(phone, otp)
    return render_template('verify_otp.html',
                           phone=phone, name=name, purpose=purpose,
                           sms_ok=ok,
                           debug_otp=dbg if DEBUG_MODE else None,
                           message='New OTP sent!' if ok else None,
                           error=None)


# ── /history ──────────────────────────────────────────────────────
@app.route('/history')
def hist():
    phone = session.get('phone')
    if not phone: return redirect(url_for('start'))
    name    = get_name(phone)
    records = history(phone)
    return render_template('history.html',
                           name=name, phone=phone, records=records)


# ── /logout  /health ──────────────────────────────────────────────
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('start'))

@app.route('/health')
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


# ── STARTUP ───────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    ensure_sheets()
    scan_url = APP_URL.rstrip('/') + '/scan'
    print(f"\n{'='*58}")
    print(f"  QR Attendance System v5")
    print(f"{'='*58}")
    print(f"  QR Display  : http://localhost:5000/       ← open in browser")
    print(f"  QR points to: {scan_url}")
    print(f"  Download QR : http://localhost:5000/qr-image")
    # print(f"  Master OTP  : {MASTER_OTP}  (works for any phone)")
    print(f"  Debug Mode  : {DEBUG_MODE}")
    print(f"{'='*58}")
    print()
    print("  HOW IT WORKS:")
    print("  1. Open http://localhost:5000/ → take screenshot of QR")
    print("  2. Share QR image to teachers via WhatsApp")
    print("  3. Teacher scans QR:")
    print("     - New?      → name + phone + OTP → registered + checked in")
    print("     - Returning → just enter phone   → auto check-in")
    print("     - Scan again → auto check-out")
    print(f"{'='*58}\n")
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG_MODE)
