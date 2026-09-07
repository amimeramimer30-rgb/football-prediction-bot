import os
import requests
from datetime import datetime
from scipy.stats import poisson

API_KEY = os.environ.get("FOOTBALL_DATA_TOKEN", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Telegram credentials missing")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        print(f"Telegram Response: {resp.text}")
    except Exception as e:
        print(f"❌ خطأ في التيليجرام: {e}")

def get_matches():
    # جلب المباريات المجدولة القادمة
    url = "https://api.football-data.org/v4/matches?status=SCHEDULED"
    headers = {"X-Auth-Token": API_KEY}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        print(f"API Status Code: {resp.status_code}")
        if resp.status_code == 200:
            return resp.json().get("matches", [])
        else:
            print(f"API Error Response: {resp.text}")
    except Exception as e:
        print(f"❌ مشكل في الشبكة: {e}")
    return []

def main():
    print("🚀 بدء تشغيل السكريبت...")
    matches = get_matches()
    
    if not matches:
        send_telegram("⚠️ لم يتم العثور على مباريات مجدولة حالياً عبر الـ API.")
        return

    telegram_msg = "⚽ *توقعات المباريات القادمة (Pro Predictor)*:\n\n"
    count = 0

    for match in matches[:5]: # أول 5 ماتشات
        home_team = match['homeTeam']['name']
        away_team = match['awayTeam']['name']
        competition = match['competition']['name']
        match_date = match['utcDate'][:10]

        # تقدير مبسط لـ Poisson للتجربة الفورية
        home_lambda = 1.4
        away_lambda = 1.1

        home_win_prob, draw_prob, away_win_prob = 0, 0, 0
        best_prob, best_score = 0, ""

        for i in range(4):
            for j in range(4):
                p = poisson.pmf(i, home_lambda) * poisson.pmf(j, away_lambda)
                if i > j: home_win_prob += p
                elif i == j: draw_prob += p
                else: away_win_prob += p
                
                if p > best_prob:
                    best_prob = p
                    best_score = f"{i} - {j}"

        telegram_msg += (
            f"🏆 *{competition}*\n"
            f"🏟 {home_team} vs {away_team}\n"
            f"📅 {match_date}\n"
            f"📊 1X2: [{home_win_prob*100:.1f}% | {draw_prob*100:.1f}% | {away_win_prob*100:.1f}%]\n"
            f"🎯 Best Score: *{best_score}* ({best_prob*100:.1f}%)\n\n"
        )
        count += 1

    if count > 0:
        send_telegram(telegram_msg)
    else:
        send_telegram("⚠️ لا توجد مباريات مطابقة للإرسال.")

if __name__ == "__main__":
    main()
