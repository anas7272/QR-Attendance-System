#!/usr/bin/env python3
import os, socket, sys

# ══════════════════════════════════════════════
#  FILL IN YOUR DETAILS HERE
# ══════════════════════════════════════════════

GOOGLE_CREDS_FILE = r"C:\Users\ASUS\Documents\QR\qr-attendance-v4\qr-v4\credentials.json"

SHEET_NAME   = "Attendance System"
FAST2SMS_KEY = ""        # paste fast2sms key or leave blank (786786 master OTP works)
DEBUG_MODE   = True      # OTP shown on screen
NGROK_TOKEN  = ""        # optional

# ══════════════════════════════════════════════

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def try_ngrok():
    try:
        from pyngrok import ngrok, conf
        if NGROK_TOKEN:
            conf.get_default().auth_token = NGROK_TOKEN
        tunnel = ngrok.connect(5000, "http")
        url = tunnel.public_url
        print(f"  ngrok URL: {url}")
        return url
    except ImportError:
        print("  pyngrok not installed - WiFi only mode")
        return None
    except Exception as e:
        print(f"  ngrok skipped: {e}")
        return None

if __name__ == '__main__':

    # 1. Check credentials file
    creds_path = os.path.abspath(GOOGLE_CREDS_FILE)
    if not os.path.exists(creds_path):
        print("\n" + "="*60)
        print("  ERROR: credentials.json NOT FOUND!")
        print("="*60)
        print(f"  Looking at: {creds_path}")
        print()
        print("  Fix: open run_local.py in Notepad")
        print("  Change GOOGLE_CREDS_FILE to your actual file path")
        print("="*60 + "\n")
        sys.exit(1)

    print(f"\n  credentials.json found OK")

    # 2. Set environment variables
    os.environ['GOOGLE_CREDS_FILE'] = creds_path
    os.environ['SHEET_NAME']        = SHEET_NAME
    os.environ['FAST2SMS_KEY']      = FAST2SMS_KEY
    os.environ['SMS_PROVIDER']      = 'fast2sms'
    os.environ['DEBUG_MODE']        = 'true' if DEBUG_MODE else 'false'
    os.environ['SECRET_KEY']        = 'local-dev-secret-key'

    # 3. Get URLs
    local_ip   = get_local_ip()
    local_url  = f"http://{local_ip}:5000"
    public_url = try_ngrok()
    app_url    = public_url if public_url else local_url
    os.environ['APP_URL'] = app_url

    # 4. Start app
    from app import app, init_db, ensure_sheets
    init_db()
    ensure_sheets()

    # 5. Print info
    print()
    print("="*60)
    print("  QR ATTENDANCE SYSTEM - READY")
    print("="*60)
    print(f"  This PC    ->  http://localhost:5000")
    print(f"  Phone/WiFi ->  {local_url}")
    if public_url:
        print(f"  Internet   ->  {public_url}")
    print()
    print(f"  QR PAGE    ->  http://localhost:5000/   <-- open this in browser!")
    print(f"               The QR appears here. Phones scan it.")
    print()
    print(f"  DOWNLOAD   ->  http://localhost:5000/qr-image")
    print()
    print(f"  Master OTP ->  786786  (always works)")
    print(f"  Debug Mode ->  {DEBUG_MODE}  (OTP shown on screen)")
    print(f"  Sheet      ->  {SHEET_NAME}")
    print("="*60)
    print()

    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
