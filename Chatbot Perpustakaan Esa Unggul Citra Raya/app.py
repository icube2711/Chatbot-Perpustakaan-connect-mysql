import json, os, random, re
from flask import Flask, render_template, request, jsonify
from gtts import gTTS
from fuzzywuzzy import fuzz
import mysql.connector
from mysql.connector import Error

from dotenv import load_dotenv
load_dotenv()  # Biar bisa baca file .env saat development

app = Flask(__name__)
app.static_folder = "static"

# Fungsi untuk membuat koneksi ke database Railway
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQLHOST", "localhost"),
        user=os.getenv("MYSQLUSER", "root"),
        password=os.getenv("MYSQLPASSWORD", ""),
        database=os.getenv("MYSQLDATABASE", "crud"),
        port=int(os.getenv("MYSQLPORT", 3306))
    )

# Load intents dari database
def load_intents_from_db():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM intents")
        rows = cur.fetchall()

        intents = {"intents": []}
        for row in rows:
            intents["intents"].append({
                "tag": row["tag"],
                "patterns": json.loads(row["patterns"]),
                "responses": json.loads(row["responses"])
            })
        return intents
    except Error as e:
        print("Database error:", e)
        return {"intents": []}
    finally:
        try:
            if conn and conn.is_connected():
                cur.close()
                conn.close()
        except:
            pass

intents = load_intents_from_db()

def clean_text(text):
    return re.sub(r"[^\w\s]", "", text.lower()).strip()

def get_all_subject_keywords():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT subject FROM books")
        results = cur.fetchall()
        return [row[0].lower() for row in results if row[0]]
    except Error as e:
        print("DB Error (get_all_subject_keywords):", e)
        return []
    finally:
        try:
            if conn and conn.is_connected():
                cur.close()
                conn.close()
        except:
            pass

def search_books_by_title(user_input):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT title, availability, location FROM books")
        books = cur.fetchall()

        best_score = 0
        matched_book = None
        for book in books:
            score = fuzz.partial_ratio(user_input.lower(), book['title'].lower())
            if score > best_score and score >= 75:
                best_score = score
                matched_book = book

        if matched_book:
            status = "tersedia" if matched_book['availability'] == 'tersedia' else "sedang dipinjam"
            return f"Buku \"{matched_book['title']}\" saat ini {status} (rak {matched_book['location']})", best_score, matched_book['title']

        return None, 0, None
    except Error as e:
        print("DB Error (search_books_by_title):", e)
        return None, 0, None
    finally:
        try:
            if conn and conn.is_connected():
                cur.close()
                conn.close()
        except:
            pass

def search_books_by_subject(user_input):
    subject_keywords = get_all_subject_keywords()
    matched_subject = next((kw for kw in subject_keywords if kw in user_input.lower()), None)

    if not matched_subject:
        return None

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT title, location FROM books 
            WHERE subject LIKE %s AND availability = 'tersedia'
        """, ('%' + matched_subject + '%',))
        results = cur.fetchall()

        if results:
            lokasi_rak = results[0]['location']
            daftar_judul = "\n".join([f"{i+1}. {row['title']}" for i, row in enumerate(results)])
            return f"Ada {len(results)} buku tentang {matched_subject} di rak {lokasi_rak}:\n{daftar_judul}"
        else:
            return f"Maaf, belum ada buku {matched_subject} yang tersedia saat ini."
    except Error as e:
        print("DB Error (books):", e)
        return None
    finally:
        try:
            if conn and conn.is_connected():
                cur.close()
                conn.close()
        except:
            pass

def find_best_match(user_input):
    user_input = clean_text(user_input)

    dynamic_book_response = search_books_by_subject(user_input)
    if dynamic_book_response:
        return dynamic_book_response, 100, "pencarian_subject"

    book_title_response, book_score, book_pattern = search_books_by_title(user_input)
    if book_title_response:
        return book_title_response, book_score, book_pattern

    best_score = 0
    best_response = "Maaf, saya tidak mengerti maksud Anda."
    best_pattern = ""

    for intent in intents['intents']:
        for pattern in intent['patterns']:
            pattern_clean = clean_text(pattern)
            score1 = fuzz.partial_ratio(user_input, pattern_clean)
            score2 = fuzz.token_sort_ratio(user_input, pattern_clean)
            final_score = (score1 + score2) / 2

            if final_score > best_score:
                best_score = final_score
                best_response = random.choice(intent['responses'])
                best_pattern = pattern

    if best_score < 80:
        return "Maaf, saya tidak mengerti maksud Anda.", best_score, ""

    return best_response, best_score, best_pattern

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/get")
def get_bot_response():
    user_txt = request.args.get("msg", "").strip()
    if not user_txt:
        return jsonify({"response": "Mohon masukkan pesan Anda.", "score": 0, "pattern": ""})

    response, score, pattern = find_best_match(user_txt)
    return jsonify({
        "response": response,
        "score": score,
        "pattern": pattern
    })

# Run on Railway's dynamic PORT
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
