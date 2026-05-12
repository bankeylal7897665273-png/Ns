import os
import requests
import pyqrcode
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = "vip_shop_super_secret_key_123"

FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "AIzaSyASlD4FM6lyIEzBAzPlflhlCwDc3Toh6Fo")
DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL", "https://earning-a9b0c-default-rtdb.firebaseio.com")
UPI_ID = os.getenv("UPI_ID", "7897803277@freecharge")
FC_COOKIE = os.getenv("FC_COOKIE", "HttpOnly_.freecharge.in	TRUE	/	TRUE	1783332750	app_fc	uE7hVQspD47b02A-fZuobEVi5aB97tMEoJnEjqz2dkR5GHDIMBxvYcqUCQJk-eFZgwJUebs3UtGwl09VliIc-Z1R9MEllacp8DgHwOzGHE-fFob76C3jdro8tz5DEBPM")

def db_get(path):
    url = f"{DATABASE_URL}/{path}.json"
    r = requests.get(url)
    return r.json() if r.ok else None

def db_put(path, data): requests.put(f"{DATABASE_URL}/{path}.json", json=data)
def db_post(path, data): return requests.post(f"{DATABASE_URL}/{path}.json", json=data).json()
def db_patch(path, data): requests.patch(f"{DATABASE_URL}/{path}.json", json=data)

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    r = requests.post(url, json={"email": data.get('email'), "password": data.get('password'), "returnSecureToken": True})
    if r.ok:
        session['user_id'] = r.json()['localId']
        session['email'] = data.get('email')
        return jsonify({"status": "success", "message": "Login Successful!"})
    return jsonify({"status": "error", "message": "Invalid credentials!"})

@app.route('/api/signup', methods=['POST'])
def api_signup():
    data = request.json
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    r = requests.post(url, json={"email": data.get('email'), "password": data.get('password'), "returnSecureToken": True})
    if r.ok:
        uid = r.json()['localId']
        session['user_id'] = uid
        session['email'] = data.get('email')
        db_put(f"shop_site/users/{uid}", {"email": data.get('email'), "balance": 0, "role": "user"})
        return jsonify({"status": "success", "message": "Account Created!"})
    return jsonify({"status": "error", "message": "Signup Failed! Email might exist."})

@app.route('/')
def index(): return redirect(url_for('dashboard')) if 'user_id' in session else render_template('auth.html')

@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html', user_email=session['email']) if 'user_id' in session else redirect(url_for('index'))

@app.route('/pay')
def pay_page(): return render_template('pay.html') if 'user_id' in session else redirect(url_for('index'))

@app.route('/api/projects', methods=['GET'])
def get_projects():
    if 'user_id' not in session: return jsonify({})
    uid = session['user_id']
    projects = db_get("shop_site/projects") or {}
    my_projects = db_get(f"shop_site/users/{uid}/my_projects") or {}
    
    # Check ownership
    for key, val in projects.items():
        if key in my_projects:
            val['owned'] = True
        else:
            val['owned'] = False
    return jsonify(projects)

@app.route('/api/add_project', methods=['POST'])
def add_project():
    data = request.json
    data['owner_id'] = session['user_id']
    data['status'] = 'pending' 
    db_post("shop_site/projects", data)
    return jsonify({"status": "success", "message": "Project sent for Admin approval!"})

@app.route('/api/generate_qr', methods=['POST'])
def generate_qr():
    data = request.json
    amount = data.get('amount')
    upi_url = f"upi://pay?pa={UPI_ID}&pn=VIPShop&am={amount}&cu=INR"
    qr = pyqrcode.create(upi_url)
    return jsonify({"qr": f"data:image/png;base64,{qr.png_as_base64_str(scale=5)}", "amount": amount})

@app.route('/api/verify_payment', methods=['POST'])
def verify_payment():
    data = request.json
    amount = str(data.get('amount'))
    project_id = data.get('project_id')
    buyer_id = session.get('user_id')
    
    # REAL COOKIE LOGIC
    headers = {"Cookie": FC_COOKIE, "User-Agent": "Mozilla/5.0"}
    payment_received = False
    try:
        # Pinging Freecharge or checking transaction history
        r = requests.get("https://www.freecharge.in/api/v1/user/transactions", headers=headers, timeout=5)
        history_data = r.text.upper()
        # Strictly checking if the amount and success status exists in recent history
        if amount in history_data and "SUCCESS" in history_data:
            payment_received = True
    except:
        payment_received = False 
        
    if payment_received:
        project = db_get(f"shop_site/projects/{project_id}")
        if project:
            seller_id = project.get('owner_id')
            seller_data = db_get(f"shop_site/users/{seller_id}")
            if seller_data:
                db_patch(f"shop_site/users/{seller_id}", {"balance": float(seller_data.get('balance', 0)) + float(amount)})
            db_put(f"shop_site/users/{buyer_id}/my_projects/{project_id}", project)
            return jsonify({"status": "success"})
            
    return jsonify({"status": "pending"})

@app.route('/api/profile_data', methods=['GET'])
def profile_data():
    uid = session.get('user_id')
    user_data = db_get(f"shop_site/users/{uid}") or {}
    my_projects = db_get(f"shop_site/users/{uid}/my_projects") or {}
    
    # Get all withdrawals
    all_withdrawals = db_get("shop_site/withdrawals") or {}
    my_withdrawals = {k: v for k, v in all_withdrawals.items() if v.get('user_id') == uid}
    
    return jsonify({
        "balance": user_data.get('balance', 0),
        "my_projects": my_projects,
        "history": my_withdrawals
    })

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    amount = float(data.get('amount'))
    uid = session.get('user_id')
    balance = float((db_get(f"shop_site/users/{uid}") or {}).get('balance', 0))
    
    if amount < 200: return jsonify({"status": "error", "message": "Min withdrawal ₹200"})
    if amount > balance: return jsonify({"status": "error", "message": "Not enough balance!"})
        
    db_patch(f"shop_site/users/{uid}", {"balance": balance - amount})
    db_post("shop_site/withdrawals", {"user_id": uid, "upi": data.get('upi'), "amount": amount, "status": "pending"})
    return jsonify({"status": "success", "message": "Withdrawal request sent!"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
