# =============================================================
#  rag.py  –  Ai-Cook  |  Retrieval-Augmented Generation
#  Recupera le ricette pertinenti dal database MySQL usando
#  FULLTEXT search e JOIN con la tabella ingredienti.
# =============================================================

import re
import mysql.connector
from mysql.connector import Error
from config import (
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME,
    MAX_RICETTE_CONTESTO, MAX_CONTESTO_CHARS
)


# ── Connessione ───────────────────────────────────────────────

def get_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        collation="utf8mb4_unicode_ci"
    )


def test_connection() -> bool:
    """Ritorna True se MySQL è raggiungibile."""
    try:
        conn = get_connection()
        conn.close()
        return True
    except Error as e:
        print(f"[DB] Errore connessione: {e}")
        return False


# ── Ricerca ricette ───────────────────────────────────────────

def cerca_ricette(domanda: str) -> list:
    """
    Cerca le ricette più rilevanti per la domanda dell'utente.
    Strategia:
      1. FULLTEXT MATCH AGAINST sulla domanda completa (ricerca semantica MySQL)
      2. Se non trova risultati (DB troppo piccolo o parole stopword),
         fallback su LIKE keyword per keyword
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor(dictionary=True)

        # -- Tentativo 1: FULLTEXT --
        query_ft = """
            SELECT r.id_ricetta, r.nome, r.procedimento,
                   r.tempo_prep, r.tempo_cottura, r.difficolta, r.porzioni,
                   c.nome AS categoria,
                   MATCH(r.nome, r.procedimento) AGAINST (%s IN NATURAL LANGUAGE MODE) AS score
            FROM ricette r
            LEFT JOIN categorie c ON r.id_categoria = c.id_categoria
            WHERE MATCH(r.nome, r.procedimento) AGAINST (%s IN NATURAL LANGUAGE MODE)
            ORDER BY score DESC
            LIMIT %s
        """
        cursor.execute(query_ft, (domanda, domanda, MAX_RICETTE_CONTESTO))
        risultati = cursor.fetchall()

        # -- Fallback: LIKE su parole chiave --
        if not risultati:
            risultati = _cerca_con_like(cursor, domanda)

        # Per ogni ricetta trovata, recupera la lista ingredienti
        for r in risultati:
            r["ingredienti"] = _get_ingredienti(cursor, r["id_ricetta"])

        cursor.close()
        conn.close()
        return risultati

    except Error as e:
        print(f"[RAG] Errore query: {e}")
        return []


def _cerca_con_like(cursor, domanda: str) -> list:
    """Fallback: cerca con LIKE sulle keyword della domanda."""
    stopwords = {
        "come", "fare", "fai", "cosa", "quali", "qual", "dove", "quando",
        "posso", "puoi", "voglio", "vorrei", "dimmi", "dammi", "aiuta",
        "ricetta", "ricette", "piatto", "piatti", "cucina", "cucinare",
        "ingredienti", "procedimento", "preparare", "preparazione",
        "che", "una", "uno", "del", "della", "dei", "delle", "con",
    }
    parole = re.findall(r"[a-zA-Zàèéìòùü]{4,}", domanda.lower())
    keywords = [p for p in parole if p not in stopwords][:5]

    if not keywords:
        # Ultima risorsa: ultime N ricette inserite
        cursor.execute("""
            SELECT r.id_ricetta, r.nome, r.procedimento,
                   r.tempo_prep, r.tempo_cottura, r.difficolta, r.porzioni,
                   c.nome AS categoria, 0 AS score
            FROM ricette r
            LEFT JOIN categorie c ON r.id_categoria = c.id_categoria
            ORDER BY r.id_ricetta DESC
            LIMIT %s
        """, (MAX_RICETTE_CONTESTO,))
        return cursor.fetchall()

    # LIKE su ogni keyword, punteggio basato su quante keyword compaiono
    score_expr = " + ".join(
        f"(CASE WHEN LOWER(r.nome) LIKE %s THEN 3 ELSE 0 END "
        f"+ CASE WHEN LOWER(r.procedimento) LIKE %s THEN 1 ELSE 0 END)"
        for _ in keywords
    )
    where_parts = " OR ".join(
        "(LOWER(r.nome) LIKE %s OR LOWER(r.procedimento) LIKE %s)"
        for _ in keywords
    )

    params = []
    for kw in keywords:
        like = f"%{kw}%"
        params.extend([like, like])   # per score
    for kw in keywords:
        like = f"%{kw}%"
        params.extend([like, like])   # per where
    params.append(MAX_RICETTE_CONTESTO)

    cursor.execute(f"""
        SELECT r.id_ricetta, r.nome, r.procedimento,
               r.tempo_prep, r.tempo_cottura, r.difficolta, r.porzioni,
               c.nome AS categoria, ({score_expr}) AS score
        FROM ricette r
        LEFT JOIN categorie c ON r.id_categoria = c.id_categoria
        WHERE {where_parts}
        ORDER BY score DESC
        LIMIT %s
    """, params)

    return cursor.fetchall()


def _get_ingredienti(cursor, id_ricetta: int) -> list:
    """Recupera la lista ingredienti di una ricetta con quantità e unità."""
    cursor.execute("""
        SELECT i.nome, ri.quantita, i.unita_misura, ri.note
        FROM ricetta_ingredienti ri
        JOIN ingredienti i ON ri.id_ingrediente = i.id_ingrediente
        WHERE ri.id_ricetta = %s
        ORDER BY ri.ordine
    """, (id_ricetta,))
    return cursor.fetchall()


# ── Costruzione contesto RAG ──────────────────────────────────

def costruisci_contesto(ricette: list) -> str:
    """
    Formatta le ricette trovate in un blocco testo da inserire
    nel prompt Ollama come contesto RAG.
    """
    if not ricette:
        return ""

    righe = ["=== RICETTE DAL DATABASE ===\n"]
    totale_chars = len(righe[0])

    for r in ricette:
        # Riga tempi
        tempi = []
        if r.get("tempo_prep"):
            tempi.append(f"prep {r['tempo_prep']} min")
        if r.get("tempo_cottura"):
            tempi.append(f"cottura {r['tempo_cottura']} min")
        info_tempi = " | ".join(tempi) if tempi else "N/D"

        # Lista ingredienti
        ingredienti_lista = []
        for ing in r.get("ingredienti", []):
            q    = f"{ing['quantita']:.0f}" if ing.get("quantita") else ""
            u    = ing.get("unita_misura") or ""
            n    = ing.get("nome") or ""
            nota = f" ({ing['note']})" if ing.get("note") else ""
            ingredienti_lista.append(f"  - {q} {u} {n}{nota}".strip())

        blocco = (
            f"--- {r['nome']} ---\n"
            f"Categoria: {r.get('categoria') or 'N/D'} | "
            f"Difficoltà: {r.get('difficolta') or 'N/D'} | "
            f"Porzioni: {r.get('porzioni') or 'N/D'} | {info_tempi}\n"
            f"Ingredienti:\n" + "\n".join(ingredienti_lista) + "\n"
            f"Procedimento:\n{r.get('procedimento') or 'N/D'}\n\n"
        )

        if totale_chars + len(blocco) > MAX_CONTESTO_CHARS:
            # Inserisce una versione accorciata (solo nome + ingredienti)
            blocco_corto = (
                f"--- {r['nome']} (estratto) ---\n"
                f"Ingredienti:\n" + "\n".join(ingredienti_lista[:10]) + "\n\n"
            )
            if totale_chars + len(blocco_corto) <= MAX_CONTESTO_CHARS:
                righe.append(blocco_corto)
                totale_chars += len(blocco_corto)
            break

        righe.append(blocco)
        totale_chars += len(blocco)

    return "".join(righe)
