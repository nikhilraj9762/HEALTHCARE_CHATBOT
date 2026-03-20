import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if api_key:
    genai.configure(api_key=api_key)

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
    "seizure",
    "one side weakness",
    "blue lips"
]

def emergency_check(user_text):
    text = user_text.lower()
    for keyword in EMERGENCY_KEYWORDS:
        if keyword in text:
            return (
                "This may be a medical emergency. Please seek immediate medical help or go to the nearest hospital right away. "
                "Do not wait for chatbot advice. This is not a final medical diagnosis."
            )
    return None

def is_symptom_query(user_text):
    text = user_text.lower()
    symptom_words = [
        "pain", "fever", "cough", "cold", "headache", "migraine", "vomiting",
        "diarrhea", "stomach", "weakness", "fatigue", "dizziness", "breathing",
        "chest", "nausea", "throat", "body pain", "sneezing", "infection",
        "i am sick", "not feeling well", "feeling unwell", "feeling sick",
        "symptom", "ill", "sore throat", "runny nose"
    ]
    return any(word in text for word in symptom_words)

def get_ai_symptom_response(user_text):
    emergency = emergency_check(user_text)
    if emergency:
        return emergency

    if not api_key:
        return (
            "AI symptom service is not configured yet. Please add your Gemini API key. "
            "This is not a final medical diagnosis."
        )

    prompt = f"""
You are a cautious healthcare support assistant for elderly users.

Rules:
- Understand natural symptom descriptions.
- Reply in simple language.
- Give likely possibilities only, never final diagnosis.
- Give simple safe home-care suggestions first if appropriate.
- Ask 1 to 3 useful follow-up questions if needed.
- Tell the user to see a doctor if symptoms continue, worsen, or are severe.
- If symptoms sound urgent, advise immediate medical care.
- Never prescribe prescription drugs.
- Keep the answer easy to understand.
- Always end with: This is not a final medical diagnosis.

User message: {user_text}
"""

    try:
        model = genai.GenerativeModel("gemini-3-flash-preview")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"AI symptom error: {str(e)}"

def get_general_ai_response(user_text):
    if not api_key:
        return "AI service is not configured yet."

    prompt = f"""
You are a helpful healthcare assistant chatbot.

Rules:
- Reply in simple and clear language.
- Help with general health questions, elderly care questions, medicine basics, wellness tips, and common user questions.
- Never give a final medical diagnosis.
- Never prescribe prescription medicines.
- If the question is medical and serious, advise consulting a doctor.
- Keep the answer short and easy to understand.

User message: {user_text}
"""

    try:
        model = genai.GenerativeModel("gemini-3-flash-preview")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"AI error: {str(e)}"