import os
import asyncio
import aiohttp
import requests
import pandas as pd
import numpy as np
import sqlite3
from datetime import datetime
from scipy.stats import poisson
from understat import Understat
from thefuzz import process

# --- الإعدادات والروابط الأساسية ---
MAJOR_LEAGUES = ["PL", "PD", "SA", "BL1", "FL1"]
UNDERSTAT_LEAGUE = {
    "PL": "EPL", "PD": "La_liga", "SA": "Serie_A",
    "BL1": "Bundesliga", "FL1": "Ligue_1"
}

API_KEY = os.environ.get("FOOTBALL_DATA_TOKEN", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SEASON = 2026
DB_NAME = "football_predictions.db"

def init_db():
    """تهيئة قاعدة البيانات لتخزين التوقعات وتتبع النتائج"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league TEXT,
            match_name TEXT,
            match_date TEXT,
            home_win_pct REAL,
            draw_pct REAL,
            away_win_pct REAL,
            best_score TEXT,
            value_bet TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_prediction(league, data, value_bet_info):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO predictions (league, match_name, match_date, home_win_pct, draw_pct, away_win_pct, best_score, value_bet, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        league, data["Match"], data["Date"], 
        float(data["Home Win %"].replace('%','')), 
        float(data["Draw %"].replace('%','')), 
        float(data["Away Win %"].replace('%','')), 
        data["Best Score"], value_bet_info, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()
    conn.close()

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ خطأ في التيليجرام: {e}")

def get_matches(league_code):
    url = f"https://api.football-data.org/v4/competitions/{league_code}/matches"
    headers = {"X-Auth-Token": API_KEY}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("matches", [])
    except Exception as e:
        print(f"❌ مشكل في الشبكة لـ {league_code}: {e}")
    return []

async def get_understat(league_code):
    league_name = UNDERSTAT_LEAGUE.get(league_code, "EPL")
    async with aiohttp.ClientSession() as session:
        understat = Understat(session)
        try:
            return await understat.get_team_stats(league_name, SEASON)
        except Exception as e:
            print(f"❌ مشكل في Understat لـ {league_code}: {e}")
            return []

def match_team(raw_name, available_teams):
    match, score = process.extractOne(raw_name, available_teams)
    return match if score > 70 else raw_name

async def process_league(league_code):
    print(f"🚀 معالجة دوري {league_code}...")
    matches = get_matches(league_code)
    understat_data = await get_understat(league_code)
    
    if not matches or not understat_data:
        return

    xg_dict = {}
    for team in understat_data:
        t_name = team["title"]
        history = team["history"]
        home_games = [x for x in history if x["h_a"] == "h"]
        away_games = [x for x in history if x["h_a"] == "a"]
        
        h_scored = sum([x["xG"] for x in home_games]) / len(home_games) if home_games else 1.3
        h_conceded = sum([x["xGA"] for x in home_games]) / len(home_games) if home_games else 1.1
        a_scored = sum([x["xG"] for x in away_games]) / len(away_games) if away_games else 1.1
        a_conceded = sum([x["xGA"] for x in away_games]) / len(away_games) if away_games else 1.3
        
        xg_dict[t_name] = {
            "home_xg_scored": h_scored, "home_xg_conceded": h_conceded,
            "away_xg_scored": a_scored, "away_xg_conceded": a_conceded
        }

    available_teams = list(xg_dict.keys())
    all_home_xg = [v["home_xg_scored"] for v in xg_dict.values()]
    all_away_xg = [v["away_xg_scored"] for v in xg_dict.values()]
    avg_home_league = np.mean(all_home_xg) if all_home_xg else 1.5
    avg_away_league = np.mean(all_away_xg) if all_away_xg else 1.2

    telegram_msg = f"⚽ *توقعات دوري {league_code} (Poisson + xG)*\n\n"
    count = 0

    for match in matches:
        if match["status"] != "SCHEDULED":
            continue

        raw_home = match["homeTeam"]["name"]
        raw_away = match["awayTeam"]["name"]
        home_team = match_team(raw_home, available_teams)
        away_team = match_team(raw_away, available_teams)

        if home_team in xg_dict and away_team in xg_dict:
            h = xg_dict[home_team]
            a = xg_dict[away_team]

            h_attack = h["home_xg_scored"] / avg_home_league
            h_defense = h["home_xg_conceded"] / avg_away_league
            a_attack = a["away_xg_scored"] / avg_away_league
            a_defense = a["away_xg_conceded"] / avg_home_league

            lambda_home = h_attack * a_defense * avg_home_league
            lambda_away = a_attack * h_defense * avg_away_league

            max_goals = 5
            home_win_prob, draw_prob, away_win_prob = 0, 0, 0
            best_prob, best_score = 0, ""

            for i in range(max_goals + 1):
                for j in range(max_goals + 1):
                    p = poisson.pmf(i, lambda_home) * poisson.pmf(j, lambda_away)
                    if i > j: home_win_prob += p
                    elif i == j: draw_prob += p
                    else: away_win_prob += p
                    
                    if p > best_prob:
                        best_prob = p
                        best_score = f"{i} - {j}"

            value_info = "None"
            if home_win_prob > 0.60:
                value_info = f"Strong Home Value ({home_win_prob*100:.1f}%)"
            elif away_win_prob > 0.50:
                value_info = f"Strong Away Value ({away_win_prob*100:.1f}%)"

            pred_data = {
                "Match": f"{home_team} vs {away_team}",
                "Date": match["utcDate"][:10],
                "Home Win %": f"{home_win_prob * 100:.1f}%",
                "Draw %": f"{draw_prob * 100:.1f}%",
                "Away Win %": f"{away_win_prob * 100:.1f}%",
                "Best Score": best_score,
                "Confidence": f"{best_prob * 100:.1f}%"
            }

            save_prediction(league_code, pred_data, value_info)

            telegram_msg += (
                f"🏟 *{pred_data['Match']}*\n"
                f"📅 {pred_data['Date']}\n"
                f"📊 1X2: [{pred_data['Home Win %']} | {pred_data['Draw %']} | {pred_data['Away Win %']}]\n"
                f"🎯 Best Score: *{pred_data['Best Score']}* ({pred_data['Confidence']})\n"
                f"💎 Tip: `{value_info}`\n\n"
            )
            count += 1
            if count >= 4:
                break

    if count > 0:
        send_telegram(telegram_msg)

async def main():
    init_db()
    for league in MAJOR_LEAGUES:
        await process_league(league)
        await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main())
