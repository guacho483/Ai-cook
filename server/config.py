# =============================================================
#  config.py  –  Ai-Cook  |  Configurazione server Flask
#  *** MODIFICA QUESTI VALORI PRIMA DI AVVIARE IL SERVER ***
# =============================================================

# ── Database MySQL (macchina DB – XAMPP) ──────────────────────
DB_HOST     = "localhost"   # ← IP della macchina con XAMPP se su altra macchina
DB_PORT     = 3306
DB_USER     = "root"
DB_PASSWORD = ""            # vuota in XAMPP di default
DB_NAME     = "ricettario_db"

# ── Ollama (sulla stessa macchina del server) ─────────────────
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL    = "gemma3:4b"

# ── Flask ─────────────────────────────────────────────────────
SERVER_HOST = "0.0.0.0"    # 0.0.0.0 = visibile a tutta la rete locale
SERVER_PORT = 5000
DEBUG       = False         # True solo in fase di sviluppo

# ── RAG – ricerca ricette nel DB ─────────────────────────────
MAX_RICETTE_CONTESTO = 3    # max ricette da includere nel prompt
MAX_CONTESTO_CHARS   = 4000 # lunghezza massima blocco contesto (caratteri)

# ── Prompt di sistema per Ollama ─────────────────────────────
SYSTEM_PROMPT = (
    "Sei Chef AI, un assistente culinario esperto, cordiale e appassionato. "
    "Rispondi SEMPRE in italiano. "
    "Quando ti vengono fornite ricette nel contesto, usale come base per la tua risposta. "
    "Sii preciso con ingredienti e quantità. "
    "Formatta le risposte con Markdown: usa elenchi puntati per gli ingredienti, "
    "elenchi numerati per il procedimento. "
    "Se la ricetta non è nel contesto, rispondi comunque con consigli generali di cucina."
)
