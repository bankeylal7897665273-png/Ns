import os
import time
import requests
import pyqrcode
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, db

# Load .env variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24) # Secure session key

# Firebase Config Initialization (Safe approach)
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY")
DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL")
UPI_ID = os.getenv("UPI_ID")
FC_COOKIE = os.getenv("FC_COOKIE")

# Initialize Firebase Admin
if not firebase_admin._apps:
    cred = credentials.Certificate({
        "type": "service_account",
        "project_id": os.getenv("FIREBASE_PROJECT_ID"),
        # Note: In a real production app, you need a serviceAccountKey.json 
        # For now, we simulate the db reference using REST API to match your config perfectly
    })
    firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})

# Helper function to interact with Firebase Realtime Database via REST
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

# Auth API using Firebase REST (Keeping it hidden from Frontend)
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
        # Create user profile in db
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
    # In real world, check if session['user_id'] is admin
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
    data['status'] = 'pending' # Needs admin approval
    db_post("shop_site/projects", data)
    return jsonify({"status": "success", "message": "Project sent for Admin approval!"})

@app.route('/api/generate_qr', methods=['POST'])
def generate_qr():
    data = request.json
    amount = data.get('amount')
    proj_id = data.get('project_id')
    # Generate UPI URI
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
    
    # ---------------------------------------------------------
    # FREECHARGE COOKIE VERIFICATION LOGIC (Automated)
    # ---------------------------------------------------------
    headers = {
        "Cookie": FC_COOKIE,
        "User-Agent": "Mozilla/5.0"
    }
    # Placeholder for actual Freecharge API transaction endpoint
    fc_api_url = "https://www.freecharge.in/api/v1/user/transactions" 
    
    try:
        # Pinging Freecharge with cookies to check latest history
        # r = requests.get(fc_api_url, headers=headers)
        # history = r.json()
        
        # simulated logic for verification (Remove True to use actual API response):
        payment_received = True 
        
        if payment_received:
            # Payment Success! Update Seller's Wallet
            project = db_get(f"shop_site/projects/{project_id}")
            seller_id = project.get('owner_id')
            
            # Add money to seller
            seller_data = db_get(f"shop_site/users/{seller_id}")
            new_balance = float(seller_data.get('balance', 0)) + float(amount)
            db_patch(f"shop_site/users/{seller_id}", {"balance": new_balance})
            
            # Record purchase for buyer
            db_put(f"shop_site/users/{buyer_id}/my_projects/{project_id}", project)
            
            return jsonify({"status": "success"})
    except Exception as e:
        pass
        
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
        
    # Deduct instantly
    db_patch(f"shop_site/users/{uid}", {"balance": balance - amount})
    
    # Send to admin
    db_post("shop_site/withdrawals", {
        "user_id": uid,
        "upi": user_upi,
        "amount": amount,
        "status": "pending"
    })
    return jsonify({"status": "success", "message": "Withdrawal request sent!"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
