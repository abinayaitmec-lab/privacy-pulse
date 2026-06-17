import os, re, json, requests, cloudscraper, traceback
from urllib.parse import urlparse
from flask import Flask, render_template, request, jsonify
from bs4 import BeautifulSoup
from html2text import HTML2Text
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

@app.after_request
def add_cors(r):
    r.headers["Access-Control-Allow-Origin"] = "*"
    r.headers["Access-Control-Allow-Headers"] = "*"
    r.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return r

scraper = cloudscraper.create_scraper()
h = HTML2Text()
h.ignore_links = True
h.ignore_images = True
h.ignore_emphasis = True
h.body_width = 0
h.ignore_anchors = True

GROQ_KEYS = [os.getenv("GROQ_API_KEY_1"), os.getenv("GROQ_API_KEY_2")]
GROQ_KEYS = [k for k in GROQ_KEYS if k]

def groq_complete(prompt):
    for key in GROQ_KEYS:
        try:
            client = Groq(api_key=key)
            return client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000
            ).choices[0].message.content
        except Exception:
            continue
    return None

PRIVACY_PATHS = [
    "/privacy",
    "/privacy-policy",
    "/privacy.html",
    "/privacy-policy.html",
    "/legal/privacy",
    "/legal/privacy-policy",
    "/policies/privacy-policy",
    "/en-US/privacy/privacy-policy",
    "/privacy-notice",
    "/data-privacy",
    "/privacy-policy/",
    "/legal/privacy-policy.html",
    "/pages/privacy-policy",
    "/about/privacy",
    "/corporate/privacy",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}

def extract_domain(raw_url):
    if not raw_url.startswith("http"):
        raw_url = "https://" + raw_url
    parsed = urlparse(raw_url)
    domain = parsed.netloc.lower()
    return domain.replace("www.", "")

def find_page(url, paths):
    if any(url.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
        raise ValueError("That's an image file, not a website. Please enter a normal URL like example.com")
    base_m = re.match(r"(https?://[^/]+)", url)
    if not base_m:
        return None
    base = base_m.group(1)

    # Strategy A: try GET each candidate URL directly
    for path in paths:
        full = base + path
        try:
            r = scraper.get(full, timeout=8, headers=HEADERS, allow_redirects=True)
            if r.status_code < 400:
                ctype = r.headers.get("Content-Type", "")
                if "text/html" in ctype or "text/plain" in ctype:
                    return full
        except requests.RequestException:
            continue

    # Strategy B: fetch homepage, search for privacy link
    try:
        found = scraper.get(url, timeout=10, headers=HEADERS, allow_redirects=True)
        if found.status_code < 400:
            ctype = found.headers.get("Content-Type", "")
            if ctype.startswith("image/"):
                raise ValueError("That link points to an image, not a webpage. Please enter a website URL.")
            soup = BeautifulSoup(found.text, "html.parser")
            for link in soup.find_all("a", href=True):
                text = link.get_text(strip=True).lower()
                href = link["href"].lower()
                if any(kw in text or kw in href for kw in ["privacy", "terms"]):
                    if href.startswith("http"):
                        return href
                    return base + (href if href.startswith("/") else "/" + href)
    except requests.RequestException:
        pass

    return None

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico")

# Curated scores for sites where live scraping commonly fails
KNOWN_SITES = {
    "instagram.com": {
        "site_name": "Instagram",
        "overall_score": 3,
        "grade": "D",
        "verdict": "Collects extensive personal data with third-party sharing.",
        "categories": {
            "data_collection": {"score": 1, "explanation": "Collects almost everything: photos, location, contacts, messages"},
            "data_sharing": {"score": 2, "explanation": "Shares broadly with Meta's ecosystem and third-party partners"},
            "user_rights": {"score": 5, "explanation": "Some control over data, but complex opt-out process"},
            "tracking": {"score": 2, "explanation": "Heavy tracking via pixels, cookies, and cross-site data"},
            "clarity": {"score": 5, "explanation": "Policy is long but moderately readable"}
        },
        "red_flags": ["Owned by Meta with cross-app data merging", "Shares data with third-party advertisers", "Tracks activity across other websites"],
        "data_collected": ["Profile info and photos", "Location data", "Contacts and device info", "Messages and content", "Browsing activity via Meta Pixel"]
    },
    "tiktok.com": {
        "site_name": "TikTok",
        "overall_score": 2,
        "grade": "F",
        "verdict": "Known for extensive data collection and data transfer concerns.",
        "categories": {
            "data_collection": {"score": 1, "explanation": "Collects vast amounts of personal and behavioral data"},
            "data_sharing": {"score": 2, "explanation": "Shares data with parent company ByteDance and third parties"},
            "user_rights": {"score": 3, "explanation": "Limited rights to access and delete data"},
            "tracking": {"score": 1, "explanation": "Aggressive tracking, keystroke patterns, and device fingerprinting"},
            "clarity": {"score": 3, "explanation": "Policy is vague about data use and international transfer"}
        },
        "red_flags": ["Data accessible to ByteDance (Chinese parent company)", "Collects keystroke patterns and biometric data", "Vague about data deletion process"],
        "data_collected": ["Profile information", "Device and network data", "Keystroke patterns and biometrics", "Content and messages", "Location data"]
    },
    "x.com": {
        "site_name": "X (Twitter)",
        "overall_score": 4,
        "grade": "D",
        "verdict": "Collects significant data, recently changed data-sharing policies.",
        "categories": {
            "data_collection": {"score": 3, "explanation": "Collects posts, likes, device info, and browsing data"},
            "data_sharing": {"score": 3, "explanation": "Shares data with third-party partners and AI training partners"},
            "user_rights": {"score": 6, "explanation": "Some control over data visibility and account deletion"},
            "tracking": {"score": 3, "explanation": "Tracks interests, engagement, and cross-site activity"},
            "clarity": {"score": 5, "explanation": "Policy has been updated recently and is somewhat readable"}
        },
        "red_flags": ["Recently changed policy to allow AI training on user data", "Shares data with third-party partners", "Tracks user activity across the web"],
        "data_collected": ["Posts and engagement data", "Device and browser info", "Location data", "Ads interaction data"]
    },
    "linkedin.com": {
        "site_name": "LinkedIn",
        "overall_score": 5,
        "grade": "C",
        "verdict": "Collects professional data but provides reasonable controls.",
        "categories": {
            "data_collection": {"score": 4, "explanation": "Collects profile data, messages, browsing activity, and device info"},
            "data_sharing": {"score": 5, "explanation": "Shares with Microsoft ecosystem and advertisers"},
            "user_rights": {"score": 7, "explanation": "Good data access and export options"},
            "tracking": {"score": 4, "explanation": "Tracks job searches, profile views, and ad interactions"},
            "clarity": {"score": 7, "explanation": "Policy is detailed and organized into clear sections"}
        },
        "red_flags": ["Microsoft data sharing across services", "Tracks job-seeking behavior for advertising", "Profile data visible to recruiters and advertisers"],
        "data_collected": ["Professional profile data", "Messages and connections", "Job search activity", "Device and usage data"]
    },
    "netflix.com": {
        "site_name": "Netflix",
        "overall_score": 7,
        "grade": "B",
        "verdict": "Collects viewing data but has strong security practices.",
        "categories": {
            "data_collection": {"score": 5, "explanation": "Collects viewing history, device info, and payment details"},
            "data_sharing": {"score": 7, "explanation": "Limited third-party sharing, primarily with service providers"},
            "user_rights": {"score": 8, "explanation": "Good account controls and data download options"},
            "tracking": {"score": 6, "explanation": "Tracks viewing for recommendations, limited cross-site tracking"},
            "clarity": {"score": 8, "explanation": "Clear and readable policy with section summaries"}
        },
        "red_flags": ["Collects viewing history and recommendations data", "Shares anonymized data with content partners"],
        "data_collected": ["Account and payment info", "Viewing history and preferences", "Device and connection info"]
    },
    "amazon.in": {
        "site_name": "Amazon India",
        "overall_score": 4,
        "grade": "D",
        "verdict": "Tracks browsing and purchase history heavily for ad targeting.",
        "categories": {
            "data_collection": {"score": 3, "explanation": "Collects purchase history, browsing activity, device info, and payment details"},
            "data_sharing": {"score": 4, "explanation": "Shares with third-party sellers and advertising partners"},
            "user_rights": {"score": 6, "explanation": "Some control over data, but opt-out process is layered"},
            "tracking": {"score": 3, "explanation": "Heavy tracking via cookies, pixels, and cross-site data collection"},
            "clarity": {"score": 5, "explanation": "Policy is detailed but dense and hard to navigate"}
        },
        "red_flags": ["Tracks browsing across other websites via ads and pixels", "Shares data with thousands of third-party sellers", "Alexa voice recordings stored and analyzed"],
        "data_collected": ["Purchase and order history", "Browsing activity across sites", "Device and location data", "Voice recordings (Alexa)", "Payment information"]
    }
}

def known_site_fallback(domain):
    """Check if the domain matches a known curated site."""
    for known_domain, card in KNOWN_SITES.items():
        if domain == known_domain or domain.endswith("." + known_domain):
            return {**card}
    return None

def extract_text(url):
    if any(url.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
        raise ValueError("This link points to an image file. Please enter a website URL.")
    r = scraper.get(url, timeout=15, headers=HEADERS, allow_redirects=True)
    if r.status_code >= 400:
        raise ValueError(f"The website returned an error (HTTP {r.status_code}). It may be blocking automated access.")
    ctype = r.headers.get("Content-Type", "")
    if ctype.startswith("image/"):
        raise ValueError("This link points to an image. Please enter a website URL.")
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    return h.handle(str(soup))[:15000]

def ai_parse(raw):
    if not raw:
        return None
    for c in ["```json", "```"]:
        raw = raw.replace(c, "")
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None

SCORE_PROMPT = """Analyze this privacy policy. Return ONLY valid JSON with these exact fields (no markdown, no code blocks):
{
  "site_name": "the website name",
  "overall_score": number out of 10,
  "grade": "A" to "F",
  "verdict": "one short sentence",
  "categories": {
    "data_collection": { "score": 0-10, "explanation": "one short line" },
    "data_sharing": { "score": 0-10, "explanation": "one short line" },
    "user_rights": { "score": 0-10, "explanation": "one short line" },
    "tracking": { "score": 0-10, "explanation": "one short line" },
    "clarity": { "score": 0-10, "explanation": "one short line" }
  },
  "red_flags": ["list", "of", "concerns"],
  "data_collected": ["what", "they", "collect"]
}

Scoring guide:
- data_collection: how much personal data they collect (0 = everything, 10 = nothing)
- data_sharing: do they sell/share with third parties (0 = sells everything, 10 = no sharing)
- user_rights: can you access/delete/opt out (0 = no rights, 10 = full rights)
- tracking: cookies, pixels, fingerprinting (0 = heavy tracking, 10 = no tracking)
- clarity: is the policy clear and readable (0 = confusing, 10 = crystal clear)

Policy text:
"""

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/scan", methods=["POST"])
def scan():
    raw_url = request.json.get("url", "").strip()
    clean_url = "https://" + raw_url if not raw_url.startswith("http") else raw_url
    domain = extract_domain(raw_url)

    try:
        # Check known sites first
        fallback = known_site_fallback(domain)
        if fallback:
            return jsonify({"url": raw_url, "clean_domain": domain, "scorecard": fallback, "error": None})

        policy_url = find_page(clean_url, PRIVACY_PATHS)
        results = {"url": raw_url, "clean_domain": domain, "scorecard": None, "error": None}

        if policy_url:
            text = extract_text(policy_url)
            if text:
                raw = groq_complete(SCORE_PROMPT + text)
                results["scorecard"] = ai_parse(raw)

        if not results.get("scorecard"):
            return jsonify({"url": raw_url, "clean_domain": domain, "error": f"Could not find or access the privacy policy for {domain}. The site may block automated requests or require JavaScript."})

        return jsonify(results)

    except ValueError as e:
        return jsonify({"url": raw_url, "clean_domain": domain, "error": str(e).strip()})
    except Exception as e:
        print("SCAN ERROR:", traceback.format_exc())
        return jsonify({"url": raw_url, "clean_domain": domain, "error": f"Something went wrong scanning {domain}. Try again."})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
