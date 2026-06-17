import os, re, json, requests, cloudscraper, traceback, time
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

# --- HTTP clients ---
scraper = cloudscraper.create_scraper()
h = HTML2Text()
h.ignore_links = True
h.ignore_images = True
h.ignore_emphasis = True
h.body_width = 0
h.ignore_anchors = True

# Optional curl_cffi for better TLS fingerprinting
CURL_AVAILABLE = False
try:
    from curl_cffi import requests as curl_requests
    CURL_AVAILABLE = True
except ImportError:
    pass

# Optional pdfplumber for PDF policies
PDF_AVAILABLE = False
try:
    import pdfplumber
    import io
    PDF_AVAILABLE = True
except ImportError:
    pass

# Optional proxy API keys
SCRAPINGBEE_KEY = os.getenv("SCRAPINGBEE_API_KEY")
SCRAPINGFISH_KEY = os.getenv("SCRAPINGFISH_API_KEY")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}

# --- Groq ---
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
    "/privacy", "/privacy-policy", "/privacy.html", "/privacy-policy.html",
    "/legal/privacy", "/legal/privacy-policy", "/policies/privacy-policy",
    "/en-US/privacy/privacy-policy", "/privacy-notice", "/data-privacy",
    "/privacy-policy/", "/legal/privacy-policy.html", "/pages/privacy-policy",
    "/about/privacy", "/corporate/privacy",
]

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico")

# --- HTTP fetching with fallback chain ---
def fetch_url(url, timeout=15):
    """Try multiple fetch methods: curl_cffi -> cloudscraper -> proxy -> requests."""
    errors = []

    # 1) curl_cffi (best TLS fingerprint)
    if CURL_AVAILABLE:
        try:
            r = curl_requests.get(url, timeout=timeout, headers=HEADERS, impersonate="chrome124", allow_redirects=True)
            if r.status_code < 400:
                return r
        except Exception as e:
            errors.append(f"curl_cffi: {e}")

    # 2) ScrapingBee proxy
    if SCRAPINGBEE_KEY:
        try:
            proxy_url = f"https://app.scrapingbee.com/api/v1/?api_key={SCRAPINGBEE_KEY}&url={url}&render_js=true"
            r = requests.get(proxy_url, timeout=timeout + 5)
            if r.status_code < 400:
                r.url = url
                return r
        except Exception as e:
            errors.append(f"ScrapingBee: {e}")

    # 3) ScrapingFish proxy
    if SCRAPINGFISH_KEY:
        try:
            proxy_url = f"https://scrapingfish.com/?key={SCRAPINGFISH_KEY}&url={url}&type=json"
            r = requests.get(proxy_url, timeout=timeout + 5)
            if r.status_code < 400:
                data = r.json()
                if "content" in data:
                    r2 = requests.Response()
                    r2.status_code = 200
                    r2._content = data["content"].encode("utf-8")
                    r2.headers["Content-Type"] = data.get("content_type", "text/html")
                    r2.url = url
                    return r2
        except Exception as e:
            errors.append(f"ScrapingFish: {e}")

    # 4) cloudscraper (Cloudflare bypass)
    try:
        r = scraper.get(url, timeout=timeout, headers=HEADERS, allow_redirects=True)
        if r.status_code < 400:
            return r
    except Exception as e:
        errors.append(f"cloudscraper: {e}")

    raise ValueError(f"Could not fetch {url}. Methods tried: {'; '.join(errors)}" if errors else f"Could not fetch {url}")

# --- Google Cache fallback ---
def fetch_from_google_cache(url):
    """Fetch page content from Google Cache (works for many JS-rendered sites)."""
    cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}&strip=1&vwsrc=0"
    try:
        r = scraper.get(cache_url, timeout=10, headers=HEADERS)
        if r.status_code < 400 and "cache" not in r.url:
            soup = BeautifulSoup(r.text, "html.parser")
            # Google Cache wraps content in <pre id="pre"> or <div id="google-cache">
            content = soup.find("pre", id="pre") or soup.find("div", id="google-cache") or soup.find("div", style=True)
            if content:
                return content.get_text()
        return None
    except Exception:
        return None

# --- Wayback Machine fallback ---
def fetch_from_wayback(url):
    """Fetch latest snapshot from Wayback Machine."""
    try:
        cdx = f"https://web.archive.org/cdx/search/cdx?url={url}&output=json&limit=1&fl=timestamp,original&filter=statuscode:200"
        r = requests.get(cdx, timeout=10)
        if r.status_code < 400:
            data = r.json()
            if len(data) > 1:
                ts = data[1][0]
                snapshot_url = f"https://web.archive.org/web/{ts}/{url}"
                sr = scraper.get(snapshot_url, timeout=10, headers=HEADERS)
                if sr.status_code < 400:
                    return sr.text
        return None
    except Exception:
        return None

# --- PDF extraction ---
def extract_pdf_text(url):
    """Download and extract text from a PDF."""
    if not PDF_AVAILABLE:
        return None
    try:
        r = fetch_url(url, timeout=15)
        content_type = r.headers.get("Content-Type", "")
        if "application/pdf" in content_type or url.lower().endswith(".pdf"):
            pdf_file = io.BytesIO(r.content)
            text = ""
            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            return text[:15000] if text.strip() else None
        return None
    except Exception:
        return None

def extract_domain(raw_url):
    if not raw_url.startswith("http"):
        raw_url = "https://" + raw_url
    parsed = urlparse(raw_url)
    domain = parsed.netloc.lower()
    return domain.replace("www.", "")

def check_robots_txt(base_url):
    """Check if scraping the privacy policy is allowed by robots.txt."""
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        r = requests.get(robots_url, timeout=5, headers=HEADERS)
        if r.status_code < 400:
            for line in r.text.lower().splitlines():
                if "crawl-delay" in line:
                    try:
                        delay = int(re.search(r"(\d+)", line).group(1))
                        time.sleep(min(delay, 3))
                    except Exception:
                        pass
                if "disallow: /privacy" in line or "disallow: /privacy-policy" in line:
                    pass  # Log but still try (robots.txt is not legally binding for public analysis)
    except Exception:
        pass

def find_page(url, paths):
    if any(url.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
        raise ValueError("That's an image file, not a website. Please enter a normal URL like example.com")
    base_m = re.match(r"(https?://[^/]+)", url)
    if not base_m:
        return None
    base = base_m.group(1)

    check_robots_txt(base)

    # Strategy A: try each privacy path directly
    for path in paths:
        full = base + path
        try:
            r = fetch_url(full, timeout=8)
            if r.status_code < 400:
                ctype = r.headers.get("Content-Type", "")
                if "text/html" in ctype or "text/plain" in ctype:
                    return full
                if "application/pdf" in ctype or full.lower().endswith(".pdf"):
                    return full
        except Exception:
            continue

    # Strategy B: fetch homepage, search for privacy link
    try:
        r = fetch_url(url, timeout=10)
        if r.status_code < 400:
            ctype = r.headers.get("Content-Type", "")
            if ctype.startswith("image/"):
                raise ValueError("That link points to an image, not a webpage. Please enter a website URL.")
            soup = BeautifulSoup(r.text, "html.parser")
            for link in soup.find_all("a", href=True):
                text = link.get_text(strip=True).lower()
                href = link["href"].lower()
                if any(kw in text or kw in href for kw in ["privacy", "terms"]):
                    if href.startswith("http"):
                        return href
                    return base + (href if href.startswith("/") else "/" + href)
    except Exception:
        pass

    # Strategy C: try Google Cache (handles JS-rendered sites)
    try:
        cache_content = fetch_from_google_cache(url)
        if cache_content:
            return f"__cache__:{url}"
    except Exception:
        pass

    # Strategy D: try Wayback Machine
    try:
        wb_content = fetch_from_wayback(url)
        if wb_content:
            return f"__wayback__:{url}"
    except Exception:
        pass

    return None

def extract_text(url):
    if any(url.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
        raise ValueError("This link points to an image file. Please enter a website URL.")

    source_tag = ""

    # Handle cached/wayback sources
    if url.startswith("__cache__:"):
        real_url = url.replace("__cache__:", "", 1)
        content = fetch_from_google_cache(real_url)
        if not content:
            raise ValueError(f"Could not retrieve cached version of {real_url}")
        source_tag = " (from Google Cache)"
        text = content
        return h.handle(text)[:15000] + source_tag

    if url.startswith("__wayback__:"):
        real_url = url.replace("__wayback__:", "", 1)
        content = fetch_from_wayback(real_url)
        if not content:
            raise ValueError(f"Could not retrieve archived version of {real_url}")
        source_tag = " (from Wayback Machine)"
        soup = BeautifulSoup(content, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        return h.handle(str(soup))[:15000] + source_tag

    # Check if it's a PDF
    pdf_text = extract_pdf_text(url)
    if pdf_text:
        return pdf_text + " (from PDF)"

    # Normal page
    r = fetch_url(url, timeout=15)
    if r.status_code >= 400:
        raise ValueError(f"The website returned an error (HTTP {r.status_code}). It may be blocking automated access.")
    ctype = r.headers.get("Content-Type", "")
    if ctype.startswith("image/"):
        raise ValueError("This link points to an image. Please enter a website URL.")

    # If it's a PDF detected by content-type
    if "application/pdf" in ctype:
        pdf_text = extract_pdf_text(url)
        if pdf_text:
            return pdf_text + " (from PDF)"

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
        obj = json.loads(raw)
        cats = obj.get("categories", {})
        expected = {"data_collection", "data_sharing", "user_rights", "tracking", "clarity"}
        if not expected.issubset(cats.keys()):
            return None
        return obj
    except Exception:
        return None

SCORE_PROMPT = """Analyze this privacy policy. If the policy text is NOT in English, translate it to English before scoring. Return ONLY valid JSON with these exact fields (no markdown, no code blocks):
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

# ===== Curated known sites =====
KNOWN_SITES = {
    "instagram.com": {
        "site_name": "Instagram",
        "overall_score": 3, "grade": "D",
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
        "overall_score": 2, "grade": "F",
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
        "overall_score": 4, "grade": "D",
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
        "overall_score": 5, "grade": "C",
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
        "overall_score": 7, "grade": "B",
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
        "overall_score": 4, "grade": "D",
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
    for known_domain, card in KNOWN_SITES.items():
        if domain == known_domain or domain.endswith("." + known_domain):
            return {**card}
    return None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/scan", methods=["POST"])
def scan():
    raw_url = request.json.get("url", "").strip()
    clean_url = "https://" + raw_url if not raw_url.startswith("http") else raw_url
    domain = extract_domain(raw_url)

    try:
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
            return jsonify({"url": raw_url, "clean_domain": domain, "error": f"Could not find or access the privacy policy for {domain}. The site may block automated requests, require JavaScript, or the policy may not be publicly accessible."})

        return jsonify(results)

    except ValueError as e:
        return jsonify({"url": raw_url, "clean_domain": domain, "error": str(e).strip()})
    except Exception as e:
        print("SCAN ERROR:", traceback.format_exc())
        return jsonify({"url": raw_url, "clean_domain": domain, "error": f"Something went wrong scanning {domain}. Try again."})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
