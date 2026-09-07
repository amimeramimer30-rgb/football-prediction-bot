import os
import requests
from scipy.stats import poisson

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FOOTBALL_DATA_API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    response = requests.post(url, json=payload)
    print("Telegram response status:", response.status_code)

def main():
    if not FOOTBALL_DATA_API_KEY:
        print("Football Data API Key missing.")
        return
    
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    url = "https://api.football-data.org/v4/matches?status=SCHEDULED"
    
    print("Fetching scheduled matches...")
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Error fetching matches: {response.status_code}, {response.text}")
        return
        
    data = response.json()
    matches = data.get("matches", [])
    
    if not matches:
        send_telegram_message("⚽ لا توجد مباريات مجدولة حالياً.")
        return
        
    message = "📊 *توقعات المباريات القادمة (Poisson Model):*\n\n"
    
    # تاخد أول 8 ماتشات باش الرسالة ما تكونش طويلة بزاف فتيليجرام
    for match in matches[:8]:
        home = match['homeTeam']['name']
        away = match['awayTeam']['name']
        competition = match['competition']['name']
        utc_date = match['utcDate']
        
        # حساب احتمالات بواسون (باستخدام معدلات افتراضية ثابتة أو متوسطات)
        lambda_home = 1.4
        lambda_away = 1.1
        
        prob_home = 0
        prob_draw = 0
        prob_away = 0
        
        for h in range(6):
            for a in range(6):
                p = poisson.pmf(h, lambda_home) * poisson.pmf(a, lambda_away)
                if h > a:
                    prob_home += p
                elif h == a:
                    prob_draw += p
                else:
                    prob_away += p
        
        message += f"🏆 *{competition}*\n"
        message += f"⚔️ {home} vs {away}\n"
        message += f"🕒 {utc_date}\n"
        message += f"📈 🏠 {int(prob_home*100)}% | 🤝 {int(prob_draw*100)}% | ✈️ {int(prob_away*100)}%\n\n"
        
    send_telegram_message(message)

if __name__ == "__main__":
    main()
