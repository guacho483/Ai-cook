import os
import re
import json
import uuid
import logging
from pathlib import Path

from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import Chroma
import ollama
import mysql.connector
from mysql.connector import Error


# ─────────────────────────────────────────────
#  CONFIGURAZIONE
# ─────────────────────────────────────────────

class Config:
    PDF_PATH      = "vs/data/ti-va-un-antipasto.pdf"  # <-- cambia con il tuo PDF
    VS_DATA_PATH  = "./vs/data"          # Chroma salva qui su disco
    OLLAMA_MODEL  = "gemma3:4b"            # modello per estrarre le ricette
    OLLAMA_EMBED  = "embeddinggemma:300m"  # il tuo modello di embedding

    DB_HOST       = "localhost"          # IP macchina con XAMPP
    DB_PORT       = 3306
    DB_USER       = "root"
    DB_PASSWORD   = ""
    DB_NAME       = "aicookDB"---------------------->>>>>cambia e adatta

    CHUNK_SIZE    = 1000
    CHUNK_OVERLAP = 500
    LOG_FILE      = "pipeline.log"


# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(Config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  STEP 1+2+3 — PDF → CHUNK → CHROMA (su disco)
# ─────────────────────────────────────────────

def carica_pdf_e_crea_vectorstore():
    """
    Carica il PDF, lo divide in chunk e li salva in Chroma su disco.
    Restituisce il vectorstore e la lista dei chunk.
    """
    log.info(f"📄 Caricamento PDF: {Config.PDF_PATH}")
    loader = PyPDFLoader(Config.PDF_PATH)
    docs = loader.load()
    log.info(f"✅ Docs loaded: {len(docs)}")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=Config.CHUNK_SIZE,
        chunk_overlap=Config.CHUNK_OVERLAP,
        length_function=len,
        is_separator_regex=False
    )
    chunks = splitter.split_documents(docs)
    log.info(f"✅ Chunks charged: {len(chunks)}")

    embeddings = OllamaEmbeddings(model=Config.OLLAMA_EMBED)

    # Chroma persiste su disco — NON InMemoryVectorStore
    Path(Config.VS_DATA_PATH).mkdir(parents=True, exist_ok=True)
    vs = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=Config.VS_DATA_PATH
    )
    vs.persist()
    log.info(f"✅ VectorStore salvato in: {Config.VS_DATA_PATH}")

    return vs, chunks


# ─────────────────────────────────────────────
#  STEP 4 — ESTRAZIONE RICETTE CON OLLAMA
# ─────────────────────────────────────────────

PROMPT_ESTRAZIONE = """
Sei un assistente specializzato nell'analisi di ricettari.
Analizza il testo seguente ed estrai TUTTE le ricette presenti.
Rispondi SOLO con un array JSON valido, senza testo aggiuntivo e senza backtick.

Struttura richiesta per ogni ricetta:
[
  {{
    "nome": "Nome della ricetta",
    "categoria": "Antipasto|Primo|Secondo|Contorno|Dolce|Bevanda",
    "procedimento": "Testo completo del procedimento",
    "ingredienti": [
      {{"nome": "farina", "quantita": 200, "unita_misura": "g", "note": ""}},
      {{"nome": "uova",   "quantita": 2,   "unita_misura": "",  "note": "a temperatura ambiente"}}
    ],
    "tempo_prep": 15,
    "tempo_cottura": 30,
    "difficolta": "facile|media|difficile",
    "porzioni": 4
  }}
]

Regole:
- Se un campo non e' presente usa null
- tempo_prep e tempo_cottura sono interi in MINUTI
- quantita e' un numero decimale

Testo:
\"\"\"
{testo}
\"\"\"
"""


def estrai_ricette(chunks: list) -> list:
    """Usa Ollama per estrarre le ricette strutturate dai chunk."""
    log.info(f"🤖 Estrazione ricette con Ollama ({Config.OLLAMA_MODEL})...")

    testo_completo = "\n\n".join(c.page_content for c in chunks)
    blocchi = [testo_completo[i:i+4000] for i in range(0, len(testo_completo), 3800)]
    log.info(f"  Testo suddiviso in {len(blocchi)} blocchi")

    tutte = []
    for idx, blocco in enumerate(blocchi):
        log.info(f"  Blocco {idx+1}/{len(blocchi)}...")
        try:
            risposta = ollama.chat(
                model=Config.OLLAMA_MODEL,
                messages=[{"role": "user", "content": PROMPT_ESTRAZIONE.format(testo=blocco)}]
            )
            raw = risposta["message"]["content"].strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            ricette = json.loads(raw)
            if isinstance(ricette, list):
                tutte.extend(ricette)
                log.info(f"  ✅ {len(ricette)} ricette trovate")
        except json.JSONDecodeError as e:
            log.warning(f"  ⚠️  JSON non valido nel blocco {idx+1}: {e}")
        except Exception as e:
            log.error(f"  ❌ Errore Ollama blocco {idx+1}: {e}")

    log.info(f"✅ Totale ricette estratte: {len(tutte)}")
    return tutte


# ─────────────────────────────────────────────
#  STEP 5 — POPOLAMENTO MYSQL
# ─────────────────────────────────────────────

def connetti_db():
    conn = mysql.connector.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        charset="utf8mb4"
    )
    log.info(f"🔌 Connesso a MySQL: {Config.DB_HOST}/{Config.DB_NAME}")
    return conn


def get_o_crea_categoria(cursor, nome: str) -> int:
    nome = (nome or "Altro").strip().capitalize()
    cursor.execute("SELECT id_categoria FROM categorie WHERE nome = %s", (nome,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("INSERT INTO categorie (nome) VALUES (%s)", (nome,))
    return cursor.lastrowid


def get_o_crea_ingrediente(cursor, nome: str, unita: str) -> int:
    nome = nome.strip().lower()
    cursor.execute("SELECT id_ingrediente FROM ingredienti WHERE nome = %s", (nome,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute(
        "INSERT INTO ingredienti (nome, unita_misura) VALUES (%s, %s)",
        (nome, unita.strip() if unita else None)
    )
    return cursor.lastrowid


def inserisci_ricetta(cursor, ricetta: dict, embedding_id: str) -> int:
    id_cat = get_o_crea_categoria(cursor, ricetta.get("categoria", "Altro"))

    diff = ricetta.get("difficolta", "media")
    if diff not in ("facile", "media", "difficile"):
        diff = "media"

    cursor.execute("""
        INSERT INTO ricette (
            nome, id_categoria, procedimento,
            tempo_prep, tempo_cottura, difficolta, porzioni,
            chunk_vs_path, embedding_id, sorgente_pdf
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        ricetta.get("nome", "Senza nome"),
        id_cat,
        ricetta.get("procedimento", ""),
        ricetta.get("tempo_prep"),
        ricetta.get("tempo_cottura"),
        diff,
        ricetta.get("porzioni", 4),
        os.path.abspath(Config.VS_DATA_PATH),
        embedding_id,
        os.path.basename(Config.PDF_PATH)
    ))
    id_ricetta = cursor.lastrowid

    for ordine, ing in enumerate(ricetta.get("ingredienti", [])):
        nome_ing = (ing.get("nome") or "").strip()
        if not nome_ing:
            continue
        id_ing = get_o_crea_ingrediente(cursor, nome_ing, ing.get("unita_misura", ""))
        quantita = ing.get("quantita")
        try:
            quantita = float(quantita) if quantita is not None else None
        except (ValueError, TypeError):
            quantita = None
        cursor.execute("""
            INSERT IGNORE INTO ricetta_ingredienti
                (id_ricetta, id_ingrediente, quantita, note, ordine)
            VALUES (%s,%s,%s,%s,%s)
        """, (id_ricetta, id_ing, quantita, ing.get("note") or None, ordine))

    return id_ricetta


def popola_database(ricette: list, mappa_id: dict):
    log.info(f"💾 Popolamento MySQL ({len(ricette)} ricette)...")
    conn = connetti_db()
    cursor = conn.cursor()
    inserite = saltate = 0

    for r in ricette:
        nome = r.get("nome", "")
        if not nome:
            saltate += 1
            continue
        try:
            eid = mappa_id.get(nome, str(uuid.uuid4()))
            inserisci_ricetta(cursor, r, eid)
            conn.commit()
            log.info(f"  ✅ '{nome}'")
            inserite += 1
        except Error as e:
            conn.rollback()
            log.error(f"  ❌ '{nome}': {e}")
            saltate += 1

    cursor.close()
    conn.close()
    log.info(f"✅ Inserite: {inserite} | Saltate: {saltate}")


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    log.info("=" * 55)
    log.info("  PIPELINE: PDF → Chroma VectorStore → MySQL")
    log.info("=" * 55)

    if not os.path.exists(Config.PDF_PATH):
        log.error(f"❌ PDF non trovato: {Config.PDF_PATH}")
        return

    # STEP 1+2+3: PDF → chunk → Chroma su disco
    vs, chunks = carica_pdf_e_crea_vectorstore()

    # STEP 4: Estrai ricette strutturate con Ollama
    ricette = estrai_ricette(chunks)
    if not ricette:
        log.error("❌ Nessuna ricetta trovata. Controlla il PDF o il modello Ollama.")
        return

    # Mappa nome → embedding_id
    mappa_id = {r.get("nome", ""): str(uuid.uuid4()) for r in ricette}

    # STEP 5: Popola MySQL
    popola_database(ricette, mappa_id)

    log.info("=" * 55)
    log.info("  ✅ PIPELINE COMPLETATA")
    log.info(f"  📁 VectorStore: {Config.VS_DATA_PATH}")
    log.info(f"  🗃️  Database:    {Config.DB_NAME}@{Config.DB_HOST}")
    log.info("=" * 55)


if __name__ == "__main__":
    main()