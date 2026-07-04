import os

BLACKLIST_FILE = "blacklist.txt"

def load_blacklist():
    if not os.path.exists(BLACKLIST_FILE):
        return set()
    blacklist = set()
    with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                blacklist.add(line.lower())
    return blacklist

def save_blacklist(blacklist_set):
    with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
        f.write("# Add one song title, URL keyword, or video ID per line to blacklist them from playing\n")
        for item in sorted(blacklist_set):
            f.write(f"{item}\n")

# Load dynamically on import
blacklist_set = load_blacklist()

def is_blacklisted(title, url, video_id=None):
    title_lower = title.lower()
    url_lower = url.lower()
    for item in blacklist_set:
        if item in title_lower or item in url_lower:
            return True
        if video_id and item == video_id.lower():
            return True
    return False
