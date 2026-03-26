---
title: Content CT
emoji: 🔬
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: 1.32.0
app_file: app.py
pinned: false
---

# Content CT

A CAT scan for your site's content problems.
A Streamlit UI wrapping website crawling, SEO auditing, and AI-powered fix suggestions.

## Running Locally

1. Create a virtual environment and activate it:
```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install the necessary dependencies:
```bash
pip install -r requirements.txt
```

3. Run the Streamlit application:
```bash
streamlit run app.py
```

## Setup API Keys (For AI Suggestions)
You can provide your Anthropic or Gemini API key through the app's UI sidebar.
Alternatively, you can set `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` as environment variables.
