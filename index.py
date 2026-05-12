import os
import time
import requests
import pyqrcode
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv

# Load .env (agar available ho)
load_dotenv()

app = Flask(__name__)
app.secret_key = "vip_shop_super_secret_key_123" # Fixed key so it never crashes

# ---------------------------------------------------------
# SMART FALLBACK SYSTEM (No crash if .env is missing on Render)
# ---------------------------------------------------------
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "AIzaSyASlD4FM6lyIEzBAzPlflhlCwDc3Toh6Fo")
DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL", "https://earning-a9b0c-default-rtdb.firebaseio.com")
UPI_ID = os.getenv("UPI_ID", "7897803277@freecharge")
FC_COOKIE = os.getenv("FC_COOKIE", "HttpOnly_.freecharge.in	TRUE	/	TRUE	1783332750	app_fc	uE7hVQspD47b02A-fZuobEVi5aB97tMEoJnEjqz2dkR5GHDIMBxvYcqUCQJk-eFZgwJUebs3UtGwl09VliIc-Z1R9MEllacp8DgHwOzGHE-fFob76C3jdro8tz5DEBPM")

# Helper function to interact with Firebase via Safe REST API
def db_get(path):
    url = f"{DATABASE_URL}/{path}.json"
    response = requests.get(url)
    return response.json() if response.ok else None

def db_put(path, data):
    url = f"{DATABASE_URL}/{path}.json"
    requests.put(url, json=data)

def db_post(path, data):
    url = f"{DATABASE_URL}/{path}.json"
    response = requests.post(url, json=data)
    return response.json()

def db_patch(path, data):
    url = f"{DATABASE_URL}/{path}.json"
    requests.patch(url, json=data)

# Auth API
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    r = requests.post(url, json=payload)
    if r.ok:
        res = r.json()
        session['user_id'] = res['localId']
        session['email'] = email
        return jsonify({"status": "success", "message": "Login Successful!"})
    return jsonify({"status": "error", "message": "Invalid credentials!"})

@app.route('/api/signup', methods=['POST'])
def api_signup():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    r = requests.post(url, json=payload)
    if r.ok:
        res = r.json()
        uid = res['localId']
        session['user_id'] = uid
        session['email'] = email
        db_put(f"shop_site/users/{uid}", {
            "email": email,
            "balance": 0,
            "role": "user"
        })
        return jsonify({"status": "success", "message": "Account Created!"})
    return jsonify({"status": "error", "message": "Signup Failed! Email might exist."})

# ---------------- HTML ROUTES ----------------

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('auth.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template('dashboard.html', user_email=session['email'])

@app.route('/admin')
def admin_panel():
    return render_template('admin.html')

@app.route('/pay')
def pay_page():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template('pay.html')

# ---------------- API ROUTES ----------------

@app.route('/api/projects', methods=['GET'])
def get_projects():
    projects = db_get("shop_site/projects") or {}
    return jsonify(projects)

@app.route('/api/add_project', methods=['POST'])
def add_project():
    if 'user_id' not in session: return jsonify({"status": "error"}), 401
    data = request.json
    data['owner_id'] = session['user_id']
    data['status'] = 'pending' 
    db_post("shop_site/projects", data)
    return jsonify({"status": "success", "message": "Project sent for Admin approval!"})

@app.route('/api/generate_qr', methods=['POST'])
def generate_qr():
    data = request.json
    amount = data.get('amount')
    proj_id = data.get('project_id')
    upi_url = f"upi://pay?pa={UPI_ID}&pn=VIPShop&am={amount}&cu=INR"
    qr = pyqrcode.create(upi_url)
    qr_base64 = qr.png_as_base64_str(scale=5)
    return jsonify({"qr": f"data:image/png;base64,{qr_base64}", "amount": amount})

@app.route('/api/verify_payment', methods=['POST'])
def verify_payment():
    data = request.json
    amount = data.get('amount')
    project_id = data.get('project_id')
    buyer_id = session.get('user_id')
    
    # Simple simulated success logic for now (No crash)
    payment_received = True 
    
    if payment_received:
        project = db_get(f"shop_site/projects/{project_id}")
        if project:
            seller_id = project.get('owner_id')
            seller_data = db_get(f"shop_site/users/{seller_id}")
            if seller_data:
                new_balance = float(seller_data.get('balance', 0)) + float(amount)
                db_patch(f"shop_site/users/{seller_id}", {"balance": new_balance})
            
            db_put(f"shop_site/users/{buyer_id}/my_projects/{project_id}", project)
            return jsonify({"status": "success"})
            
    return jsonify({"status": "pending"})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    amount = float(data.get('amount'))
    user_upi = data.get('upi')
    uid = session.get('user_id')
    
    user_data = db_get(f"shop_site/users/{uid}")
    balance = float(user_data.get('balance', 0))
    
    if amount < 200:
        return jsonify({"status": "error", "message": "Min withdrawal is ₹200"})
    if amount > balance:
        return jsonify({"status": "error", "message": "Not enough balance!"})
        
    db_patch(f"shop_site/users/{uid}", {"balance": balance - amount})
    
    db_post("shop_site/withdrawals", {
        "user_id": uid,
        "upi": user_upi,
        "amount": amount,
        "status": "pending"
    })
    return jsonify({"status": "success", "message": "Withdrawal request sent!"})

# Render gunicorn use karega, fallback humne de diya hai
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
