<h1 align="center">🛡️ PrivacyPulse</h1>
<p align="center">Paste any URL. Get a plain English privacy score in seconds.</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white"/>
  <img src="https://img.shields.io/badge/Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white"/>
  <img src="https://img.shields.io/badge/Netlify-00C7B7?style=for-the-badge&logo=netlify&logoColor=white"/>
  <img src="https://img.shields.io/badge/Status-Live-brightgreen?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge"/>
</p>

<p align="center">
  <a href="https://zingy-shortbread-1b6a1d.netlify.app/">🔗 Try PrivacyPulse Live</a>
</p>

---

## What is PrivacyPulse

Nobody reads privacy policies. They are written in legal jargon. PrivacyPulse reads them for you and gives a clear score out of 10. Just paste any website URL and get an instant, plain English breakdown of what they do with your data.

---

## Features

- 🔍 **Scan any website instantly** — Enter a URL, get a score in seconds
- 📊 **Privacy scorecard** out of 10 across 5 categories
- 🌍 **Hardcoded database** for 20+ major sites
- 👥 **Community contribution system** for unknown sites
- 🌐 **Public contributions page** with status tracking
- 📱 **Mobile responsive** dark UI
- ⚡ **No login required**

---

## How it works

1️⃣ Paste any website URL  
2️⃣ PrivacyPulse scans trackers, cookies, data policies  
3️⃣ Get a clear scorecard — no jargon, just facts  

---

## Scoring categories

| Category | What it checks |
|---|---|
| 📦 Data Collection | How much data the site collects |
| 🤝 Data Sharing | Whether data is sold or shared |
| ⚖️ Your Rights | Can you delete or export your data |
| 👁️ Tracking | Cookies, pixels, fingerprinting |
| 📖 Clarity | Is the privacy policy readable |

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask |
| Frontend | HTML, CSS, JavaScript |
| Database | Supabase (PostgreSQL) |
| Deployment | Netlify |
| AI Analysis | Gemini API |

---

## Local setup

```bash
git clone https://github.com/abinayaitmec-lab/privacypulse
cd privacypulse
pip install -r requirements.txt
```

Add `SUPABASE_URL` and `SUPABASE_KEY` to `.env` file:

```
SUPABASE_URL=https://iebxzeqmpuvrbyutknvp.supabase.co
SUPABASE_KEY=your_anon_key
```

Then run:

```bash
python app.py
```

---

<p align="center">Built with ❤️ by Abi</p>
<p align="center">
  <a href="https://github.com/abinayaitmec-lab">GitHub</a> •
  <a href="https://www.linkedin.com/in/abinayavitmec/">LinkedIn</a> •
  <a href="mailto:abinayaitmec@gmail.com">Email</a>
</p>
