import pandas as pd
import os
import re
import tkinter as tk
from tkinter import filedialog
import ssl

# --- CHECK FOR NLTK ---
try:
    import nltk
    from nltk.sentiment.vader import SentimentIntensityAnalyzer
except ImportError:
    print("Please install nltk: pip install nltk")
    exit()

# --- SETUP (Ignore SSL errors) ---
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

try:
    nltk.data.find('sentiment/vader_lexicon.zip')
except LookupError:
    nltk.download('vader_lexicon', quiet=True)

# Initialize Analyzer
sia = SentimentIntensityAnalyzer()

# ---------------------------------------------------------
# 🇻🇳 VIETNAMESE DICTIONARY (The Heart of the Script) 🇻🇳
# ---------------------------------------------------------
# Scores: -4 (Terrible) to +4 (Amazing)
VN_SCORES = {
    # --- POSITIVE NEGATIONS (Good things) ---
    "không ồn": 3.0, "ko ồn": 3.0,
    "không hôi": 2.5, "ko hôi": 2.5,
    "không dơ": 2.5, "ko dơ": 2.5,
    "không bụi": 2.5,
    "không tệ": 2.0, "ko tệ": 2.0,
    "không có gián": 3.0, "ko có gián": 3.0,
    "không vấn đề": 2.0, "ko vấn đề": 2.0,
    "không phàn nàn": 2.5, "ko phàn nàn": 2.5,
    "không khó chịu": 3.0, "ko khó chịu": 3.0,
    "không ồn ào": 3.0, "ko ồn ào": 3.0,
    "không mất nước": 3.0, "ko mất nước": 3.0,
    "không mất điện": 3.0,  "ko mất điện": 3.0,
    "không chán": 2.5,  "ko chán": 2.5,
    "không đắt": 2.0, "ko đắt": 2.0,
    "không hư": 3.0, "ko hư": 3.0,
    "không lỗi": 3.0, "ko lỗi": 3.0,
    "không rác": 2.5,   "ko rác": 2.5,  
    "Không mốc": 3.0, "ko mốc": 3.0,
    "không ẩm mốc": 3.5, "ko ẩm mốc": 3.5,
    "không cũ": 2.5, "ko cũ": 2.5,
    "không hỏng": 3.0, "ko hỏng": 3.0,
    "không dột": 3.0, "ko dột": 3.0,
    "không gián": 3.5, "ko gián": 3.5,
    "không kiến": 3.5, "ko kiến": 3.5,
    "không chuột": 3.5, "ko chuột": 3.5,
    "không rệp": 3.5, "ko rệp": 3.5,
    "Không mùi": 2.5, "ko mùi": 2.5,
    
    
    "quá đã": 4.0,           # Slang for "awesome"
    "nhức nách": 4.0,        # Slang for "so good it hurts"
    "món ăn ngon": 3.0,      # Specific praise
    "phở ngon": 3.5,         # Specific food
    "chủ trọ hãm": -4.0,     # Slang for "bad landlord/host"
    "wifi yếu": -3.0,        # Tech complaint
    "chập chờn": -2.5,       # Unstable (usually wifi/water)

    # --- NEGATIVE PHRASES (Bad things) ---
    "không sạch": -4.0, "ko sạch": -4.0, "chưa sạch": -3.5,
    "không có nước": -4.0, "cúp nước": -4.0,
    "không lạnh": -3.0, "máy lạnh hư": -4.0,
    "thái độ": -4.0, "lồi lõm": -4.0, # Slang for bad attitude
    "khó chịu": -3.0, "bất lịch sự": -3.5,
    "không thân thiện": -3.0, "ko thân thiện": -3.0,
    "không hỗ trợ": -3.5, "ko hỗ trợ": -3.5,
    "cách âm kém": -3.5, "ồn ào": -3.5,
    "dơ bẩn": -4.0, "như hạch": -4.0, # Slang
    "xuống cấp": -3.0, "cũ kỹ": -2.5,
    "đắt": -2.0, "mắc": -2.0, "chém giá": -4.0,
    "thất vọng": -3.5, "tệ hại": -4.0, "kinh khủng": -4.0,
    
    # --- POSITIVE WORDS ---
    "sạch": 3.0, "sạch sẽ": 3.5, "thoáng": 2.5, "thơm": 3.0,
    "ngon": 3.0, "tốt": 2.5, "tuyệt": 4.0, "tuyệt vời": 4.5,
    "xuất sắc": 4.5, "đẹp": 3.0, "xinh": 2.5,
    "nhiệt tình": 3.5, "thân thiện": 3.5, "dễ thương": 3.0, "vui vẻ": 3.0,
    "chu đáo": 3.5, "hỗ trợ": 2.5, "chuyên nghiệp": 3.5,
    "tiện nghi": 3.0, "đầy đủ": 2.5, "êm": 3.0, "ấm": 2.5,
    "yên tĩnh": 3.5, "gần trung tâm": 3.0, "tiện lợi": 3.0,
    "giá rẻ": 2.5, "hợp lý": 2.5, "đáng tiền": 3.5, "ok": 2.0, "ổn": 2.0 , "rộng": 2.5, "thoải mái": 3.0, 
}

# --- 1. OVERRIDE ENGLISH DICTIONARY ---
# We clear the English words and load strictly Vietnamese words
sia.lexicon.clear()
# Create "glued" versions (replace space with underscore)
vn_updates = {k.replace(" ", "_"): v for k, v in VN_SCORES.items()}
sia.lexicon.update(vn_updates)

# --- 2. STRICT VIETNAMESE NEGATIVES (Kill Switch) ---
# If these appear, the score is forced negative
STRICT_NEGATIVES_VN = {
    "dơ", "bẩn", "hôi", "thối", "mốc", "gián", "kiến", "chuột", "rệp",
    "ồn", "hư", "hỏng", "dột", "cũ", "nát",
    "thái_độ", "lồi_lõm", "bất_lịch_sự", "thô_lỗ", "cọc_cằn",
    "tệ", "kém", "chán", "thất_vọng", "lừa_đảo", "treo_đầu_dê"
    "trộm",      # Theft
    "cắp",       # Stealing
    "thấm",      # Leaking/Water damage
    "mốc_meo",   # Moldy (Multi-word must use underscore here if not in VN_SCORES)
}

# Helper set for fast lookup
NEGATIVE_TOKENS = {k.replace(" ", "_") for k, v in VN_SCORES.items() if v < 0}
NEGATIVE_TOKENS.update(STRICT_NEGATIVES_VN)

# --- CONFIGURATION ---
# IMPORTANT: Change this to your Vietnamese CSV file name!
INPUT_FILE = "20k vietnamese.csv" 
OUTPUT_FILE = "20k vietnamese.csv"

# Vietnamese Topics
TOPIC_KEYWORDS_VN = {
    "Staff_Attitude": ["nhân viên", "nv", "lễ tân", "bảo vệ", "chủ", "thái độ", "phục vụ", "nhiệt tình", "thân thiện", "dễ thương", "cọc", "khó chịu"],
    "Cleanliness": ["sạch", "dơ", "bẩn", "hôi", "mùi", "rác", "bụi", "mốc", "gián", "kiến", "khăn", "ga", "giường", "vệ sinh"],
    "Room_Comfort": ["phòng", "giường", "nệm", "gối", "máy lạnh", "điều hòa", "nóng lạnh", "nước", "view", "cửa sổ", "ồn", "cách âm", "rộng", "chật", "bí"],
    "Location": ["vị trí", "địa điểm", "trung tâm", "gần", "xa", "chợ", "biển", "đi lại", "hẻm", "ngõ", "tìm", "hẻm xe hơi", "mặt tiền"  ],
    "Price": ["giá", "tiền", "đắt", "mắc", "rẻ", "hợp lý", "tương xứng", "bình dân"],
    "Facilities": ["wifi", "mạng", "thang máy", "hồ bơi", "ăn sáng", "buffet", "đỗ xe", "gửi xe", "sảnh","bún bò", "phở", "cà phê" ]

}

def preprocess_text(text):
    if not isinstance(text, str): return ""
    text = text.lower()
    # Sort phrases by length to match "không sạch" before "sạch"
    sorted_phrases = sorted(VN_SCORES.keys(), key=len, reverse=True)
    for phrase in sorted_phrases:
        if phrase in text:
            glued_phrase = phrase.replace(" ", "_")
            text = text.replace(phrase, glued_phrase)
    return text

def get_sentiment_score(text_segment):
    scores = sia.polarity_scores(text_segment)
    compound = scores['compound']
    
    # Strict Negative Logic for Vietnamese
    has_strict_negative = False
    words = text_segment.split()
    for word in words:
        clean_word = word.strip(".,!?;:")
        if clean_word in STRICT_NEGATIVES_VN or clean_word in NEGATIVE_TOKENS:
            # Safety: If it's a positive negation (like "không_ồn"), ignore strict rule
            if clean_word in sia.lexicon and sia.lexicon[clean_word] > 0:
                continue
            has_strict_negative = True
            break
            
    if has_strict_negative:
        if compound > -0.2: compound = -0.4
    
    if compound == 0: return 0
    sign = 1 if compound > 0 else -1
    abs_score = abs(compound)
    boosted = abs_score ** 0.5 
    final_score = boosted * 10 * sign
    return round(final_score)

def analyze_review_aspects(text):
    if not isinstance(text, str): return {}
    text = preprocess_text(text)
    
    # Vietnamese sentence splitters (added "nhưng" = but)
    segments = re.split(r'[.!?,;]|\bnhưng\b|\btuy_nhiên\b|\bmà\b', text)
    
    scores = {topic: [] for topic in TOPIC_KEYWORDS_VN}
    
    for segment in segments:
        if len(segment.strip()) < 2: continue
        segment_score = get_sentiment_score(segment)
        
        for topic, keywords in TOPIC_KEYWORDS_VN.items():
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
        print(f"\n[INFO] Could not find '{file_path}'. Searching...")
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            file_path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
            root.destroy()
            if not file_path: return
        except: return

    print(f"Loading Vietnamese data from: {file_path}")
    
    try:
        df = pd.read_csv(file_path, encoding='utf-8-sig', on_bad_lines='skip')

        # Auto-Repair Overflow Columns
        overflow_cols = [col for col in df.columns if str(col).startswith("Unnamed")]
        target_column = 'comment_text'
        
        if target_column not in df.columns:
            if 'Comment' in df.columns: target_column = 'Comment'
            else: 
                print("[ERROR] No comment column found.")
                return

        if overflow_cols:
            print(f"-> Repairing split sentences...")
            df[overflow_cols] = df[overflow_cols].fillna('')
            for col in overflow_cols:
                df[target_column] = df[target_column].astype(str) + " " + df[col].astype(str)
            df.drop(columns=overflow_cols, inplace=True)
        
        print(f"Analyzing Vietnamese sentiment...")
        
        score_data = df[target_column].apply(analyze_review_aspects).apply(pd.Series)
        result_df = pd.concat([df, score_data], axis=1)

        result_df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
        print(f"Done! Saved to {OUTPUT_FILE}")
        
        print("\n--- Preview (Vietnamese) ---")
        preview_cols = [target_column] + [col for col in result_df.columns if 'Score_' in col]
        print(result_df[preview_cols].head())

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()