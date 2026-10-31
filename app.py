import streamlit as st
import sqlite3
import os
import re
import unicodedata

st.set_page_config(page_title="Gestione Laboratorio PC", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "laboratorio_pc.db")

STATI = ["In attesa", "In lavorazione", "Pronto", "Consegnato"]


@st.cache_resource
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


conn = get_conn()
c = conn.cursor()

c.execute('''
    CREATE TABLE IF NOT EXISTS registro (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente TEXT,
        modello TEXT,
        problema TEXT,
        stato TEXT,
        data_ingresso TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')
c.execute('''
    CREATE TABLE IF NOT EXISTS enciclopedia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        componente TEXT,
        sintomo TEXT,
        soluzione TEXT
    )
''')
conn.commit()

# ==========================================
# MOTORE DI RICERCA
# ==========================================
STOPWORDS = {
    "il", "lo", "la", "le", "li", "i", "gli", "un", "uno", "una", "di", "a", "da",
    "in", "con", "su", "per", "tra", "fra", "e", "ed", "o", "ma", "si", "non", "che",
    "del", "della", "dei", "delle", "al", "alla", "ai", "alle", "nel", "nella",
    "sul", "sulla", "mi", "ti", "ci", "ha", "ho", "è", "e'", "sono", "fa", "fanno",
    "pc", "computer", "notebook", "portatile", "desktop", "problema", "guasto",
}

SINONIMI = {
    "bip": "beep", "schermata": "schermo", "monitor": "schermo", "display": "schermo",
    "lento": "lent", "lenta": "lent", "rallenta": "lent", "scatta": "lent",
    "caldo": "temperatura", "surriscalda": "temperatura", "surriscaldamento": "temperatura",
    "ventola": "ventole", "ventilatore": "ventole",
    "hd": "disco", "hdd": "disco", "ssd": "disco", "hard": "disco",
    "wifi": "wi-fi", "wireless": "wi-fi",
    "accende": "accensione", "accendo": "accensione", "avvia": "avvio",
    "bsod": "blu", "blue": "blu",
}


def normalizza(testo):
    testo = unicodedata.normalize("NFD", testo.lower())
    testo = "".join(ch for ch in testo if unicodedata.category(ch) != "Mn")
    return re.findall(r"[a-z0-9]+", testo)


def token_record(testo):
    out = []
    for t in normalizza(testo):
        out.append(SINONIMI.get(t, t))
    return out


def radici_query(testo):
    radici = []
    for p in normalizza(testo):
        if p in STOPWORDS:
            continue
        p = SINONIMI.get(p, p)
        p = re.sub(r"[^a-z0-9]", "", p)
        if len(p) >= 2:
            radici.append(p[:5])  # radice approssimata: bloccano/blocca -> blocc
    return radici


def cerca_soluzioni(chiave):
    radici = set(radici_query(chiave))
    if not radici:
        return []
    c.execute("SELECT id, componente, sintomo, soluzione FROM enciclopedia")
    risultati = []
    for row in c.fetchall():
        tok_titolo = token_record(f"{row[1]} {row[2]}")
        tok_sol = token_record(row[3])
        punteggio = 0
        for r in radici:
            if any(t.startswith(r) for t in tok_titolo):
                punteggio += 2
            elif any(t.startswith(r) for t in tok_sol):
                punteggio += 1
        if punteggio:
            risultati.append((punteggio, row))
    risultati.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in risultati]


st.title("💻 Sistema Gestione Riparazioni PC")

tab1, tab2, tab3, tab4 = st.tabs([
    "📥 Accettazione",
    "📋 Registro PC",
    "🔍 Cerca/Aggiungi Soluzioni",
    "📚 Gestione Enciclopedia"
])

# ==========================================
# 1. ACCETTAZIONE
# ==========================================
with tab1:
    st.header("Inserisci Nuovo PC in Riparazione")
    with st.form("form_accettazione", clear_on_submit=True):
        cliente = st.text_input("Nome Cliente")
        modello = st.text_input("Modello PC / Componente")
        problema = st.text_area("Descrizione del Problema")
        stato = st.selectbox("Stato Iniziale", STATI)
        submit = st.form_submit_button("Registra Ingresso")

        if submit:
            if cliente and modello:
                c.execute(
                    "INSERT INTO registro (cliente, modello, problema, stato) VALUES (?, ?, ?, ?)",
                    (cliente, modello, problema, stato)
                )
                conn.commit()
                st.success(f"PC di {cliente} registrato con successo!")
            else:
                st.error("I campi 'Cliente' e 'Modello' sono obbligatori.")

# ==========================================
# 2. REGISTRO PC
# ==========================================
with tab2:
    st.header("Stato Riparazioni")
    filtro_stato = st.selectbox("Filtra per Stato", ["Tutti"] + STATI)

    if filtro_stato == "Tutti":
        c.execute("SELECT * FROM registro ORDER BY id DESC")
    else:
        c.execute("SELECT * FROM registro WHERE stato=? ORDER BY id DESC", (filtro_stato,))
    elenco = c.fetchall()

    if not elenco:
        st.info("Nessun PC presente nel registro con i filtri selezionati.")
    else:
        for pc in elenco:
            with st.expander(f"ID {pc[0]} - {pc[1]} | {pc[2]} ({pc[4]})"):
                st.write(f"**Problema:** {pc[3]}")
                st.write(f"**Data Ingresso:** {pc[5]}")

                col1, col2 = st.columns(2)
                with col1:
                    idx = STATI.index(pc[4]) if pc[4] in STATI else 0
                    nuovo_stato = st.selectbox(
                        f"Aggiorna Stato ID {pc[0]}", STATI, index=idx, key=f"stato_{pc[0]}"
                    )
                    if st.button("Salva Stato", key=f"save_{pc[0]}"):
                        c.execute("UPDATE registro SET stato=? WHERE id=?", (nuovo_stato, pc[0]))
                        conn.commit()
                        st.rerun()
                with col2:
                    if st.button("❌ Rimuovi dal Registro", key=f"del_reg_{pc[0]}"):
                        c.execute("DELETE FROM registro WHERE id=?", (pc[0],))
                        conn.commit()
                        st.rerun()

# ==========================================
# 3. CERCA / AGGIUNGI SOLUZIONI
# ==========================================
with tab3:
    st.header("Ricerca Guasti e Soluzioni")
    chiave = st.text_input(
        "Descrivi il problema (es. schermata blu, beep, mouse bloccato, non si accende, batteria...)"
    )

    if chiave:
        risultati = cerca_soluzioni(chiave)
        if risultati:
            st.subheader(f"Risultati trovati ({len(risultati)}), dal più pertinente:")
            for res in risultati:
                with st.expander(f"#{res[0]} · {res[1]} — {res[2]}", expanded=len(risultati) <= 3):
                    st.write(f"**💡 Soluzione:** {res[3]}")
        else:
            st.warning("Nessuna soluzione trovata. Aggiungila qui sotto: la prossima volta la ritroverai.")

    st.markdown("---")
    st.subheader("➕ Aggiungi una nuova soluzione")
    with st.form("form_enc_tab3", clear_on_submit=True):
        comp3 = st.text_input("Componente (es. RAM, Alimentatore, Batteria notebook)")
        sint3 = st.text_input("Sintomo")
        sol3 = st.text_area("Soluzione")
        if st.form_submit_button("Salva nell'Enciclopedia"):
            if comp3 and sint3 and sol3:
                c.execute(
                    "INSERT INTO enciclopedia (componente, sintomo, soluzione) VALUES (?, ?, ?)",
                    (comp3, sint3, sol3)
                )
                conn.commit()
                st.success("Soluzione salvata!")
            else:
                st.error("Compila tutti i campi.")

# ==========================================
# 4. GESTIONE ENCICLOPEDIA
# ==========================================
with tab4:
    st.header("Archivio Enciclopedia Risoluzioni")

    st.subheader("➕ Aggiungi Nuova Risoluzione")
    with st.form("form_enciclopedia", clear_on_submit=True):
        comp = st.text_input("Componente")
        sint = st.text_input("Sintomo Riscontrato")
        sol = st.text_area("Soluzione Tecnica applicata")
        submit_enc = st.form_submit_button("Salva nell'Enciclopedia")
        if submit_enc:
            if comp and sint and sol:
                c.execute(
                    "INSERT INTO enciclopedia (componente, sintomo, soluzione) VALUES (?, ?, ?)",
                    (comp, sint, sol)
                )
                conn.commit()
                st.rerun()
            else:
                st.error("Tutti i campi sono richiesti per salvare la scheda.")

    st.markdown("---")

    c.execute("SELECT COUNT(*) FROM enciclopedia")
    totale = c.fetchone()[0]
    st.subheader(f"Tutti i Record ({totale})")

    filtro = st.text_input("Filtra l'elenco per componente o sintomo", key="filtro_enc")

    c.execute("SELECT id, componente, sintomo, soluzione FROM enciclopedia ORDER BY componente, id")
    tutti_guasti = c.fetchall()

    if filtro:
        radici_f = set(radici_query(filtro))
        tutti_guasti = [
            g for g in tutti_guasti
            if all(any(t.startswith(r) for t in token_record(f"{g[1]} {g[2]}")) for r in radici_f)
        ] if radici_f else tutti_guasti

    if not tutti_guasti:
        st.write("Nessun record da mostrare.")
    else:
        for g in tutti_guasti:
            with st.expander(f"#{g[0]} · {g[1]} — {g[2]}"):
                n_comp = st.text_input("Componente", g[1], key=f"ec_c_{g[0]}")
                n_sint = st.text_input("Sintomo", g[2], key=f"ec_s_{g[0]}")
                n_sol = st.text_area("Soluzione", g[3], key=f"ec_l_{g[0]}")
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("💾 Salva modifiche", key=f"ec_save_{g[0]}"):
                        c.execute(
                            "UPDATE enciclopedia SET componente=?, sintomo=?, soluzione=? WHERE id=?",
                            (n_comp, n_sint, n_sol, g[0])
                        )
                        conn.commit()
                        st.rerun()
                with b2:
                    if st.button("🗑️ Elimina", key=f"ec_del_{g[0]}"):
                        c.execute("DELETE FROM enciclopedia WHERE id=?", (g[0],))
                        conn.commit()
                        st.rerun()