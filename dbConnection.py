"""DA CAMBIARE E ADATTARE AL MIO PROGETTO AI COOK"""
import os
import re
import json
import uuid
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# PDF
from pypdf import PdfReader

# VectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings

# Database
import mysql.connector
from mysql.connector import Error

# Ollama (per l'estrazione strutturata)
import ollama


# ─────────────────────────────────────────────
#  CONFIGURAZIONE  — modifica questi valori
# ─────────────────────────────────────────────

class Config:
    # Percorso del PDF da elaborare
    PDF_PATH = "79824327-La-Risotteria.pdf"

    # Cartella dove salvare i chunk del VectorStore
    VS_DATA_PATH = "vs/data"

    # Modello Ollama da usare
    OLLAMA_MODEL = "gemma3:4b"          # oppure "llama3", "gemma3", ecc.
    OLLAMA_EMBED_MODEL = "nomic-embed-text"  # modello per gli embedding

    # Connessione MySQL (XAMPP)
    DB_HOST = "localhost"             # IP della macchina 3 (database)
    DB_PORT = 3306
    DB_USER = "root"
    DB_PASSWORD = ""                  # lascia vuoto se non hai password in XAMPP
    DB_NAME = "ricettario_db"

    # Chunking
    CHUNK_SIZE = 800         # caratteri per chunk
    CHUNK_OVERLAP = 100      # sovrapposizione tra chunk

    # Log
    LOG_FILE = "pipeline.log"


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
#  STRUTTURA DATI RICETTA
# ─────────────────────────────────────────────

@dataclass
class Ricetta:
    nome: str
    categoria: str
    procedimento: str
    ingredienti: list[dict]          # [{nome, quantita, unita_misura, note}]
    tempo_prep: Optional[int] = None
    tempo_cottura: Optional[int] = None
    difficolta: str = "media"
    porzioni: int = 4
    chunk_vs_path: str = ""
    embedding_id: str = ""
    sorgente_pdf: str = ""


# ─────────────────────────────────────────────
#  STEP 1 — LETTURA PDF
# ─────────────────────────────────────────────

def leggi_pdf(pdf_path: str) -> str:
    """Estrae il testo grezzo dall'intero PDF."""
    log.info(f"📄 Lettura PDF: {pdf_path}")
    reader = PdfReader(pdf_path)
    testo_totale = []

    for i, pagina in enumerate(reader.pages):
        testo = pagina.extract_text()
        if testo:
            testo_totale.append(testo)
            log.debug(f"  Pagina {i+1}: {len(testo)} caratteri estratti")
        else:
            log.warning(f"  Pagina {i+1}: nessun testo estratto (PDF scansionato?)")

    testo_completo = "\n\n".join(testo_totale)
    log.info(f"✅ PDF letto: {len(reader.pages)} pagine, {len(testo_completo)} caratteri totali")
    return testo_completo


# ─────────────────────────────────────────────
#  STEP 2 — SUDDIVISIONE IN RICETTE tramite Ollama
# ─────────────────────────────────────────────

PROMPT_ESTRAZIONE = """
Sei un assistente specializzato nell'analisi di ricettari.

Ti verrà fornito un blocco di testo estratto da un PDF di un ricettario.
Il tuo compito è estrarre TUTTE le ricette presenti nel testo e restituirle
in formato JSON, seguendo esattamente questa struttura:

[
  {{
    "nome": "Nome della ricetta",
    "categoria": "Primo|Secondo|Antipasto|Contorno|Dolce|Bevanda",
    "procedimento": "Testo completo del procedimento...",
    "ingredienti": [
      {{"nome": "farina", "quantita": 200, "unita_misura": "g", "note": ""}},
      {{"nome": "uova", "quantita": 2, "unita_misura": "", "note": "a temperatura ambiente"}}
    ],
    "tempo_prep": 15,
    "tempo_cottura": 30,
    "difficolta": "facile|media|difficile",
    "porzioni": 4
  }}
]

REGOLE IMPORTANTI:
- Restituisci SOLO il JSON, senza testo aggiuntivo, senza markdown
- Se un campo non è presente nel testo, usa null
- tempo_prep e tempo_cottura sono in MINUTI (interi)
- quantita è un numero decimale (es: 0.5 per mezzo cucchiaio)
- unita_misura può essere: g, kg, ml, l, cucchiai, cucchiaini, q.b., pz, ""

Testo da analizzare:
\"\"\"
{testo}
\"\"\"
"""


def estrai_ricette_con_ollama(testo: str) -> list[dict]:
    """Usa Ollama per estrarre le ricette strutturate dal testo grezzo."""
    log.info(f"🤖 Estrazione ricette con Ollama ({Config.OLLAMA_MODEL})...")

    # Suddivide il testo in blocchi da ~4000 caratteri per non superare il context
    blocchi = [testo[i:i+4000] for i in range(0, len(testo), 3800)]
    log.info(f"  Testo suddiviso in {len(blocchi)} blocchi")

    tutte_le_ricette = []

    for idx, blocco in enumerate(blocchi):
        log.info(f"  Elaborazione blocco {idx+1}/{len(blocchi)}...")
        prompt = PROMPT_ESTRAZIONE.format(testo=blocco)

        try:
            risposta = ollama.chat(
                model=Config.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}]
            )
            testo_risposta = risposta.message.content.strip()

            # Rimuove eventuali backtick markdown
            testo_risposta = re.sub(r"```json|```", "", testo_risposta).strip()

            ricette_blocco = json.loads(testo_risposta)

            if isinstance(ricette_blocco, list):
                tutte_le_ricette.extend(ricette_blocco)
                log.info(f"  ✅ Blocco {idx+1}: {len(ricette_blocco)} ricette trovate")
            else:
                log.warning(f"  ⚠️  Blocco {idx+1}: risposta non è una lista, salto")

        except json.JSONDecodeError as e:
            log.error(f"  ❌ Blocco {idx+1}: JSON non valido — {e}")
            log.debug(f"  Risposta raw: {testo_risposta[:300]}")
        except Exception as e:
            log.error(f"  ❌ Blocco {idx+1}: errore Ollama — {e}")

    log.info(f"✅ Totale ricette estratte: {len(tutte_le_ricette)}")
    return tutte_le_ricette


# ─────────────────────────────────────────────
#  STEP 3 — CHUNKING E VECTORSTORE
# ─────────────────────────────────────────────

def crea_vectorstore(ricette_raw: list[dict], pdf_path: str) -> tuple[Chroma, dict]:
    """
    Crea i chunk per ogni ricetta, li salva nel VectorStore Chroma (vs/data)
    e restituisce il db e un dizionario {nome_ricetta: embedding_id}.
    """
    log.info(f"🗂️  Creazione VectorStore in: {Config.VS_DATA_PATH}")
    Path(Config.VS_DATA_PATH).mkdir(parents=True, exist_ok=True)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=Config.CHUNK_SIZE,
        chunk_overlap=Config.CHUNK_OVERLAP,
        separators=["\n\n", "\n", " ", ""]
    )

    embeddings = OllamaEmbeddings(model=Config.OLLAMA_EMBED_MODEL)

    testi_chunk = []
    metadati_chunk = []
    id_chunk = []
    mappa_ricetta_id = {}  # nome_ricetta -> primo embedding_id

    for ricetta in ricette_raw:
        nome = ricetta.get("nome", "Senza nome")

        # Testo da inserire nel vectorstore (nome + ingredienti + procedimento)
        ingredienti_str = ", ".join(
            f"{i.get('quantita', '')} {i.get('unita_misura', '')} {i.get('nome', '')}".strip()
            for i in ricetta.get("ingredienti", [])
        )
        testo_completo = (
            f"Ricetta: {nome}\n"
            f"Categoria: {ricetta.get('categoria', '')}\n"
            f"Ingredienti: {ingredienti_str}\n"
            f"Procedimento: {ricetta.get('procedimento', '')}"
        )

        chunks = splitter.split_text(testo_completo)
        primo_id = None

        for i, chunk in enumerate(chunks):
            chunk_id = str(uuid.uuid4())
            if i == 0:
                primo_id = chunk_id

            testi_chunk.append(chunk)
            id_chunk.append(chunk_id)
            metadati_chunk.append({
                "ricetta": nome,
                "categoria": ricetta.get("categoria", ""),
                "sorgente_pdf": os.path.basename(pdf_path),
                "chunk_index": i,
                "chunk_totali": len(chunks)
            })

        mappa_ricetta_id[nome] = primo_id
        log.debug(f"  {nome}: {len(chunks)} chunk creati")

    # Salva nel VectorStore
    vs = Chroma.from_texts(
        texts=testi_chunk,
        embedding=embeddings,
        metadatas=metadati_chunk,
        ids=id_chunk,
        persist_directory=Config.VS_DATA_PATH
    )
    

    log.info(f"✅ VectorStore salvato: {len(testi_chunk)} chunk totali in {Config.VS_DATA_PATH}")
    return vs, mappa_ricetta_id


# ─────────────────────────────────────────────
#  STEP 4 — DATABASE MYSQL
# ─────────────────────────────────────────────

def connetti_db() -> mysql.connector.MySQLConnection:
    """Apre la connessione a MySQL su XAMPP."""
    conn = mysql.connector.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        charset="utf8mb4"
    )
    log.info(f"🔌 Connessione MySQL: {Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}")
    return conn


def get_o_crea_categoria(cursor, nome_categoria: str) -> int:
    """Recupera o inserisce una categoria e restituisce il suo id."""
    nome_pulito = nome_categoria.strip().capitalize() if nome_categoria else "Altro"

    cursor.execute("SELECT id_categoria FROM categorie WHERE nome = %s", (nome_pulito,))
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute(
        "INSERT INTO categorie (nome) VALUES (%s)",
        (nome_pulito,)
    )
    return cursor.lastrowid


def get_o_crea_ingrediente(cursor, nome: str, unita: str) -> int:
    """Recupera o inserisce un ingrediente e restituisce il suo id."""
    nome_pulito = nome.strip().lower()
    cursor.execute("SELECT id_ingrediente FROM ingredienti WHERE nome = %s", (nome_pulito,))
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute(
        "INSERT INTO ingredienti (nome, unita_misura) VALUES (%s, %s)",
        (nome_pulito, unita.strip() if unita else None)
    )
    return cursor.lastrowid


def inserisci_ricetta(cursor, ricetta: dict, mappa_id: dict, pdf_path: str) -> int:
    """Inserisce una ricetta completa nel database e restituisce il suo id."""
    nome = ricetta.get("nome", "Senza nome")
    id_categoria = get_o_crea_categoria(cursor, ricetta.get("categoria", "Altro"))

    difficolta = ricetta.get("difficolta", "media")
    if difficolta not in ("facile", "media", "difficile"):
        difficolta = "media"

    embedding_id = mappa_id.get(nome, "")
    chunk_path = os.path.abspath(Config.VS_DATA_PATH) if embedding_id else None

    cursor.execute("""
        INSERT INTO ricette (
            nome, id_categoria, procedimento,
            tempo_prep, tempo_cottura, difficolta, porzioni,
            chunk_vs_path, embedding_id, sorgente_pdf
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        nome,
        id_categoria,
        ricetta.get("procedimento", ""),
        ricetta.get("tempo_prep"),
        ricetta.get("tempo_cottura"),
        difficolta,
        ricetta.get("porzioni", 4),
        chunk_path,
        embedding_id,
        os.path.basename(pdf_path)
    ))

    id_ricetta = cursor.lastrowid

    # Inserisce gli ingredienti nella tabella pivot
    for ordine, ing in enumerate(ricetta.get("ingredienti", [])):
        nome_ing = ing.get("nome", "").strip()
        if not nome_ing:
            continue

        id_ing = get_o_crea_ingrediente(
            cursor,
            nome_ing,
            ing.get("unita_misura", "")
        )

        quantita = ing.get("quantita")
        if quantita is not None:
            try:
                quantita = float(quantita)
            except (ValueError, TypeError):
                quantita = None

        cursor.execute("""
            INSERT IGNORE INTO ricetta_ingredienti
                (id_ricetta, id_ingrediente, quantita, note, ordine)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            id_ricetta,
            id_ing,
            quantita,
            ing.get("note", "") or None,
            ordine
        ))

    return id_ricetta


def popola_database(ricette_raw: list[dict], mappa_id: dict, pdf_path: str):
    """Inserisce tutte le ricette nel database MySQL."""
    log.info(f"💾 Popolamento database MySQL ({len(ricette_raw)} ricette)...")

    try:
        conn = connetti_db()
        cursor = conn.cursor()
        inserite = 0
        saltate = 0

        for ricetta in ricette_raw:
            nome = ricetta.get("nome", "")
            if not nome:
                saltate += 1
                continue
            try:
                id_ricetta = inserisci_ricetta(cursor, ricetta, mappa_id, pdf_path)
                conn.commit()
                log.info(f"  ✅ Inserita: '{nome}' (id={id_ricetta})")
                inserite += 1
            except Error as e:
                conn.rollback()
                log.error(f"  ❌ Errore inserimento '{nome}': {e}")
                saltate += 1

        log.info(f"✅ Database popolato: {inserite} ricette inserite, {saltate} saltate")

    except Error as e:
        log.error(f"❌ Errore connessione MySQL: {e}")
        raise
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()
            log.info("🔌 Connessione MySQL chiusa")


# ─────────────────────────────────────────────
#  MAIN PIPELINE
# ─────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("  AVVIO PIPELINE: PDF → VectorStore → MySQL")
    log.info("=" * 60)

    pdf_path = Config.PDF_PATH

    # Verifica che il PDF esista
    if not os.path.exists(pdf_path):
        log.error(f"❌ File PDF non trovato: {pdf_path}")
        raise FileNotFoundError(f"PDF non trovato: {pdf_path}")

    # STEP 1: Leggi il PDF
    testo = leggi_pdf(pdf_path)

    # STEP 2: Estrai le ricette con Ollama
    ricette_raw = estrai_ricette_con_ollama(testo)

    if not ricette_raw:
        log.error("❌ Nessuna ricetta estratta. Controlla il PDF o il modello Ollama.")
        return

    # STEP 3: Crea il VectorStore
    _, mappa_id = crea_vectorstore(ricette_raw, pdf_path)

    # STEP 4: Popola il database
    popola_database(ricette_raw, mappa_id, pdf_path)

    log.info("=" * 60)
    log.info("  ✅ PIPELINE COMPLETATA CON SUCCESSO")
    log.info(f"  📁 Chunk salvati in: {Config.VS_DATA_PATH}")
    log.info(f"  🗃️  Database: {Config.DB_NAME} su {Config.DB_HOST}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
