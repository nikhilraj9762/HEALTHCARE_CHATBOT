from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from dotenv import load_dotenv
load_dotenv()

import requests
import re
import sqlite3
from datetime import datetime, date, timedelta
from symptom_service import is_symptom_query, get_ai_symptom_response, get_general_ai_response
from math import radians, cos, sin, asin, sqrt
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = "healthcare_chatbot_super_secret_key_2026"
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

# -----------------------------
# Chat state for step-by-step reminder conversation
# -----------------------------
chat_state = {
    "mode": None,
    "reminder_data": {}
}

EMERGENCY_KEYWORDS = [
    "chest pain",
    "breathing difficulty",
    "can't breathe",
    "cannot breathe",
    "stroke",
    "face drooping",
    "slurred speech",
    "severe bleeding",
    "unconscious",
    "heart attack",
    "seizure"
]

# -----------------------------
# Database helpers
# -----------------------------
def get_db_connection():
    conn = sqlite3.connect("healthcare.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medicine_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            dosage TEXT NOT NULL,
            date TEXT NOT NULL,
            end_date TEXT,
            time TEXT NOT NULL,
            schedule TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            doctor TEXT,
            hospital TEXT,
            date TEXT,
            time TEXT,
            purpose TEXT,
            location TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


def init_auth_tables():
    # Kept for compatibility with your old structure
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def create_default_admin():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM admins WHERE email = ?", ("admin@gmail.com",))
    existing_admin = cursor.fetchone()

    if not existing_admin:
        hashed_password = generate_password_hash("admin123")
        cursor.execute("""
            INSERT INTO admins (full_name, email, password)
            VALUES (?, ?, ?)
        """, ("Admin", "admin@gmail.com", hashed_password))
        conn.commit()

    conn.close()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "admin_id" not in session:
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function


# -----------------------------
# Medicine reminder DB functions
# -----------------------------
def add_medicine_reminder(user_id, name, dosage, reminder_date, reminder_time, schedule, end_date=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO medicine_reminders (user_id, name, dosage, date, end_date, time, schedule)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, name, dosage, reminder_date, end_date, reminder_time, schedule))
    conn.commit()
    reminder_id = cursor.lastrowid
    conn.close()

    return {
        "id": reminder_id,
        "user_id": user_id,
        "name": name,
        "dosage": dosage,
        "date": reminder_date,
        "end_date": end_date,
        "time": reminder_time,
        "schedule": schedule
    }


def get_all_medicine_reminders(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM medicine_reminders
        WHERE user_id = ?
        ORDER BY date ASC, time ASC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_today_medicine_reminders(user_id):
    today = date.today().strftime("%Y-%m-%d")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM medicine_reminders
        WHERE user_id = ? AND date = ?
        ORDER BY time ASC
    """, (user_id, today))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# -----------------------------
# Appointment DB functions
# -----------------------------
def add_appointment(user_id, doctor, hospital, appointment_date, appointment_time, purpose, location):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO appointments (user_id, doctor, hospital, date, time, purpose, location)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, doctor, hospital, appointment_date, appointment_time, purpose, location))

    conn.commit()
    appointment_id = cursor.lastrowid
    conn.close()

    return {
        "id": appointment_id,
        "user_id": user_id,
        "doctor": doctor,
        "hospital": hospital,
        "date": appointment_date,
        "time": appointment_time,
        "purpose": purpose,
        "location": location
    }


def get_all_appointments(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM appointments
        WHERE user_id = ?
        ORDER BY date ASC, time ASC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_today_appointments(user_id):
    today = date.today().strftime("%Y-%m-%d")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM appointments
        WHERE user_id = ? AND date = ?
        ORDER BY time ASC
    """, (user_id, today))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_next_appointment(user_id):
    today = date.today().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM appointments
        WHERE user_id = ?
          AND (date > ? OR (date = ? AND time >= ?))
        ORDER BY date ASC, time ASC
        LIMIT 1
    """, (user_id, today, today, now_time))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_appointments_by_doctor(user_id, doctor_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM appointments
        WHERE user_id = ? AND LOWER(doctor) LIKE ?
        ORDER BY date ASC, time ASC
    """, (user_id, f"%{doctor_name.lower()}%"))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_tomorrow_appointments(user_id):
    tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM appointments
        WHERE user_id = ? AND date = ?
        ORDER BY time ASC
    """, (user_id, tomorrow))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# -----------------------------
# Appointment formatting helpers
# -----------------------------
def format_all_appointments(user_id):
    appointments = get_all_appointments(user_id)

    if not appointments:
        return "You do not have any appointments booked yet."

    lines = ["Your booked appointments are:"]
    for i, appt in enumerate(appointments, start=1):
        lines.append(
            f"{i}. Dr. {appt['doctor']} at {appt['hospital']} on {appt['date']} at {appt['time']}. "
            f"Location: {appt['location']}. Purpose: {appt['purpose']}."
        )
    return "\n".join(lines)


def format_today_appointments(user_id):
    appointments = get_today_appointments(user_id)
    today = date.today().strftime("%Y-%m-%d")

    if not appointments:
        return f"You do not have any appointments today ({today})."

    lines = [f"Your appointments for today ({today}) are:"]
    for i, appt in enumerate(appointments, start=1):
        lines.append(
            f"{i}. Dr. {appt['doctor']} at {appt['hospital']} at {appt['time']}. "
            f"Location: {appt['location']}. Purpose: {appt['purpose']}."
        )
    return "\n".join(lines)


def format_next_appointment(user_id):
    appt = get_next_appointment(user_id)

    if not appt:
        return "You do not have any upcoming appointments."

    return (
        f"Your next appointment is with Dr. {appt['doctor']} at {appt['hospital']} "
        f"on {appt['date']} at {appt['time']}. Location: {appt['location']}. "
        f"Purpose: {appt['purpose']}."
    )


def format_appointments_by_doctor(user_id, doctor_name):
    appointments = get_appointments_by_doctor(user_id, doctor_name)

    if not appointments:
        return f"I could not find any appointment with Dr. {doctor_name.title()}."

    lines = [f"Appointments found for Dr. {doctor_name.title()}:"]

    for i, appt in enumerate(appointments, start=1):
        lines.append(
            f"{i}. {appt['date']} at {appt['time']} at {appt['hospital']}. "
            f"Location: {appt['location']}. Purpose: {appt['purpose']}."
        )
    return "\n".join(lines)


def format_tomorrow_appointments(user_id):
    appointments = get_tomorrow_appointments(user_id)
    tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    if not appointments:
        return f"You do not have any appointments tomorrow ({tomorrow})."

    lines = [f"Your appointments for tomorrow ({tomorrow}) are:"]
    for i, appt in enumerate(appointments, start=1):
        lines.append(
            f"{i}. Dr. {appt['doctor']} at {appt['hospital']} at {appt['time']}. "
            f"Location: {appt['location']}. Purpose: {appt['purpose']}."
        )
    return "\n".join(lines)


# -----------------------------
# Symptom checker
# -----------------------------
def analyze_symptoms(user_text):
    text = user_text.lower()

    for keyword in EMERGENCY_KEYWORDS:
        if keyword in text:
            return (
                "This may be a medical emergency. Please seek immediate medical help or go to the nearest hospital right away. "
                "Do not wait for chatbot advice."
            )

    if "headache" in text or "migraine" in text:
        return (
            "This may be a headache or migraine. Please tell me whether the pain is mild or severe, "
            "and whether you also have fever, vomiting, or sensitivity to light. "
            "General care: rest, drink water, and avoid bright light. "
            "This is not a final medical diagnosis."
        )

    if "fever" in text and "cough" in text:
        return (
            "These symptoms may be related to cold, flu, or viral infection. "
            "Please tell me if you also have sore throat, body pain, or breathing trouble. "
            "General care: rest, fluids, and monitor temperature. "
            "This is not a final medical diagnosis."
        )

    if "cold" in text or "runny nose" in text or "sneezing" in text:
        return (
            "This may be a common cold or mild allergy. Please tell me if you also have fever, cough, or throat pain. "
            "General care: warm fluids, rest, and steam inhalation. "
            "This is not a final medical diagnosis."
        )

    if "stomach pain" in text or "vomiting" in text or "diarrhea" in text:
        return (
            "These symptoms may be related to indigestion or stomach infection. "
            "Please tell me if you also have fever, dehydration, or severe abdominal pain. "
            "General care: drink water, take ORS if needed, eat light food, and rest. "
            "This is not a final medical diagnosis."
        )

    if "body pain" in text or "weakness" in text or "fatigue" in text:
        return (
            "This may happen with viral illness, dehydration, poor sleep, or general weakness. "
            "Please tell me if you also have fever, cough, dizziness, or loss of appetite. "
            "This is not a final medical diagnosis."
        )

    return (
        "Please describe your symptoms more clearly, for example: headache, fever, cough, stomach pain, weakness, "
        "breathing trouble, or chest pain. I can guide you safely, but this is not a final diagnosis."
    )


# -----------------------------
# Medicine info API
# -----------------------------
def get_medicine_info(medicine_name):
    try:
        url = "https://api.fda.gov/drug/label.json"
        params = {
            "search": f'openfda.generic_name:"{medicine_name}" OR openfda.brand_name:"{medicine_name}"',
            "limit": 1
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if "results" not in data or not data["results"]:
            return f"Sorry, I could not find reliable information for {medicine_name}."

        result = data["results"][0]
        purpose = result.get("purpose", [""])
        warnings = result.get("warnings", [""])
        indications = result.get("indications_and_usage", [""])

        parts = [f"Medicine information for {medicine_name}:"]

        if purpose[0]:
            parts.append(f"Purpose: {purpose[0]}")
        if indications[0]:
            parts.append(f"Use: {indications[0][:250]}")
        if warnings[0]:
            parts.append(f"Warning: {warnings[0][:250]}")

        parts.append(
            "Please do not take any medicine without proper medical advice, especially for elderly patients or those with multiple conditions."
        )

        return "\n\n".join(parts)

    except Exception:
        return (
            f"Sorry, I could not fetch medicine information for {medicine_name} right now. "
            "Please consult a pharmacist or doctor before using any medicine."
        )


# -----------------------------
# Time helpers
# -----------------------------
def normalize_time(raw_time):
    raw_time = raw_time.strip().lower()
    raw_time = raw_time.replace(".", "")
    raw_time = " ".join(raw_time.split())

    raw_time = re.sub(r"(\d)(am|pm)$", r"\1 \2", raw_time)
    raw_time = re.sub(r"(\d{1,2}:\d{2})(am|pm)$", r"\1 \2", raw_time)

    formats = ["%I %p", "%I:%M %p", "%H:%M", "%H"]

    for fmt in formats:
        try:
            return datetime.strptime(raw_time, fmt).strftime("%H:%M")
        except ValueError:
            continue

    return None


def normalize_date(raw_date):
    text = raw_date.strip().lower()

    text = text.replace("/", "-")
    text = text.replace(".", "-")
    text = text.replace(" dash ", "-")
    text = text.replace(" slash ", "-")
    text = text.replace(" minus ", "-")
    text = " ".join(text.split())
    text = text.replace(" - ", "-").replace(" -", "-").replace("- ", "-")

    date_formats = [
        "%Y-%m-%d",
        "%Y %m %d",
        "%d-%m-%Y",
        "%d %m %Y",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d %Y",
        "%b %d %Y"
    ]

    for fmt in date_formats:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


# -----------------------------
# Reminder parsing
# -----------------------------
def parse_reminder_command(message, user_id):
    text = message.lower().strip()

    pattern_with_dosage = r"(?:set reminder for|remind me to take)\s+(.+?)\s+(\d+\s*\w+.*?)\s+on\s+(\d{4}-\d{2}-\d{2})\s+at\s+([0-9: ]+(?:am|pm|a\.m\.|p\.m\.)?)\s*(daily|everyday|once|morning|afternoon|evening|night)?"
    match = re.search(pattern_with_dosage, text)

    if match:
        med_name = match.group(1).strip().title()
        dosage = match.group(2).strip()
        reminder_date = match.group(3).strip()
        raw_time = match.group(4).strip()
        schedule = (match.group(5) or "Daily").title()

        parsed_time = normalize_time(raw_time)
        if not parsed_time:
            return None

        return add_medicine_reminder(user_id, med_name, dosage, reminder_date, parsed_time, schedule)

    pattern_simple = r"(?:set reminder for|remind me to take)\s+(.+?)\s+on\s+(\d{4}-\d{2}-\d{2})\s+at\s+([0-9: ]+(?:am|pm|a\.m\.|p\.m\.)?)\s*(daily|everyday|once|morning|afternoon|evening|night)?"
    match = re.search(pattern_simple, text)

    if match:
        med_name = match.group(1).strip().title()
        reminder_date = match.group(2).strip()
        raw_time = match.group(3).strip()
        schedule = (match.group(4) or "Daily").title()

        parsed_time = normalize_time(raw_time)
        if not parsed_time:
            return None

        return add_medicine_reminder(user_id, med_name, "As prescribed", reminder_date, parsed_time, schedule)

    return None


# -----------------------------
# Reminder formatting
# -----------------------------
def format_all_reminders(user_id):
    reminders = get_all_medicine_reminders(user_id)

    if not reminders:
        return "You do not have any medicine reminders yet."

    lines = ["Your medicine reminders are:"]
    for i, med in enumerate(reminders, start=1):
        if str(med.get("schedule", "")).lower() == "daily":
            lines.append(
                f"{i}. {med['name']} - {med['dosage']} - from {med['date']} until {med.get('end_date', 'Not set')} at {med['time']} - {med['schedule']}"
            )
        else:
            lines.append(
                f"{i}. {med['name']} - {med['dosage']} - {med['date']} at {med['time']} - {med['schedule']}"
            )
    return "\n".join(lines)


def format_today_reminders(user_id):
    today = date.today().strftime("%Y-%m-%d")
    reminders = get_all_medicine_reminders(user_id)

    today_list = []
    for med in reminders:
        schedule = str(med.get("schedule", "")).lower()

        if schedule == "daily":
            start_date = med.get("date")
            end_date = med.get("end_date")
            if start_date and end_date and start_date <= today <= end_date:
                today_list.append(med)
        else:
            if med.get("date") == today:
                today_list.append(med)

    today_list.sort(key=lambda x: x["time"])

    if not today_list:
        return f"You have no medicine reminders for today ({today})."

    lines = [f"Today's dosages for {today} are:"]
    for i, med in enumerate(today_list, start=1):
        lines.append(
            f"{i}. {med['name']} - {med['dosage']} at {med['time']} - {med['schedule']}"
        )
    return "\n".join(lines)


def get_next_today_dosage(user_id):
    today = date.today().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M")
    reminders = get_all_medicine_reminders(user_id)

    today_list = []
    for med in reminders:
        schedule = str(med.get("schedule", "")).lower()

        if schedule == "daily":
            start_date = med.get("date")
            end_date = med.get("end_date")
            if start_date and end_date and start_date <= today <= end_date:
                today_list.append(med)
        else:
            if med.get("date") == today:
                today_list.append(med)

    today_list.sort(key=lambda x: x["time"])

    if not today_list:
        return f"You have no medicine reminders for today ({today})."

    for med in today_list:
        if med["time"] >= now_time:
            return f"The next dosage for today is {med['name']} - {med['dosage']} at {med['time']}."

    last_med = today_list[-1]
    return (
        f"All of today's scheduled dosages have passed. The last one was "
        f"{last_med['name']} - {last_med['dosage']} at {last_med['time']}."
    )


# -----------------------------
# Step-by-step reminder conversation
# -----------------------------
def save_reminder_from_state(user_id):
    data = chat_state["reminder_data"]

    medicine = add_medicine_reminder(
        user_id,
        data["name"],
        data["dosage"],
        data["date"],
        data["time"],
        data["schedule"],
        data.get("end_date")
    )

    chat_state["mode"] = None
    chat_state["reminder_data"] = {}

    return medicine


def handle_reminder_conversation(message, user_id):
    if chat_state["mode"] == "awaiting_reminder_name":
        chat_state["reminder_data"]["name"] = message.strip().title()
        chat_state["mode"] = "awaiting_reminder_dosage"
        return "What dosage should I save?"

    if chat_state["mode"] == "awaiting_reminder_dosage":
        chat_state["reminder_data"]["dosage"] = message.strip()
        chat_state["mode"] = "awaiting_reminder_schedule"
        return "Should I set it as once or daily?"

    if chat_state["mode"] == "awaiting_reminder_schedule":
        schedule_text = message.strip().lower()

        if schedule_text not in ["once", "daily"]:
            return "Please type only once or daily."

        chat_state["reminder_data"]["schedule"] = schedule_text.title()

        if schedule_text == "once":
            chat_state["mode"] = "awaiting_reminder_date"
            return "What date should I set it for? Please use format YYYY-MM-DD."

        if schedule_text == "daily":
            chat_state["mode"] = "awaiting_reminder_start_date"
            return "What start date should I set it from? Please use format YYYY-MM-DD."

    if chat_state["mode"] == "awaiting_reminder_date":
        date_text = message.strip()
        parsed_date = normalize_date(date_text)

        if not parsed_date:
            return "Please enter a valid date. Example: 2026-03-21."

        chat_state["reminder_data"]["date"] = parsed_date
        chat_state["reminder_data"]["end_date"] = None
        chat_state["mode"] = "awaiting_reminder_time"
        return "What time should I set it for? For example: 8 PM or 08:30 AM."

    if chat_state["mode"] == "awaiting_reminder_start_date":
        date_text = message.strip()
        parsed_date = normalize_date(date_text)

        if not parsed_date:
            return "Please enter a valid start date. Example: 2026-03-21."

        chat_state["reminder_data"]["date"] = parsed_date
        chat_state["mode"] = "awaiting_reminder_end_date"
        return "What end date should I set it until? Please use format YYYY-MM-DD."

    if chat_state["mode"] == "awaiting_reminder_end_date":
        date_text = message.strip()
        parsed_date = normalize_date(date_text)

        if not parsed_date:
            return "Please enter a valid end date. Example: 2026-03-30."

        start_date = datetime.strptime(chat_state["reminder_data"]["date"], "%Y-%m-%d")
        end_date = datetime.strptime(parsed_date, "%Y-%m-%d")

        if end_date < start_date:
            return "End date cannot be before start date. Please enter a valid end date."

        chat_state["reminder_data"]["end_date"] = parsed_date
        chat_state["mode"] = "awaiting_reminder_time"
        return "What time should I set it for? For example: 8 PM or 08:30 AM."

    if chat_state["mode"] == "awaiting_reminder_time":
        clean_time = message.strip().replace(",", "").replace("?", "").replace("!", "")
        parsed_time = normalize_time(clean_time)

        if not parsed_time:
            return "Please enter a valid time, for example: 8 PM or 08:30 AM."

        chat_state["reminder_data"]["time"] = parsed_time
        medicine = save_reminder_from_state(user_id)

        if medicine["schedule"].lower() == "daily":
            return (
                f"Daily reminder added successfully for {medicine['name']} with dosage {medicine['dosage']} "
                f"from {medicine['date']} until {medicine['end_date']} at {medicine['time']}."
            )

        return (
            f"One-time reminder added successfully for {medicine['name']} with dosage {medicine['dosage']} "
            f"on {medicine['date']} at {medicine['time']}."
        )

    return None


# -----------------------------
# Nearby search helpers
# -----------------------------
def calculate_distance_km(lat1, lon1, lat2, lon2):
    lon1, lat1, lon2, lat2 = map(float, [lon1, lat1, lon2, lat2])
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    r = 6371
    return round(c * r, 2)


def is_nearby_search_query(message):
    msg = message.lower()
    nearby_words = ["near me", "nearby", "closest", "nearest"]
    place_words = [
        "pharmacy", "hospital", "dentist", "doctor", "clinic",
        "gynecologist", "gynaecologist", "cardiologist", "heart hospital",
        "heart checkup", "skin doctor", "dermatologist"
    ]
    return any(a in msg for a in nearby_words) and any(b in msg for b in place_words)


def detect_place_type(message):
    msg = message.lower()

    if "pharmacy" in msg or "medical shop" in msg:
        return "pharmacy"

    if "dentist" in msg or "dental" in msg:
        return "dentist"

    if "gynecologist" in msg or "gynaecologist" in msg or "women doctor" in msg:
        return "gynecologist"

    if "cardiologist" in msg or "heart checkup" in msg or "heart hospital" in msg:
        return "cardiology"

    if "skin doctor" in msg or "dermatologist" in msg:
        return "dermatologist"

    if "clinic" in msg:
        return "clinic"

    if "doctor" in msg:
        return "doctor"

    return "hospital"


def build_overpass_query(lat, lon, place_type):
    if place_type == "pharmacy":
        return f"""
        [out:json][timeout:25];
        (
          node["amenity"="pharmacy"](around:5000,{lat},{lon});
          way["amenity"="pharmacy"](around:5000,{lat},{lon});
          relation["amenity"="pharmacy"](around:5000,{lat},{lon});
        );
        out center tags;
        """

    if place_type == "dentist":
        return f"""
        [out:json][timeout:25];
        (
          node["amenity"="dentist"](around:10000,{lat},{lon});
          way["amenity"="dentist"](around:10000,{lat},{lon});
          relation["amenity"="dentist"](around:10000,{lat},{lon});
          node["healthcare"="dentist"](around:10000,{lat},{lon});
          way["healthcare"="dentist"](around:10000,{lat},{lon});
          relation["healthcare"="dentist"](around:10000,{lat},{lon});
        );
        out center tags;
        """

    if place_type == "clinic":
        return f"""
        [out:json][timeout:25];
        (
          node["amenity"="clinic"](around:10000,{lat},{lon});
          way["amenity"="clinic"](around:10000,{lat},{lon});
          relation["amenity"="clinic"](around:10000,{lat},{lon});
        );
        out center tags;
        """

    if place_type == "doctor":
        return f"""
        [out:json][timeout:25];
        (
          node["amenity"="doctors"](around:10000,{lat},{lon});
          way["amenity"="doctors"](around:10000,{lat},{lon});
          relation["amenity"="doctors"](around:10000,{lat},{lon});
          node["healthcare"="doctor"](around:10000,{lat},{lon});
          way["healthcare"="doctor"](around:10000,{lat},{lon});
          relation["healthcare"="doctor"](around:10000,{lat},{lon});
          node["amenity"="clinic"](around:10000,{lat},{lon});
          way["amenity"="clinic"](around:10000,{lat},{lon});
          relation["amenity"="clinic"](around:10000,{lat},{lon});
        );
        out center tags;
        """

    return f"""
    [out:json][timeout:25];
    (
      node["amenity"="hospital"](around:10000,{lat},{lon});
      way["amenity"="hospital"](around:10000,{lat},{lon});
      relation["amenity"="hospital"](around:10000,{lat},{lon});
      node["amenity"="clinic"](around:10000,{lat},{lon});
      way["amenity"="clinic"](around:10000,{lat},{lon});
      relation["amenity"="clinic"](around:10000,{lat},{lon});
      node["amenity"="doctors"](around:10000,{lat},{lon});
      way["amenity"="doctors"](around:10000,{lat},{lon});
      relation["amenity"="doctors"](around:10000,{lat},{lon});
    );
    out center tags;
    """


def matches_specialty(tags, place_type):
    if place_type in ["pharmacy", "dentist", "clinic", "doctor", "hospital"]:
        return True

    searchable_text = " ".join([
        str(tags.get("name", "")),
        str(tags.get("healthcare", "")),
        str(tags.get("healthcare:speciality", "")),
        str(tags.get("description", "")),
        str(tags.get("speciality", "")),
        str(tags.get("medical_specialty", ""))
    ]).lower()

    if place_type == "gynecologist":
        keywords = ["gynaec", "gynec", "obstetric", "women", "maternity"]
        return any(word in searchable_text for word in keywords)

    if place_type == "cardiology":
        keywords = ["cardio", "heart"]
        return any(word in searchable_text for word in keywords)

    if place_type == "dermatologist":
        keywords = ["derma", "skin"]
        return any(word in searchable_text for word in keywords)

    return True


def search_nearby_places(lat, lon, place_type):
    overpass_url = "https://overpass-api.de/api/interpreter"
    query = build_overpass_query(lat, lon, place_type)

    response = requests.get(overpass_url, params={"data": query}, timeout=30)
    data = response.json()

    results = []

    for item in data.get("elements", []):
        tags = item.get("tags", {})

        if not matches_specialty(tags, place_type):
            continue

        item_lat = item.get("lat") or item.get("center", {}).get("lat")
        item_lon = item.get("lon") or item.get("center", {}).get("lon")

        if item_lat is None or item_lon is None:
            continue

        address_parts = [
            tags.get("addr:housename", ""),
            tags.get("addr:housenumber", ""),
            tags.get("addr:street", ""),
            tags.get("addr:suburb", ""),
            tags.get("addr:city", ""),
            tags.get("addr:state", "")
        ]
        address = ", ".join([part for part in address_parts if part.strip()])

        services = []
        if tags.get("emergency") == "yes":
            services.append("Emergency")
        if tags.get("dispensing") == "yes":
            services.append("Medicine dispensing")
        if tags.get("healthcare"):
            services.append(tags.get("healthcare").title())
        if tags.get("healthcare:speciality"):
            services.append(tags.get("healthcare:speciality").title())
        if tags.get("operator"):
            services.append(f"Operator: {tags.get('operator')}")

        results.append({
            "name": tags.get("name", "Unnamed Place"),
            "location": address if address else "Address not available",
            "timings": tags.get("opening_hours", "Timing not available"),
            "rating": "Not available",
            "services": services if services else ["Service details not available"],
            "phone": tags.get("phone", "Phone not available"),
            "distance_km": calculate_distance_km(lat, lon, item_lat, item_lon),
            "lat": item_lat,
            "lon": item_lon
        })

    results.sort(key=lambda x: x["distance_km"])
    return results[:10]


def format_nearby_results(message, lat, lon):
    place_type = detect_place_type(message)
    results = search_nearby_places(lat, lon, place_type)

    if not results:
        return "Sorry, I could not find matching places near you right now."

    title_map = {
        "pharmacy": "pharmacies",
        "dentist": "dentists",
        "gynecologist": "gynecologists",
        "cardiology": "heart hospitals / cardiology centers",
        "dermatologist": "skin specialists",
        "clinic": "clinics",
        "doctor": "doctors",
        "hospital": "hospitals"
    }

    lines = [f"I found these nearby {title_map.get(place_type, 'places')}:"]

    for i, place in enumerate(results[:5], start=1):
        maps_link = f"https://www.google.com/maps?q={place['lat']},{place['lon']}"
        services_text = ", ".join(place["services"])

        lines.append(
            f"{i}. {place['name']}\n"
            f"Location: {place['location']}\n"
            f"Distance: {place['distance_km']} km\n"
            f"Timings: {place['timings']}\n"
            f"Phone: {place['phone']}\n"
            f"Services: {services_text}\n"
            f"Open in Maps: {maps_link}"
        )

    return "\n\n".join(lines)


# -----------------------------
# Main chatbot logic
# -----------------------------
def chatbot_response(message, user_id, lat=None, lon=None):
    msg = message.lower().strip()

    if msg in ["cancel", "stop", "reset", "exit", "clear"]:
        chat_state["mode"] = None
        chat_state["reminder_data"] = {}
        return "Okay, I cancelled the current reminder process."

    if msg in ["hi", "hello", "hey", "hii", "helo"]:
        chat_state["mode"] = None
        chat_state["reminder_data"] = {}
        return (
            "Hello! I am your AI healthcare assistant. I can help with symptoms, medicine reminders, "
            "appointments, nearby hospitals, nearby pharmacies, and doctor searches."
        )

    interrupt_commands = [
        "show appointments",
        "show my appointments",
        "all appointments",
        "my appointments",
        "appointment today",
        "appointments today",
        "any appointment today",
        "do i have any appointments today",
        "appointment tomorrow",
        "appointments tomorrow",
        "do i have appointment tomorrow",
        "next appointment",
        "my next appointment",
        "when is my next appointment",
        "appointment with",
        "appointments with",
        "show all reminders",
        "show reminders",
        "show my reminders",
        "show medicines",
        "my reminders",
        "medicine reminders",
        "today dosage",
        "today dosages",
        "today reminder",
        "today reminders",
        "what are today's dosages",
        "show today's reminders",
        "show today reminders",
        "show today dosage",
        "next dosage",
        "next medicine",
        "what is the next dosage",
        "next dosage for today",
        "next reminder",
        "set reminder",
        "add reminder",
        "create reminder",
        "new reminder",
        "set reminder for",
        "remind me to take",
        "near me",
        "nearby",
        "closest",
        "nearest"
    ]

    if chat_state["mode"] and chat_state["mode"].startswith("awaiting_reminder"):
        if any(command in msg for command in interrupt_commands):
            chat_state["mode"] = None
            chat_state["reminder_data"] = {}
        else:
            return handle_reminder_conversation(message, user_id)

    if is_nearby_search_query(message):
        if lat is None or lon is None:
            return "Please allow location access in the chatbot so I can search nearby places for you."
        return format_nearby_results(message, lat, lon)

    if (
        "today dosage" in msg
        or "today dosages" in msg
        or "today reminder" in msg
        or "today reminders" in msg
        or "what are today's dosages" in msg
        or "show today's reminders" in msg
        or "show today reminders" in msg
        or "show today dosage" in msg
    ):
        return format_today_reminders(user_id)

    if (
        "next dosage" in msg
        or "next medicine" in msg
        or "what is the next dosage" in msg
        or "next dosage for today" in msg
        or "next reminder" in msg
    ):
        return get_next_today_dosage(user_id)

    if (
        "show all reminders" in msg
        or "show reminders" in msg
        or "show my reminders" in msg
        or "show medicines" in msg
        or "my reminders" in msg
        or "medicine reminders" in msg
    ):
        return format_all_reminders(user_id)

    if "set reminder for" in msg or "remind me to take" in msg:
        reminder = parse_reminder_command(message, user_id)
        if reminder:
            return (
                f"Reminder added successfully for {reminder['name']} with dosage {reminder['dosage']} "
                f"on {reminder['date']} at {reminder['time']} with schedule {reminder['schedule']}."
            )

        chat_state["mode"] = "awaiting_reminder_name"
        chat_state["reminder_data"] = {}
        return "Sure. What is the medicine name?"

    if msg in ["set reminder", "add reminder", "create reminder", "new reminder"]:
        chat_state["mode"] = "awaiting_reminder_name"
        chat_state["reminder_data"] = {}
        return "Sure. What is the medicine name?"

    if (
        "show appointments" in msg
        or "show my appointments" in msg
        or "all appointments" in msg
        or "my appointments" in msg
    ):
        return format_all_appointments(user_id)

    if "appointment tomorrow" in msg or "appointments tomorrow" in msg or "do i have appointment tomorrow" in msg:
        return format_tomorrow_appointments(user_id)

    if (
        "appointment today" in msg
        or "appointments today" in msg
        or "any appointment today" in msg
        or "do i have any appointments today" in msg
    ):
        return format_today_appointments(user_id)

    if (
        "next appointment" in msg
        or "my next appointment" in msg
        or "when is my next appointment" in msg
    ):
        return format_next_appointment(user_id)

    if "appointment with" in msg or "appointments with" in msg:
        doctor_name = msg.split("with", 1)[1].strip()
        doctor_name = doctor_name.replace("dr.", "").replace("dr", "").strip()
        if doctor_name:
            return format_appointments_by_doctor(user_id, doctor_name)
        return "Please tell me the doctor's name."

    if is_symptom_query(message):
        return get_ai_symptom_response(message)

    return get_general_ai_response(message)


# -----------------------------
# Auth routes
# -----------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not full_name or not email or not password:
            flash("All fields are required.")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (full_name, email, password)
                VALUES (?, ?, ?)
            """, (full_name, email, hashed_password))
            conn.commit()
            conn.close()

            flash("Registration successful. Please login.")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("Email already exists. Please use another email.")
            return redirect(url_for("register"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["user_name"] = user["full_name"]
            return redirect(url_for("user_dashboard"))

        flash("Invalid email or password.")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM admins WHERE email = ?", (email,))
        admin = cursor.fetchone()
        conn.close()

        if admin and check_password_hash(admin["password"], password):
            session.clear()
            session.permanent = True
            session["admin_id"] = admin["id"]
            session["admin_name"] = admin["full_name"]
            return redirect(url_for("admin_dashboard"))

        flash("Invalid admin email or password.")
        return redirect(url_for("admin_login"))

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, full_name, email, created_at FROM users ORDER BY id DESC")
    users = cursor.fetchall()
    conn.close()
    return render_template("admin_dashboard.html", users=users)


@app.route("/admin/users")
@admin_required
def admin_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, full_name, email, created_at FROM users ORDER BY id DESC")
    users = cursor.fetchall()
    conn.close()
    return render_template("admin_users.html", users=users)


@app.route("/admin/delete_user/<int:user_id>", methods=["DELETE"])
@admin_required
def admin_delete_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM medicine_reminders WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM appointments WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))

    conn.commit()
    conn.close()
    return jsonify({"status": "success"})


@app.route("/admin/appointments")
@admin_required
def admin_appointments():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT appointments.*, users.full_name AS user_name, users.email AS user_email
        FROM appointments
        LEFT JOIN users ON appointments.user_id = users.id
        ORDER BY date ASC, time ASC
    """)
    appointments = cursor.fetchall()
    conn.close()
    return render_template("admin_appointments.html", appointments=appointments)


@app.route("/admin/reminders")
@admin_required
def admin_reminders():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT medicine_reminders.*, users.full_name AS user_name, users.email AS user_email
        FROM medicine_reminders
        LEFT JOIN users ON medicine_reminders.user_id = users.id
        ORDER BY date ASC, time ASC
    """)
    reminders = cursor.fetchall()
    conn.close()

    today = date.today().strftime("%Y-%m-%d")

    return render_template(
        "admin_reminders.html",
        reminders=reminders,
        today=today
    )


@app.route("/admin/alerts")
@admin_required
def admin_alerts():
    today = date.today().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT medicine_reminders.*, users.full_name AS user_name, users.email AS user_email
        FROM medicine_reminders
        LEFT JOIN users ON medicine_reminders.user_id = users.id
        WHERE schedule = 'Once' AND date < ?
        ORDER BY date ASC, time ASC
    """, (today,))
    expired_once = cursor.fetchall()

    cursor.execute("""
        SELECT medicine_reminders.*, users.full_name AS user_name, users.email AS user_email
        FROM medicine_reminders
        LEFT JOIN users ON medicine_reminders.user_id = users.id
        WHERE schedule = 'Daily' AND end_date IS NOT NULL AND end_date < ?
        ORDER BY end_date ASC, time ASC
    """, (today,))
    expired_daily = cursor.fetchall()

    cursor.execute("""
        SELECT appointments.*, users.full_name AS user_name, users.email AS user_email
        FROM appointments
        LEFT JOIN users ON appointments.user_id = users.id
        WHERE date = ? AND time < ?
        ORDER BY time ASC
    """, (today, now_time))
    missed_appointments = cursor.fetchall()

    conn.close()

    return render_template(
        "admin_alerts.html",
        expired_once=expired_once,
        expired_daily=expired_daily,
        missed_appointments=missed_appointments
    )


@app.route("/admin/requests")
@admin_required
def admin_requests():
    demo_requests = [
        {
            "id": 1,
            "name": "Demo User",
            "type": "Support",
            "message": "Need help understanding medicine reminder setup.",
            "status": "Pending"
        },
        {
            "id": 2,
            "name": "Demo User 2",
            "type": "Appointment",
            "message": "Requested reschedule for upcoming appointment.",
            "status": "Open"
        }
    ]
    return render_template("admin_requests.html", requests_list=demo_requests)


# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("user_dashboard"))
    if "admin_id" in session:
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def user_dashboard():
    return render_template("user_dashboard.html")


@app.route("/chatbot")
@login_required
def chatbot_page():
    return render_template("chatbot.html")


@app.route("/medicine-reminder")
@login_required
def medicine_reminder_page():
    return render_template("medicine_reminder.html")


@app.route("/appointments")
@login_required
def appointments_page():
    return render_template("appointments.html")


@app.route("/nearby-pharmacy")
@login_required
def nearby_pharmacy_page():
    return render_template("nearby_pharmacy.html")


@app.route("/nearby-hospital")
@login_required
def nearby_hospital_page():
    return render_template("nearby_hospital.html")


@app.route("/chat", methods=["POST"])
@login_required
def chat():
    data = request.get_json()
    message = data.get("message", "")
    lat = data.get("lat")
    lon = data.get("lon")

    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except (ValueError, TypeError):
        lat = None
        lon = None

    reply = chatbot_response(message, session["user_id"], lat, lon)
    return jsonify({"reply": reply})


@app.route("/get_medicines", methods=["GET"])
@login_required
def get_medicines():
    return jsonify(get_all_medicine_reminders(session["user_id"]))


# -----------------------------
# Reminder CRUD routes
# -----------------------------
@app.route("/add_medicine", methods=["POST"])
@login_required
def add_medicine():
    data = request.get_json()

    reminder = add_medicine_reminder(
        session["user_id"],
        data["name"],
        data["dosage"],
        data["date"],
        data["time"],
        data["schedule"],
        data.get("end_date")
    )

    return jsonify(reminder)


@app.route("/update_medicine", methods=["POST"])
@login_required
def update_medicine():
    data = request.get_json()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE medicine_reminders
        SET name=?, dosage=?, date=?, end_date=?, time=?, schedule=?
        WHERE id=? AND user_id=?
    """, (
        data["name"],
        data["dosage"],
        data["date"],
        data.get("end_date"),
        data["time"],
        data["schedule"],
        data["id"],
        session["user_id"]
    ))

    conn.commit()
    conn.close()

    return jsonify({"status": "success"})


@app.route("/delete_medicine/<int:reminder_id>", methods=["DELETE"])
@login_required
def delete_medicine(reminder_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM medicine_reminders WHERE id=? AND user_id=?",
        (reminder_id, session["user_id"])
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})


# -----------------------------
# Appointment CRUD routes
# -----------------------------
@app.route("/add_appointment", methods=["POST"])
@login_required
def add_appointment_route():
    data = request.get_json()

    appointment = add_appointment(
        session["user_id"],
        data["doctor"],
        data["hospital"],
        data["date"],
        data["time"],
        data["purpose"],
        data["location"]
    )

    return jsonify(appointment)


@app.route("/get_appointments", methods=["GET"])
@login_required
def get_appointments():
    return jsonify(get_all_appointments(session["user_id"]))


@app.route("/update_appointment", methods=["POST"])
@login_required
def update_appointment():
    data = request.get_json()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE appointments
        SET doctor=?, hospital=?, date=?, time=?, purpose=?, location=?
        WHERE id=? AND user_id=?
    """, (
        data["doctor"],
        data["hospital"],
        data["date"],
        data["time"],
        data["purpose"],
        data["location"],
        data["id"],
        session["user_id"]
    ))

    conn.commit()
    conn.close()

    return jsonify({"status": "success"})


@app.route("/delete_appointment/<int:appointment_id>", methods=["DELETE"])
@login_required
def delete_appointment(appointment_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM appointments WHERE id=? AND user_id=?",
        (appointment_id, session["user_id"])
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})


# -----------------------------
# Nearby API routes
# -----------------------------
@app.route("/api/nearby_pharmacy", methods=["POST"])
@login_required
def api_nearby_pharmacy():
    data = request.get_json()
    lat = float(data["lat"])
    lon = float(data["lon"])
    results = search_nearby_places(lat, lon, "pharmacy")
    return jsonify(results)


@app.route("/api/nearby_hospital", methods=["POST"])
@login_required
def api_nearby_hospital():
    data = request.get_json()
    lat = float(data["lat"])
    lon = float(data["lon"])
    results = search_nearby_places(lat, lon, "hospital")
    return jsonify(results)


if __name__ == "__main__":
    init_db()
    init_auth_tables()
    create_default_admin()
    app.run(host="0.0.0.0", port=5000, debug=True)