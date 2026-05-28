# =============================================================
#  ollama_client.py  –  Ai-Cook  |  Client HTTP Ollama
# =============================================================

import json
import requests
from requests.exceptions import RequestException
from config import OLLAMA_BASE_URL, OLLAMA_MODEL, SYSTEM_PROMPT


def test_ollama() -> bool:
    """Controlla che Ollama sia avviato e risponda."""
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if r.status_code != 200:
            return False
        modelli = [m["name"] for m in r.json().get("models", [])]
        if not any(OLLAMA_MODEL in m for m in modelli):
            print(f"[Ollama] Attenzione: '{OLLAMA_MODEL}' non trovato. "
                  f"Disponibili: {modelli}")
        return True
    except RequestException as e:
        print(f"[Ollama] Non raggiungibile: {e}")
        return False


def genera_risposta(domanda: str, contesto_rag: str = "") -> str:
    """
    Invia la domanda a Ollama con il contesto RAG e restituisce
    la risposta testuale.

    Args:
        domanda:       testo scritto dall'utente nella chat.
        contesto_rag:  blocco di ricette recuperate dal DB.

    Returns:
        Risposta testuale generata dal modello.
    """
    if contesto_rag:
        prompt_utente = (
            f"{contesto_rag}\n\n"
            f"Domanda dell'utente: {domanda}"
        )
    else:
        prompt_utente = domanda

    payload = {
        "model":  OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt_utente},
        ],
        "options": {
            "temperature": 0.7,
            "num_predict": 1024,
        }
    }

    try:
        r = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=120
        )
        r.raise_for_status()
        return r.json()["message"]["content"].strip()

    except requests.HTTPError as e:
        print(f"[Ollama] HTTP error: {e}")
        return "Mi dispiace, si è verificato un errore nella generazione della risposta."
    except RequestException as e:
        print(f"[Ollama] Errore di rete: {e}")
        return "Ollama non è raggiungibile. Assicurarsi che sia avviato sulla macchina server."
    except (KeyError, json.JSONDecodeError) as e:
        print(f"[Ollama] Risposta malformata: {e}")
        return "Risposta non valida ricevuta da Ollama."
