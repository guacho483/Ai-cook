# =============================================================
#  server.py  –  Ai-Cook  |  Server Flask principale
#
#  Avvio rapido:
#      pip install -r requirements.txt
#      python server.py
#
#  Il server ascolta su 0.0.0.0:5000 ed è raggiungibile da
#  tutte le macchine sulla stessa rete locale.
#
#  Endpoint:
#      POST /api/chat     – { "question": "..." } → { "answer": "..." }
#      GET  /api/health   – stato server, DB e Ollama
#      GET  /api/ricette  – lista ricette nel DB (debug)
# =============================================================

from flask import Flask, request, jsonify
from flask_cors import CORS

from config import SERVER_HOST, SERVER_PORT, DEBUG
from rag import cerca_ricette, costruisci_contesto, test_connection
from ollama_client import genera_risposta, test_ollama


# ── App Flask ─────────────────────────────────────────────────
app = Flask(__name__)

# CORS aperto: il frontend HTML gira su un'altra macchina
# con origine diversa, quindi servono gli header CORS.
CORS(app, resources={r"/api/*": {"origins": "*"}})


# ── POST /api/chat ────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Endpoint principale.

    Request JSON:
        { "question": "Come si fa il risotto?" }

    Response JSON (200):
        {
            "answer": "Ecco come preparare il risotto...",
            "ricette_trovate": 2
        }

    Response JSON (400):
        { "error": "messaggio di errore" }
    """
    data = request.get_json(silent=True)

    # Validazione input
    if not data or "question" not in data:
        return jsonify({"error": "Parametro 'question' mancante nel body JSON"}), 400

    question = data["question"].strip()

    if not question:
        return jsonify({"error": "La domanda non può essere vuota"}), 400

    if len(question) > 2000:
        return jsonify({"error": "Domanda troppo lunga (max 2000 caratteri)"}), 400

    # 1) RAG: cerca ricette pertinenti nel database
    ricette  = cerca_ricette(question)
    contesto = costruisci_contesto(ricette)

    # 2) Genera risposta con Ollama
    risposta = genera_risposta(question, contesto)

    return jsonify({
        "answer":          risposta,
        "ricette_trovate": len(ricette)
    }), 200


# ── GET /api/health ───────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health():
    """
    Verifica lo stato di tutti i componenti.
    Utile per testare la connettività dalla macchina frontend.

    Response JSON:
        {
            "server":   "ok",
            "database": "ok" | "error",
            "ollama":   "ok" | "error"
        }
    """
    db_ok     = test_connection()
    ollama_ok = test_ollama()

    stato = {
        "server":   "ok",
        "database": "ok" if db_ok     else "error",
        "ollama":   "ok" if ollama_ok else "error",
    }
    codice = 200 if (db_ok and ollama_ok) else 503
    return jsonify(stato), codice


# ── GET /api/ricette ──────────────────────────────────────────

@app.route("/api/ricette", methods=["GET"])
def list_ricette():
    """
    Restituisce le ultime ricette presenti nel DB.
    Utile per verificare che la pipeline dbConnection.py abbia funzionato.

    Query params:
        limit  – numero di ricette (default 20, max 100)
    """
    try:
        limit = min(int(request.args.get("limit", 20)), 100)
    except ValueError:
        limit = 20

    from rag import get_connection
    from mysql.connector import Error

    try:
        conn   = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT r.id_ricetta, r.nome, c.nome AS categoria,
                   r.difficolta, r.porzioni, r.sorgente_pdf
            FROM ricette r
            LEFT JOIN categorie c ON r.id_categoria = c.id_categoria
            ORDER BY r.id_ricetta DESC
            LIMIT %s
        """, (limit,))
        ricette = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({"ricette": ricette, "totale": len(ricette)}), 200

    except Error as e:
        return jsonify({"error": str(e)}), 500


# ── Avvio ─────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  Ai-Cook  |  Server Flask")
    print("=" * 55)

    print("[DB]     Connessione al database...", end=" ", flush=True)
    print("OK" if test_connection() else "ERRORE – controlla config.py")

    print("[Ollama] Connessione a Ollama.......", end=" ", flush=True)
    print("OK" if test_ollama() else "ERRORE – avvia Ollama prima del server")

    print(f"\n[Server] In ascolto su http://{SERVER_HOST}:{SERVER_PORT}")
    print(f"[Server] Endpoint chat:   POST http://<IP-QUESTA-MACCHINA>:{SERVER_PORT}/api/chat")
    print(f"[Server] Health check:    GET  http://<IP-QUESTA-MACCHINA>:{SERVER_PORT}/api/health")
    print("=" * 55)

    app.run(
        host=SERVER_HOST,
        port=SERVER_PORT,
        debug=DEBUG,
        use_reloader=False
    )
