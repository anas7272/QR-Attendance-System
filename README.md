📋 QR Attendance System
A smart, automated attendance system built with Python Flask. Teachers scan a QR code with their phone — the system automatically marks Check-In or Check-Out instantly. All data is saved to Google Sheets in real-time.

✨ Features

One QR Code — print it once, works forever
Auto Check-In / Check-Out — just scan, no buttons to press
New user? → Register once (name + phone + OTP) → never asked again
Existing user? → Just enter phone → instantly marked
Session memory — phone remembers you for 1 year, next scan is instant
Google Sheets sync — every record saved in real-time
Personal sheet per user — each teacher gets their own tab in Google Sheets
Master OTP — admin override code works for any phone
Interactive history — day-by-day list + bar graph view with search
Works on any phone — no app install needed, just camera


📸 How It Looks
Admin opens:  http://localhost:5000/
              → Beautiful QR code displayed on screen

Teacher scans QR:
  First time  → Enter name + phone + OTP → Registered + Checked In ✅
  Next time   → Enter phone → Auto Checked In ✅
  Scan again  → Auto Checked Out ✅ + Duration shown

🗂️ Google Sheets Structure
Your spreadsheet will have these tabs automatically created:
Sheet TabWhat it containsUsersAll registered teachers — phone, name, dateAll AttendanceEveryone's records in one placeRahul - 3210Rahul's personal attendance onlyPriya - 5678Priya's personal attendance only

🛠️ Requirements

Python 3.9 or higher
Google account (for Sheets)
fast2sms account (for OTP SMS) — optional, master OTP works without it


📦 Installation
Step 1 — Clone or download the project
bashgit clone https://github.com/yourusername/qr-attendance.git
cd qr-attendance/qr-v4
Or download ZIP → extract → open the qr-v4 folder.
Step 2 — Install Python packages
bashpip install -r requirements.txt
Step 3 — Set up Google Sheets
3a. Create spreadsheet

Go to sheets.google.com
Create new spreadsheet
Name it exactly: Attendance System

3b. Create service account

Go to console.cloud.google.com
Create new project → name it Attendance
Enable Google Sheets API + Google Drive API
Left menu → IAM & Admin → Service Accounts → Create
Name: attendance-bot → Role: Editor
Click the account → Keys tab → Add Key → JSON → Download
Rename downloaded file to credentials.json
Place credentials.json in the qr-v4 folder

3c. Share the spreadsheet

Open credentials.json in Notepad
Copy the client_email value (looks like attendance-bot@xxx.iam.gserviceaccount.com)
Go to your Google Sheet → Share → paste that email → Editor → Send

Step 4 — Configure run_local.py
Open run_local.py in Notepad and fill in:
pythonGOOGLE_CREDS_FILE = r"C:\path\to\your\qr-v4\credentials.json"
SHEET_NAME        = "Attendance System"   # must match exactly
FAST2SMS_KEY      = "your_fast2sms_key"  # or leave blank
DEBUG_MODE        = True                  # shows OTP on screen for testing
NGROK_TOKEN       = ""                    # optional, for internet access

🚀 Running the App
bashcd qr-v4
python run_local.py
You will see:
============================================================
  QR ATTENDANCE SYSTEM - READY
============================================================
  This PC    ->  http://localhost:5000
  Phone/WiFi ->  http://192.168.1.x:5000

  QR PAGE    ->  http://localhost:5000/
  DOWNLOAD   ->  http://localhost:5000/qr-image
============================================================
Open http://localhost:5000/ in your browser → the QR code appears.

📱 Using the System
For Admin

Run python run_local.py
Open http://localhost:5000/ in browser
Screenshot the QR code
Share it on WhatsApp to all teachers
OR print it and stick it at the entrance

For Teachers (First Time)

Scan QR code with phone camera
Enter your phone number
Enter your full name
Enter the OTP received on your phone
✅ Registered and Checked In automatically

For Teachers (Every Day After)

Scan QR code
Enter phone number
✅ Checked In instantly — no OTP needed

For Check-Out

Scan QR code again
Enter phone number
✅ Checked Out instantly — duration calculated automatically


🔑 OTP System
OTP TypeHow it worksReal SMS OTPSent via fast2sms to teacher's phoneMaster OTP: 786786Works for ANY phone, ANY time — admin overrideDebug OTPShown on screen when DEBUG_MODE=True

Note: Master OTP is hidden from users. Only admin knows it.


🌐 Making it Accessible on Mobile Data
By default the app only works on the same WiFi network. To make it work from anywhere:
Option A — ngrok (temporary URL, free)

Sign up at dashboard.ngrok.com
Copy your authtoken
In run_local.py set: NGROK_TOKEN = "your_token"
Restart the app — you'll get a public URL


⚠️ ngrok URL changes every restart

Option B — PythonAnywhere (permanent URL, free)

Sign up at pythonanywhere.com
Upload all files to /home/yourusername/mysite/
Set up WSGI file (see deployment section below)
Your permanent URL: https://yourusername.pythonanywhere.com

Option C — Railway (permanent URL, free)

Push code to GitHub
Connect to railway.app
Add environment variables
Get permanent URL


☁️ Deploying to PythonAnywhere (Free, Permanent)
Step 1 — Upload files

Go to Files tab → mysite folder
Upload: app.py, credentials.json, requirements.txt
Create templates folder → upload all HTML files from templates/

Step 2 — Install packages
Open Bash console:
bashmkvirtualenv --python=python3.11 myenv
pip install gspread google-auth google-auth-oauthlib qrcode[pil] pillow flask requests twilio
Step 3 — Configure WSGI
Web tab → click WSGI config file → delete everything → paste:
pythonimport sys, os

sys.path.insert(0, '/home/yourusername/mysite')

os.environ['SHEET_NAME']        = 'Attendance System'
os.environ['SECRET_KEY']        = 'any-random-string'
os.environ['DEBUG_MODE']        = 'false'
os.environ['SMS_PROVIDER']      = 'fast2sms'
os.environ['FAST2SMS_KEY']      = 'your_fast2sms_key'
os.environ['GOOGLE_CREDS_FILE'] = '/home/yourusername/mysite/credentials.json'
os.environ['APP_URL']           = 'https://yourusername.pythonanywhere.com'

from app import app as application
Step 4 — Set virtualenv
Web tab → Virtualenv section → enter:
/home/yourusername/.virtualenvs/myenv
Step 5 — Reload
Click Reload → open https://yourusername.pythonanywhere.com ✅

⚠️ Free PythonAnywhere expires every month — log in and click "Run until 1 month from today" to keep it running.


📊 Viewing Attendance History
Each teacher can view their own history at /history:

Mode 1: Day-by-Day — search by date, see each record
Mode 2: Bar Graph — visual 30-day overview with hover tooltips


🗄️ Managing Data (SQLite)
All user data is stored locally in attendance.db.
View all users:
cmdpython -c "import sqlite3; db=sqlite3.connect('attendance.db'); [print(u) for u in db.execute('SELECT * FROM users').fetchall()]"
Delete one user (replace phone number):
cmdpython -c "import sqlite3; db=sqlite3.connect('attendance.db'); db.execute('DELETE FROM users WHERE phone=?',('9876543210',)); db.execute('DELETE FROM att_cache WHERE phone=?',('9876543210',)); db.commit(); print('Deleted')"
Delete all except one user:
cmdpython -c "import sqlite3; db=sqlite3.connect('attendance.db'); db.execute('DELETE FROM users WHERE phone != ?',('9876543210',)); db.execute('DELETE FROM att_cache WHERE phone != ?',('9876543210',)); db.commit(); print('Done')"
Full reset:
cmdpython -c "import sqlite3; db=sqlite3.connect('attendance.db'); db.execute('DELETE FROM users'); db.execute('DELETE FROM att_cache'); db.commit(); print('Reset done')"

After deleting from SQLite, also delete from Google Sheets manually (Users tab + personal tab + All Attendance rows).


⚙️ Environment Variables
VariableDescriptionExampleAPP_URLYour app's public URLhttps://yourapp.pythonanywhere.comSECRET_KEYFlask secret key (any random string)abc123xyzSHEET_NAMEGoogle Sheet name (exact)Attendance SystemGOOGLE_CREDS_FILEPath to credentials.jsoncredentials.jsonGOOGLE_CREDS_JSONJSON content as string (for cloud deploy){"type":"service_account"...}SMS_PROVIDERSMS service to usefast2sms or twilioFAST2SMS_KEYfast2sms API keyABCxyz...TWILIO_SIDTwilio Account SIDACxxxxxxxxxTWILIO_TOKENTwilio Auth Tokenyour_tokenTWILIO_FROMTwilio phone number+1XXXXXXXXXXDEBUG_MODEShow OTP on screentrue or falsePORTServer port5000

📁 Project Structure
qr-v4/
├── app.py                  ← Main Flask application
├── run_local.py            ← Run locally with auto IP detection
├── credentials.json        ← Google service account (DO NOT commit)
├── attendance.db           ← SQLite database (auto-created)
├── requirements.txt        ← Python dependencies
├── Procfile                ← For Railway/Render deployment
├── railway.json            ← Railway config
├── render.yaml             ← Render config
├── Dockerfile              ← Docker config
├── attendance.service      ← Systemd service (Linux VPS)
├── nginx.conf              ← Nginx config (Linux VPS)
└── templates/
    ├── show_qr.html        ← QR display page (home page)
    ├── start.html          ← Phone number entry
    ├── register.html       ← New user registration
    ├── verify_otp.html     ← OTP verification
    ├── done.html           ← Check-in/out result
    ├── history.html        ← Attendance history + graphs
    └── attendance.html     ← Attendance page (legacy)

🐛 Troubleshooting
ProblemSolutioncredentials.json not foundCheck path in run_local.py → must be exact path to fileModuleNotFoundErrorRun pip install -r requirements.txtSheets not updatingCheck sheet is shared with service account emailSpreadsheetNotFoundCheck SHEET_NAME matches exactly including capitalsOTP not receivedSet DEBUG_MODE=True to show OTP on screen, or use master OTP 786786Only works on WiFiSet up ngrok or deploy to PythonAnywhere/RailwaySlow on first scanNormal — first scan checks Sheets, after that uses local cacheDouble entries in SheetsFixed in latest version — duplicate check before every write

🔒 Security Notes

Never commit credentials.json to GitHub — add it to .gitignore
Change SECRET_KEY to a random string in production
Keep DEBUG_MODE=false in production (hides OTP from screen)
Master OTP 786786 is only for admin use — not shown to users


📞 SMS Providers
fast2sms (India — Recommended)

Sign up at fast2sms.com
Dashboard → Dev API → copy API key
Cost: ₹1-2 per OTP
Set: FAST2SMS_KEY=your_key

Twilio (International)

Sign up at twilio.com
Free trial gives $15 credit
Set: SMS_PROVIDER=twilio, TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM


🙏 Built With

Flask — Python web framework
gspread — Google Sheets API
qrcode — QR code generation
SQLite — Local database
fast2sms — SMS OTP delivery


## 👨‍💻 Developer

## 👨‍💻 Developer

**Muhammad Anas**
- 📧 Email: anas.mleng@email.com
- 📱 Phone: +91-7067043139
- 🐙 GitHub: [anas7272](https://github.com/anas7272)
- 💼 LinkedIn: [Muhammad Anas](https://www.linkedin.com/in/muhammad-anas-15770327a)

> Built and designed by **Muhammad Anas** — All rights reserved.

---

> Built and designed by **Your Name** — All rights reserved.

---
