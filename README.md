# Ai-Cook — Chef AI Chatbot

Progetto scolastico ITIS – Quinta superiore  
Architettura su **3 macchine** collegate alla stessa rete locale.

---

## Struttura del progetto

```
AI-COOK/
│
├── README.md
│
├── frontend/                      ← Macchina 1
│   ├── index.html
│   ├── script.js
│   └── style.css
│
├── server/                        ← Macchina 2 (tua parte)
│   ├── server.py
│   ├── config.py
│   ├── rag.py
│   ├── ollama_client.py
│   └── requirements.txt
│
└── database/                      ← Macchina 3
    ├── dbbuild.sql
    ├── dbConnection.py
    ├── requirements.txt
    ├── pipeline.log               (generato automaticamente)
    ├── vs/
    │   └── data/                  (generato da dbConnection.py – VectorStore Chroma)
    ├── 79824327-La-Risotteria.pdf
    ├── Cannella_SMO870_IT_Recipe_Cards.pdf
    ├── libro-artusi.pdf
    └── ti-va-un-antipasto.pdf
```

---

## Macchina 3 — Database (setup da fare per prima)

### 1. Installa XAMPP e avvia solo MySQL

Scarica XAMPP da https://sourceforge.net/projects/xampp/  
Nel pannello di controllo XAMPP, avvia **solo MySQL** (non Apache).

### 2. Crea il database

Apri **phpMyAdmin** (`http://localhost/phpmyadmin`),  
vai su "Import" e carica `dbbuild.sql`.  
Oppure da terminale:
```bash
mysql -u root < database/dbbuild.sql
```

### 3. Crea l'ambiente virtuale Python

```bash
cd database
python -m venv venv
venv\Scripts\activate          # Windows
# oppure: source venv/bin/activate   (Linux/Mac)
pip install -r requirements.txt
```

### 4. Installa i modelli Ollama necessari

```bash
ollama pull gemma3:4b
ollama pull nomic-embed-text
```

### 5. Metti i PDF nella cartella database/

Scarica qualche ricettario PDF (es. da Giallo Zafferano) e copialo in `database/`.

### 6. Esegui la pipeline

```bash
# Processa tutti i PDF nella cartella:
python dbConnection.py

# Oppure un singolo file:
python dbConnection.py 79824327-La-Risotteria.pdf
```

Il log viene salvato in `pipeline.log`.

### 7. Nota sulla rete

Se il server (macchina 2) è su un'altra macchina, apri `database/dbConnection.py`  
e in `Config` lascia `DB_HOST = "localhost"` (il DB è su questa macchina).  
In `server/config.py` invece metti `DB_HOST = "<IP-MACCHINA-3>"`.

---

## Macchina 2 — Server Flask (Mattia)

### 1. Installa Ollama

Scarica da https://ollama.com e avvialo:
```bash
ollama serve
ollama pull gemma3:4b
```

### 2. Crea l'ambiente virtuale Python

```bash
cd server
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configura config.py

Apri `server/config.py` e modifica:
```python
DB_HOST = "192.168.X.X"   # IP della macchina 3 (database)
```
Se il DB è sulla stessa macchina del server, lascia `"localhost"`.

### 4. Avvia il server

```bash
python server.py
```

All'avvio vengono eseguiti i controlli di connessione a DB e Ollama.  
Il server sarà raggiungibile su `http://<IP-QUESTA-MACCHINA>:5000`.

### 5. Verifica il funzionamento

Dal browser di qualsiasi macchina nella rete:
```
http://<IP-SERVER>:5000/api/health
```
Risposta attesa: `{"server":"ok","database":"ok","ollama":"ok"}`

---

## Macchina 1 — Frontend

### 1. Configura l'IP del server

Apri `frontend/script.js` e modifica la prima riga:
```javascript
const SERVER_URL = "http://192.168.X.X:5000";  // IP della macchina 2
```

### 2. Apri la chat

Apri `frontend/index.html` direttamente nel browser  
(doppio clic sul file, nessun server web necessario).

---

## Flusso di una richiesta

```
[Browser - Macchina 1]
      │  POST /api/chat  { question: "Come si fa il risotto?" }
      ▼
[Flask Server - Macchina 2]
      │  1. Cerca ricette rilevanti nel DB (FULLTEXT + JOIN ingredienti)
      │  2. Costruisce il contesto RAG
      │  3. Invia contesto + domanda a Ollama
      ▼
[MySQL - Macchina 3]          [Ollama locale - Macchina 2]
  ricette + ingredienti  →  genera risposta con gemma3:4b
      │
      ▼
[Browser - Macchina 1]
      { answer: "Ecco la ricetta del risotto..." }
```

---

## Endpoint API del server

| Metodo | URL | Descrizione |
|--------|-----|-------------|
| `POST` | `/api/chat` | Invia `{"question":"..."}`, riceve `{"answer":"...","ricette_trovate":N}` |
| `GET`  | `/api/health` | Stato di server, DB e Ollama |
| `GET`  | `/api/ricette?limit=20` | Lista ricette nel DB (debug) |

---

## Dipendenze riassuntive

**Macchina server** (pip):
`flask`, `flask-cors`, `mysql-connector-python`, `requests`

**Macchina database** (pip):
`pypdf`, `ollama`, `mysql-connector-python`, `langchain`, `langchain-chroma`,
`langchain-ollama`, `langchain-text-splitters`, `chromadb`

**Ollama** (modelli da pullare):
- `gemma3:4b` — su macchina server (generazione risposte)
- `gemma3:4b` — su macchina database (estrazione ricette dai PDF)
- `nomic-embed-text` — su macchina database (embedding per VectorStore)
