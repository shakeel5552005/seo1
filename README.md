# SA Digital Marketing — SEO Master Pro V2

A Streamlit website SEO auditing tool by Shakeel Ahmed.

## Features
- Same-domain crawler using internal links and XML sitemaps
- Per-page on-page and technical SEO checklist
- Executive summary and page-by-page audit views
- Google Autocomplete keyword suggestions (when reachable), on-page phrase extraction, and optional local Ollama AI suggestions
- Google PageSpeed Insights mobile and desktop tests for the homepage
- Detailed PDF, CSV and Excel exports
- Optional Google Search Console integration for URL Inspection and Search Analytics; the app works without GSC

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Optional local AI keyword suggestions
Install [Ollama](https://ollama.com), download a model (for example `ollama pull llama3.2:3b`), keep the Ollama server running, and use the local server URL/model name in the sidebar. This is optional and does not require a paid AI API.

## Optional Google Search Console setup
1. Enable the Google Search Console API in a Google Cloud project.
2. Create a service account and download its JSON key.
3. Add the service-account email as a user with Full access to the verified Search Console property.
4. In the app, upload the JSON key and enter the property exactly (for example `sc-domain:example.com` or `https://example.com/`).
5. Use URL Inspection and Search Performance in the Google Index tab. Google quotas and permissions apply.

## Notes and limitations
- Crawl only websites you own or are authorized to audit. Respect robots.txt and configure a conservative page limit.
- The checklist score is not a Google ranking score.
- Sitemap inclusion does not prove Google indexing. Verified index status and search performance require Google Search Console API access.
- Live SERP positions, backlink authority and keyword search volumes require third-party data providers and are not fabricated by this app.
- PageSpeed is run for the homepage to avoid excessive API requests.
- Without Ollama, keyword suggestions are Google Autocomplete and page-text derived; they are not represented as AI-generated or volume-validated. Ollama suggestions depend on the locally selected model.
