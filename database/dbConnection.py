"""
dbConnection.py  –  Ai-Cook  |  Pipeline PDF → VectorStore → MySQL
=====================================================================
Uso:
    python dbConnection.py                    # processa Config.PDF_FOLDER (tutti i PDF)
    python dbConnection.py miofile.pdf        # processa un singolo PDF
"""

import os
import re
import sys
import json
import uuid
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# PDF
from pypdf import PdfReader

# Langchain (versioni aggiornate)
from langchain_text_splitters import RecursiveCharacterTextSplitter
try:
    from langchain_chroma import Chroma
    from langchain_ollama import OllamaEmbeddings
except ImportError:
    # fallback per installazioni più vecchie
    from langchain_community.vectorstores import Chroma
    from langchain_community.embeddings import OllamaEmbeddings

# Database MySQL
import mysql.connector
from mysql.connector import Error

# Ollama (client Python nativo)
import ollama


# ─────────────────────────────────────────────────────────────────
#  CONFIGURAZIONE  —  modifica questi valori prima di avviare
# ─────────────────────────────────────────────────────────────────

class Config:
    # Cartella contenente i PDF delle ricette
    # (tutti i .pdf presenti verranno processati)
    PDF_FOLDER = "."                         # "." = stessa cartella dello script

    # Cartella dove salvare i chunk del VectorStore Chroma
    VS_DATA_PATH = "vs/data"

    # Modello Ollama per l'estrazione strutturata delle ricette
    OLLAMA_MODEL = "gemma3:4b"

    # Modello Ollama per gli embedding (richiede: ollama pull nomic-embed-text)
    OLLAMA_EMBED_MODEL = "nomic-embed-text"

    # Connessione MySQL (XAMPP – macchina database)
    DB_HOST     = "localhost"   # ← cambia con l'IP della macchina DB se remota
    DB_PORT     = 3306
    DB_USER     = "root"
    DB_PASSWORD = ""            # lascia vuoto se non hai password in XAMPP
    DB_NAME     = "ricettario_db"

    # Chunking per il VectorStore
    CHUNK_SIZE    = 800    # caratteri per chunk
    CHUNK_OVERLAP = 100    # sovrapposizione tra chunk

    # Log
    LOG_FILE = "pipeline.log"


# ─────────────────────────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(Config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  STRUTTURA DATI RICETTA
# ─────────────────────────────────────────────────────────────────

@dataclass
class Ricetta:
    nome: str
    categoria: str
    procedimento: str
    ingredienti: list          # [{nome, quantita, unita_misura, note}]
    tempo_prep: Optional[int] = None
    tempo_cottura: Optional[int] = None
    difficolta: str = "media"
    porzioni: int = 4
    chunk_vs_path: str = ""
    embedding_id: str = ""
    sorgente_pdf: str = ""


# ─────────────────────────────────────────────────────────────────
#  STEP 1 — LETTURA PDF
# ─────────────────────────────────────────────────────────────────

def leggi_pdf(pdf_path: str) -> str:
    """Estrae il testo grezzo dall'intero PDF."""
    log.info(f"Lettura PDF: {pdf_path}")
    reader = PdfReader(pdf_path)
    pagine = []

    for i, pagina in enumerate(reader.pages):
        testo = pagina.extract_text()
        if testo and testo.strip():
            pagine.append(testo)
            log.debug(f"  Pagina {i+1}: {len(testo)} caratteri")
        else:
            log.warning(f"  Pagina {i+1}: nessun testo (PDF scansionato?)")

    testo_completo = "\n\n".join(pagine)
    log.info(f"PDF letto: {len(reader.pages)} pagine, {len(testo_completo)} caratteri totali")
    return testo_completo


# ─────────────────────────────────────────────────────────────────
#  STEP 2 — ESTRAZIONE RICETTE tramite Ollama
# ─────────────────────────────────────────────────────────────────

PROMPT_ESTRAZIONE = """
Sei un assistente specializzato nell'analisi di ricettari italiani.

Ti verrà fornito un blocco di testo estratto da un PDF di un ricettario.
Il tuo compito è estrarre TUTTE le ricette presenti nel testo e restituirle
in formato JSON, seguendo ESATTAMENTE questa struttura:

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

REGOLE OBBLIGATORIE:
- Restituisci SOLO il JSON valido, senza testo aggiuntivo, senza markdown, senza backtick
- Se un campo non è presente nel testo, usa null
- tempo_prep e tempo_cottura sono INTERI in minuti (es: 30)
- quantita è un numero decimale (es: 0.5, 200, 2)
- unita_misura: g, kg, ml, l, cucchiai, cucchiaini, q.b., pz, oppure stringa vuota
- difficolta deve essere esattamente: "facile", "media" o "difficile"
- Se il testo non contiene ricette complete, restituisci: []

Testo da analizzare:
\"\"\"
{testo}
\"\"\"
"""


def estrai_ricette_con_ollama(testo: str) -> list:
    """Usa Ollama per estrarre le ricette strutturate dal testo grezzo."""
    log.info(f"Estrazione ricette con Ollama ({Config.OLLAMA_MODEL})...")

    # Suddivide il testo in blocchi per non superare il context window
    blocchi = [testo[i:i+4000] for i in range(0, len(testo), 3800)]
    log.info(f"Testo suddiviso in {len(blocchi)} blocchi")

    tutte_le_ricette = []

    for idx, blocco in enumerate(blocchi):
        if not blocco.strip():
            continue

        log.info(f"Elaborazione blocco {idx+1}/{len(blocchi)}...")
        prompt = PROMPT_ESTRAZIONE.format(testo=blocco)

        try:
            risposta = ollama.chat(
                model=Config.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}]
            )
            testo_risposta = risposta.message.content.strip()

            # Rimuove backtick markdown residui
            testo_risposta = re.sub(r"```json\s*|```\s*", "", testo_risposta).strip()

            # A volte il modello aggiunge testo prima del JSON: cerca il primo [
            idx_start = testo_risposta.find("[")
            idx_end   = testo_risposta.rfind("]")
            if idx_start != -1 and idx_end != -1:
                testo_risposta = testo_risposta[idx_start:idx_end+1]

            ricette_blocco = json.loads(testo_risposta)

            if isinstance(ricette_blocco, list):
                # Filtra ricette con nome non vuoto
                valide = [r for r in ricette_blocco if r.get("nome", "").strip()]
                tutte_le_ricette.extend(valide)
                log.info(f"Blocco {idx+1}: {len(valide)} ricette trovate")
            else:
                log.warning(f"Blocco {idx+1}: risposta non è una lista, salto")

        except json.JSONDecodeError as e:
            log.error(f"Blocco {idx+1}: JSON non valido — {e}")
        except Exception as e:
            log.error(f"Blocco {idx+1}: errore Ollama — {e}")

    log.info(f"Totale ricette estratte: {len(tutte_le_ricette)}")
    return tutte_le_ricette


# ─────────────────────────────────────────────────────────────────
#  STEP 3 — VECTORSTORE Chroma
# ─────────────────────────────────────────────────────────────────

def crea_vectorstore(ricette_raw: list, pdf_path: str) -> tuple:
    """
    Crea i chunk per ogni ricetta, li salva nel VectorStore Chroma (vs/data)
    e restituisce il db Chroma e un dizionario {nome_ricetta: primo_embedding_id}.
    """
    log.info(f"Creazione VectorStore in: {Config.VS_DATA_PATH}")
    Path(Config.VS_DATA_PATH).mkdir(parents=True, exist_ok=True)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=Config.CHUNK_SIZE,
        chunk_overlap=Config.CHUNK_OVERLAP,
        separators=["\n\n", "\n", " ", ""]
    )

    embeddings = OllamaEmbeddings(model=Config.OLLAMA_EMBED_MODEL)

    testi_chunk   = []
    metadati_chunk = []
    id_chunk       = []
    mappa_ricetta_id = {}   # nome_ricetta → primo embedding_id

    for ricetta in ricette_raw:
        nome = ricetta.get("nome", "Senza nome")

        ingredienti_str = ", ".join(
            f"{ing.get('quantita', '')} {ing.get('unita_misura', '')} {ing.get('nome', '')}".strip()
            for ing in ricetta.get("ingredienti", [])
            if ing.get("nome", "").strip()
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
                "ricetta":       nome,
                "categoria":     ricetta.get("categoria", ""),
                "sorgente_pdf":  os.path.basename(pdf_path),
                "chunk_index":   i,
                "chunk_totali":  len(chunks)
            })

        if primo_id:
            mappa_ricetta_id[nome] = primo_id
        log.debug(f"  {nome}: {len(chunks)} chunk creati")

    if not testi_chunk:
        log.warning("Nessun chunk da inserire nel VectorStore.")
        return None, mappa_ricetta_id

    # Salva nel VectorStore (chromadb >= 0.4 persiste automaticamente)
    vs = Chroma.from_texts(
        texts=testi_chunk,
        embedding=embeddings,
        metadatas=metadati_chunk,
        ids=id_chunk,
        persist_directory=Config.VS_DATA_PATH
    )

    log.info(f"VectorStore salvato: {len(testi_chunk)} chunk in {Config.VS_DATA_PATH}")
    return vs, mappa_ricetta_id


# ─────────────────────────────────────────────────────────────────
#  STEP 4 — DATABASE MySQL
# ─────────────────────────────────────────────────────────────────

def connetti_db():
    """Apre la connessione a MySQL su XAMPP."""
    conn = mysql.connector.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        charset="utf8mb4",
        collation="utf8mb4_unicode_ci"
    )
    log.info(f"Connessione MySQL: {Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}")
    return conn


def get_o_crea_categoria(cursor, nome_categoria: str) -> int:
    """Recupera o inserisce una categoria e restituisce il suo id."""
    nome_pulito = (nome_categoria or "Altro").strip().capitalize()
    cursor.execute("SELECT id_categoria FROM categorie WHERE nome = %s", (nome_pulito,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("INSERT INTO categorie (nome) VALUES (%s)", (nome_pulito,))
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

    embedding_id  = mappa_id.get(nome, "") or ""
    chunk_path    = os.path.abspath(Config.VS_DATA_PATH) if embedding_id else None

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
        ricetta.get("porzioni") or 4,
        chunk_path,
        embedding_id or None,
        os.path.basename(pdf_path)
    ))

    id_ricetta = cursor.lastrowid

    for ordine, ing in enumerate(ricetta.get("ingredienti", [])):
        nome_ing = (ing.get("nome") or "").strip()
        if not nome_ing:
            continue

        id_ing = get_o_crea_ingrediente(
            cursor,
            nome_ing,
            ing.get("unita_misura") or ""
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
            ing.get("note") or None,
            ordine
        ))

    return id_ricetta


def popola_database(ricette_raw: list, mappa_id: dict, pdf_path: str):
    """Inserisce tutte le ricette estratte nel database MySQL."""
    log.info(f"Popolamento database MySQL ({len(ricette_raw)} ricette)...")

    conn = None
    try:
        conn    = connetti_db()
        cursor  = conn.cursor()
        inserite = 0
        saltate  = 0

        for ricetta in ricette_raw:
            nome = ricetta.get("nome", "")
            if not nome:
                saltate += 1
                continue
            try:
                id_ricetta = inserisci_ricetta(cursor, ricetta, mappa_id, pdf_path)
                conn.commit()
                log.info(f"  Inserita: '{nome}' (id={id_ricetta})")
                inserite += 1
            except Error as e:
                conn.rollback()
                log.error(f"  Errore inserimento '{nome}': {e}")
                saltate += 1

        log.info(f"Database popolato: {inserite} inserite, {saltate} saltate")

    except Error as e:
        log.error(f"Errore connessione MySQL: {e}")
        raise
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            log.info("Connessione MySQL chiusa")


# ─────────────────────────────────────────────────────────────────
#  PIPELINE COMPLETA PER UN SINGOLO PDF
# ─────────────────────────────────────────────────────────────────

def processa_pdf(pdf_path: str):
    """Esegue l'intera pipeline (leggi → estrai → vectorstore → db) su un PDF."""
    log.info("=" * 60)
    log.info(f"  INIZIO PIPELINE: {os.path.basename(pdf_path)}")
    log.info("=" * 60)

    if not os.path.exists(pdf_path):
        log.error(f"File PDF non trovato: {pdf_path}")
        return

    # STEP 1: Leggi il PDF
    testo = leggi_pdf(pdf_path)
    if not testo.strip():
        log.error("Nessun testo estratto dal PDF. È forse un PDF scansionato?")
        return

    # STEP 2: Estrai le ricette con Ollama
    ricette_raw = estrai_ricette_con_ollama(testo)
    if not ricette_raw:
        log.error("Nessuna ricetta estratta. Controlla il PDF o il modello Ollama.")
        return

    # STEP 3: Crea il VectorStore
    _, mappa_id = crea_vectorstore(ricette_raw, pdf_path)

    # STEP 4: Popola il database
    popola_database(ricette_raw, mappa_id, pdf_path)

    log.info(f"  PIPELINE COMPLETATA: {os.path.basename(pdf_path)}")
    log.info("=" * 60)


def processa_tutti_i_pdf(cartella: str = "."):
    """Processa tutti i file .pdf presenti nella cartella specificata."""
    pdf_files = sorted(Path(cartella).glob("*.pdf"))

    if not pdf_files:
        log.error(f"Nessun file PDF trovato in: {os.path.abspath(cartella)}")
        return

    log.info(f"Trovati {len(pdf_files)} PDF in '{cartella}':")
    for f in pdf_files:
        log.info(f"  - {f.name}")

    for pdf in pdf_files:
        processa_pdf(str(pdf))

    log.info("Tutti i PDF processati.")


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Argomento passato: processa solo quel PDF
        processa_pdf(sys.argv[1])
    else:
        # Nessun argomento: processa tutti i PDF nella cartella configurata
        processa_tutti_i_pdf(Config.PDF_FOLDER)
