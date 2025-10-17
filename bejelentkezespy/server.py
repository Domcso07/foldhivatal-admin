from flask import Flask, render_template, request, jsonify, make_response, redirect
import requests
import base64
import json
import os
from datetime import date, timedelta

app = Flask(__name__)

# --- Adatkezelés fájlban ---
DATA_FILE = "users.json"

def load_users():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return []

def save_users(users):
    with open(DATA_FILE, "w") as f:
        json.dump(users, f, indent=2)

users = load_users()

# --- Segédfüggvények ---
def get_current_user():
    """Visszaadja a bejelentkezett user objektumát a session cookie alapján."""
    cookie = request.cookies.get("session")
    if not cookie:
        return None
    try:
        decoded = base64.b64decode(cookie).decode()
        email = decoded.split(":", 1)[1]
        return next((u for u in users if u["email"] == email), None)
    except Exception:
        return None

def next_monday():
    """Következő hétfő dátuma."""
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)

def is_admin(user):
    """Admin jogosultság ellenőrzése."""
    return user and user["email"] == "domcso007@gmail.com"

# --- Példa házárak ---
house_prices = {
    1: 1500, 2: 1700, 3: 2450, 4: 2000, 5: 1000,
    6: 1000, 7: 2110, 8: 2050, 9: 1750, 10: 1350,
    11: 4500, 12: 1200, 13: 1250, 14: 4450, 15: 2350,
    16: 3100, 17: 2670, 18: 1950, 20: 3950, 21: 5000
}

# --- Discord OAuth2 beállítások ---
DISCORD_CLIENT_ID = "1428726706067345491"
DISCORD_CLIENT_SECRET = "UdJsCL_sQwVGAS62qvhEeuEg8zP0_oha"
DISCORD_REDIRECT_URI = "http://localhost:5000/api/discord/callback"

# --- Discord login ---
@app.route("/api/discord/login")
def discord_login():
    url = (
        "https://discord.com/api/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={DISCORD_REDIRECT_URI}"
        "&response_type=code&scope=identify%20email"
    )
    return redirect(url)

@app.route("/api/discord/callback")
def discord_callback():
    code = request.args.get("code")
    if not code:
        return "No code provided", 400

    # Token kérése
    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "scope": "identify email"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post("https://discord.com/api/oauth2/token", data=data, headers=headers)
    r.raise_for_status()
    tokens = r.json()

    # User info lekérése
    user_info = requests.get(
        "https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"}
    ).json()

    email = user_info.get("email") or f"discord_{user_info['id']}@discord.local"
    username = user_info.get("username")
    discord_id = user_info.get("id")

    # Ha nincs még user, létrehozzuk
    user = next((u for u in users if u["email"] == email), None)
    if not user:
        user = {
        "email": email,
        "username": username,
        "discord_id": discord_id,
        "houses": [],
        "payments": {},
        "paid_history": {}   # <<< fontos
    }
        users.append(user)
        save_users(users)


    # Session cookie beállítása
    token = base64.b64encode(f"user:{email}".encode()).decode()
    resp = make_response(redirect("/houses"))
    resp.set_cookie("session", token, httponly=True, samesite="Lax")
    return resp

# --- Oldalak ---
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/register")
def register_page():
    return render_template("register.html")

@app.route("/houses")
def houses_page():
    return render_template("houses.html")

@app.route("/admin")
def admin_page():
    user = get_current_user()
    if not is_admin(user):
        return "Nincs jogosultság", 403
    return render_template("admin.html", users=users)

# --- Admin API-k ---
@app.route("/api/admin/addhouse", methods=["POST"])
def admin_add_house():
    admin = get_current_user()
    if not is_admin(admin):
        return jsonify({"error": "Not authorized"}), 403

    data = request.get_json()
    email, house = data.get("email"), data.get("house")

    user = next((u for u in users if u["email"] == email), None)
    if not user:
        return jsonify({"error": "User not found"}), 404

    user.setdefault("houses", []).append(house)
    save_users(users)
    return jsonify({"ok": True, "houses": user["houses"]})

@app.route("/api/admin/removehouse", methods=["POST"])
def admin_remove_house():
    admin = get_current_user()
    if not is_admin(admin):
        return jsonify({"error": "Not authorized"}), 403

    data = request.get_json()
    email, house = data.get("email"), data.get("house")

    user = next((u for u in users if u["email"] == email), None)
    if not user:
        return jsonify({"error": "User not found"}), 404

    if house in user.get("houses", []):
        user["houses"].remove(house)
        save_users(users)
    return jsonify({"ok": True, "houses": user.get("houses", [])})

@app.route("/api/admin/setpayment", methods=["POST"])
def admin_set_payment():
    admin = get_current_user()
    if not is_admin(admin):
        return jsonify({"error": "Not authorized"}), 403

    data = request.get_json()
    email, house, due_date = data.get("email"), data.get("house"), data.get("due_date")

    user = next((u for u in users if u["email"] == email), None)
    if not user:
        return jsonify({"error": "User not found"}), 404

    user.setdefault("payments", {})[str(house)] = due_date
    save_users(users)
    return jsonify({"ok": True, "payments": user["payments"]})

@app.route("/api/admin/deleteuser", methods=["POST"])
def admin_delete_user():
    admin = get_current_user()
    if not is_admin(admin):
        return jsonify({"error": "Not authorized"}), 403

    data = request.get_json()
    email = data.get("email")

    global users
    users = [u for u in users if u["email"] != email]
    save_users(users)
    return jsonify({"ok": True})

@app.route("/api/admin/markpaid", methods=["POST"])
def admin_mark_paid():
    admin = get_current_user()
    if not is_admin(admin):
        return jsonify({"error": "Not authorized"}), 403

    data = request.get_json()
    email = data.get("email")
    house = str(data.get("house"))
    date_str = data.get("date")
    paid = data.get("paid", True)

    user = next((u for u in users if u["email"] == email), None)
    if not user:
        return jsonify({"error": "User not found"}), 404

    # biztosítjuk, hogy legyen paid_history
    user.setdefault("paid_history", {}).setdefault(house, [])

    # ha már van ilyen dátum, frissítjük
    for entry in user["paid_history"][house]:
        if entry["date"] == date_str:
            entry["paid"] = paid
            break
    else:
        # ha nincs, új bejegyzést adunk hozzá
        user["paid_history"][house].append({"date": date_str, "paid": paid})

    save_users(users)
    return jsonify({"ok": True, "history": user["paid_history"][house]})

# --- User API-k ---
@app.route("/api/logout", methods=["POST"])
def logout():
    resp = make_response(jsonify({"ok": True}))
    resp.set_cookie("session", "", httponly=True, samesite="Lax", max_age=0)
    return resp

@app.route("/api/me")
def me():
    user = get_current_user()
    if user:
        return jsonify({"logged_in": True, "email": user["email"]})
    return jsonify({"logged_in": False})

@app.route("/api/myhouses")
def my_houses():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    return jsonify({"houses": user.get("houses", [])})

@app.route("/api/payments")
def payments():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401

    payments = []
    for h in user.get("houses", []):
        history = []
        if "paid_history" in user and str(h) in user["paid_history"]:
            history = user["paid_history"][str(h)]
        payments.append({
            "house": h,
            "weekly_rent": house_prices.get(h),
            "next_due": user.get("payments", {}).get(str(h)),
            "paid_history": history
        })
    return jsonify({"payments": payments})

# --- Indítás ---
if __name__ == "__main__":
    app.run(port=5000, debug=True)
