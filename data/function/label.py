import pandas as pd
import os
import re
import tkinter as tk
from tkinter import filedialog
import ssl
import math


INPUT_FILE = "50k other.csv" 
OUTPUT_FILE = "50k other.csv"


# --- CHECK FOR NLTK LIBRARY ---
try:
    import nltk
    from nltk.sentiment.vader import SentimentIntensityAnalyzer
except ImportError:
    print("\n[ERROR] Missing the NLTK library.")
    print("Please run this command in your terminal/command prompt:")
    print("pip install nltk")
    exit()

# --- SETUP NLTK ---
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

try:
    nltk.data.find('sentiment/vader_lexicon.zip')
except LookupError:
    print("Downloading sentiment dictionary...")
    nltk.download('vader_lexicon', quiet=True)

sia = SentimentIntensityAnalyzer()

# --- 🔧 SMART PHRASE DICTIONARY (UPDATED) 🔧 ---
PHRASE_SCORES = {
    # --- POSITIVE NEGATIONS (The Fix for "No Bugs") ---
    # These must be first/longer so they override the bad words
    "no bugs": 2.5,
    "no cockroach": 2.5,
    "no insects": 2.5,
    "no ants": 2.5,
    "no mosquitoes": 2.5,
    "no noise": 3.0,
    "no smell": 2.0,
    "no odor": 2.0,
    "no problem": 2.5,
    "no issues": 2.5,
    "not noisy": 3.0,
    "not dirty": 2.0,
    "didn't smell": 2.0,
    "doesn't smell": 2.0,

    # Service Issues
    "not provide": -3.0, "did not provide": -3.0, "no help": -3.0, "not helpful": -3.0,
    "not friendly": -3.0, "bad attitude": -4.0, "unprofessional": -3.5, "no greeting": -2.0,
    
    # Facility/Room Issues
    "no water": -3.0, "no hot water": -4.0, "cold water": -3.0, "not working": -3.0,
    "broken": -3.0, "leaking": -3.0, "no towel": -2.5, "no toilet paper": -3.0,
    "hard bed": -2.5, "uncomfortable": -3.0, "noisy": -3.5, "loud": -3.5, "thin walls": -3.0,
    
    # Cleanliness (If "no bugs" is not found, these will catch the bad stuff)
    "not clean": -4.0, "didn't clean": -4.0, "dirty": -3.5, "filthy": -4.0, "smell": -3.0,
    "mold": -3.5, "cockroach": -4.0, "bugs": -3.5, "hair on": -3.0, "stained": -3.0, "ants": -3.0,
    
    # Idioms
    "cost an arm and a leg": -4.0, "rip off": -4.0, "below average": -3.0,
    "steer clear": -4.0, "game changer": 4.0, "hidden gem": 4.0
}

# 1. Update VADER dictionary with "glued" versions
vader_updates = {k.replace(" ", "_"): v for k, v in PHRASE_SCORES.items()}
sia.lexicon.update(vader_updates)

# STRICT NEGATIVE WORDS
STRICT_NEGATIVES = {
    "dirty", "filthy", "rude", "unfriendly", "loud", "noisy", "broken", 
    "smell", "stink", "mold", "bugs", "cockroach", "ants", "stain", "stained",
    "gross", "disgusting", "horrible", "terrible", "awful", "bad", "worst",
    "poor", "disappointing", "uncomfortable", "hard", "old", "worn",
    "not_provide", "did_not_provide", "no_hot_water", "no_water", "not_clean"
}

NEGATIVE_TOKENS = {k.replace(" ", "_") for k, v in PHRASE_SCORES.items() if v < 0}
NEGATIVE_TOKENS.update(STRICT_NEGATIVES)


TOPIC_KEYWORDS = {
    "Staff_Attitude": ["staff", "attitude", "reception", "host", "service", "friendly", "rude", "helpful", "manager", "guard", "check-in", "welcoming", "polite", "unpleasant", "support", "personnel", "security", "bellboy", "ignore", "lazy"],
    "Cleanliness": ["clean", "dirty", "smell", "dust", "mold", "stain", "hygiene", "messy", "tidy", "bug", "insect", "cockroach", "rat", "hair", "filthy", "spotted", "trash", "garbage", "ants", "mosquito", "sheet", "towel"],
    "Room_Comfort": ["room", "bed", "bathroom", "shower", "ac", "air con", "conditioner", "view", "window", "sleep", "noise", "pillow", "comfortable", "spacious", "small", "tiny", "huge", "soft", "hard", "furniture", "water", "broken", "leak", "sound", "quiet", "dark"],
    "Location": ["location", "center", "far", "close", "near", "district", "walk", "airport", "grab", "taxi", "convenient", "traffic", "accessible", "alley", "remote", "market", "restaurants"],
    "Price": ["price", "value", "expensive", "cheap", "worth", "money", "cost", "budget", "deal", "affordable", "overpriced", "bill", "deposit"],
    "Facilities": ["pool", "gym", "wifi", "internet", "elevator", "lift", "breakfast", "food", "parking", "lobby", "amenities", "fridge", "buffet"]
}

def preprocess_text(text):
    if not isinstance(text, str): return ""
    text = text.lower()
    # Sort by length DESC so "no bugs" (7 chars) is handled BEFORE "bugs" (4 chars)
    sorted_phrases = sorted(PHRASE_SCORES.keys(), key=len, reverse=True)
    for phrase in sorted_phrases:
        if phrase in text:
            glued_phrase = phrase.replace(" ", "_")
            text = text.replace(phrase, glued_phrase)
    return text

def get_sentiment_score(text_segment):
    scores = sia.polarity_scores(text_segment)
    compound = scores['compound']
    
    # "Smart" Strict Negative Check
    # We only trigger strict negative if the word matches EXACTLY and isn't part of a positive phrase
    # (Since we already glued "no_bugs", the word "bugs" won't appear alone!)
    has_strict_negative = False
    words = text_segment.split()
    for word in words:
        clean_word = word.strip(".,!?;:")
        if clean_word in STRICT_NEGATIVES or clean_word in NEGATIVE_TOKENS:
            # SAFETY CHECK: If the token score is actually positive (like "no_bugs"), ignore the strict rule
            if clean_word in sia.lexicon and sia.lexicon[clean_word] > 0:
                continue 
            has_strict_negative = True
            break
            
    if has_strict_negative:
        if compound > -0.2:
            compound = -0.4 
    
    if compound == 0: return 0
    sign = 1 if compound > 0 else -1
    abs_score = abs(compound)
    boosted = abs_score ** 0.5 
    final_score = boosted * 10 * sign
    return round(final_score)

def analyze_review_aspects(text):
    if not isinstance(text, str): return {}
    text = preprocess_text(text)
    scores = {topic: [] for topic in TOPIC_KEYWORDS}
    segments = re.split(r'[.!?,;]|\bbut\b|\bhowever\b|\balthough\b|\band\b', text)
    
    for segment in segments:
        if len(segment.strip()) < 2: continue
        segment_score = get_sentiment_score(segment)
        for topic, keywords in TOPIC_KEYWORDS.items():
            if any(word in segment for word in keywords):
                scores[topic].append(segment_score)
    
    final_scores = {}
    for topic, val_list in scores.items():
        if val_list:
            avg = sum(val_list) / len(val_list)
            final_scores[f"Score_{topic}"] = round(avg)
        else:
            final_scores[f"Score_{topic}"] = None 
    return final_scores

def main():
    file_path = INPUT_FILE
    
    if not os.path.exists(file_path):
        print(f"\n[INFO] Could not find '{file_path}' automatically.")
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            file_path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
            root.destroy()
            if not file_path: return
        except: return

    print(f"Loading data from: {file_path}")
    
    try:
        df = pd.read_csv(file_path, encoding='utf-8-sig', on_bad_lines='skip')

        # --- REPAIR COLUMNS (Same as before) ---
        overflow_cols = [col for col in df.columns if str(col).startswith("Unnamed")]
        target_column = 'comment_text'
        if target_column not in df.columns:
            if 'Comment' in df.columns: target_column = 'Comment'
            elif 'Review' in df.columns: target_column = 'Review'
            else: return

        if overflow_cols:
            print(f"-> Detected overflow columns. Repairing...")
            df[overflow_cols] = df[overflow_cols].fillna('')
            for col in overflow_cols:
                df[target_column] = df[target_column].astype(str) + ", " + df[col].astype(str)
            df.drop(columns=overflow_cols, inplace=True)
            df[target_column] = df[target_column].str.strip(", ")
        
        print(f"Analyzing sentiments in column: '{target_column}'...")
        
        score_data = df[target_column].apply(analyze_review_aspects).apply(pd.Series)
        result_df = pd.concat([df, score_data], axis=1)

        result_df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
        print(f"Done! Saved to {OUTPUT_FILE}")
        
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()