from flask import Flask, render_template, request, jsonify
from scanner import run_scan

app = Flask(__name__)

@app.after_request
def no_cache(resp):
    # stop the browser serving stale HTML/JS between edits
    resp.headers["Cache-Control"] = "no-store"
    return resp

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/scan", methods=["POST"])
def scan():
    data = request.json
    
    client_id = data.get("client_id")
    access_token = data.get("access_token")
    tg_bot = data.get("tg_bot")
    tg_chat = data.get("tg_chat")
    
    if not client_id or not access_token:
        return jsonify({"status": "error", "message": "Client ID and Access Token are required."}), 400
        
    result = run_scan(client_id, access_token, tg_bot, tg_chat)
    
    if result.get("status") == "error":
        return jsonify(result), 400
        
    return jsonify(result)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
