import sqlite3
import os
import numpy as np
from sentence_transformers import SentenceTransformer, util

DB_FILE = os.path.expanduser("~/.workspace_agent_memory.db")
MODEL = SentenceTransformer("all-MiniLM-L6-v2")

def init_memory_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS command_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        command TEXT,
        embedding BLOB
    )
    """)
    conn.commit()
    conn.close()

def save_command(command: str):
    embedding = MODEL.encode(command)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO command_memory (command, embedding) VALUES (?, ?)", 
              (command, embedding.tobytes()))
    conn.commit()
    conn.close()

def retrieve_similar(query: str, top_n=3):
    query_emb = MODEL.encode(query)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT command, embedding FROM command_memory")
    results = []
    for command, blob in c.fetchall():
        emb = np.frombuffer(blob, dtype=np.float32)
        sim = util.cos_sim(query_emb, emb)[0].item()
        results.append((command, sim))
    conn.close()
    return sorted(results, key=lambda x: x[1], reverse=True)[:top_n]
