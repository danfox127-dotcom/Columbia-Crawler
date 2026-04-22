# Global AI Stack Configuration

## Overview
This document outlines the **global AI workflow harness** used across projects for intelligent code generation, documentation, analysis, and automation. Each project inherits this stack via environment variables and MCP server registration.

---

## 1. AI Model Providers

### Gemini (Google)
**Status**: ✅ Active (integrated in `app.py`)

**Use Case**: Healthcare SEO content corrections, fast reasoning
- **Model**: `gemini-2.5-flash`
- **API Endpoint**: `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent`
- **Auth**: `GEMINI_API_KEY` (environment variable or HF Secrets)
- **Config**:
  ```json
  {
    "timeout": 60,
    "payload": {
      "contents": [{"parts": [{"text": "..."}]}]
    }
  }
  ```
- **Tokens Used For**:
  - SEO issue remediation suggestions
  - Bulk title/meta description rewrites
  - Content gap analysis prompts

### Claude (Anthropic)
**Status**: 🔄 Available (not yet integrated in this project)

**Use Case**: Code review, architecture decisions, complex reasoning
- **Model Family**: Claude Opus 4.6 / Sonnet 4.6 / Haiku 4.5
- **API**: `https://api.anthropic.com/v1/...`
- **Auth**: `ANTHROPIC_API_KEY` (environment variable)
- **Recommended For**:
  - Architecture reviews & refactoring decisions
  - Multi-step debugging workflows
  - Long-context documentation generation
  - Code quality analysis (prompt caching for large codebases)

### Local LLM (Bonsai)
**Status**: 🚧 Placeholder (future integration)

**Use Case**: Offline/private inference, cost reduction at scale
- **Model**: Open-source LLM (Llama 2, Mistral, etc.)
- **Deployment**: Local Docker container or edge device
- **Auth**: Local endpoint (no API key)
- **Recommended For**:
  - Privacy-critical analysis (healthcare data)
  - High-volume batch processing (cost optimization)
  - Fallback when cloud APIs unavailable

---

## 2. MCP Server Registry

MCP (Model Context Protocol) servers provide structured access to external tools and data sources. Register servers in `settings.json` or via the Claude Code CLI.

### Currently Configured
| Server | Purpose | Status |
|--------|---------|--------|
| **claude.ai/Ahrefs** | SEO analytics & backlink data | 🔄 Optional |
| **claude.ai/Clinical Trials** | ClinicalTrials.gov API access | 🔄 Optional |
| **claude.ai/bioRxiv** | Preprint research discovery | 🔄 Optional |
| **claude.ai/Context7** | Library/framework documentation | ✅ Ready |
| **claude.ai/Windsor.ai** | Multi-source ad analytics | 🔄 Optional |
| **claude.ai/PubMed** | Biomedical literature search | 🔄 Optional |
| **claude.ai/Hugging Face** | Model & dataset discovery | 🔄 Optional |
| **plugin:vercel:vercel** | Vercel deployment management | 🔄 Optional |
| **plugin:context7:context7** | Docs lookup (same as above) | ✅ Ready |

### Recommended Setup for Columbia-Crawler
```json
{
  "mcp_servers": {
    "context7": {
      "description": "Fetch Streamlit, Scrapy, Pandas docs on-demand",
      "enabled": true
    },
    "ahrefs": {
      "description": "SEO competitive analysis (future feature)",
      "enabled": false,
      "config": {}
    },
    "hugging-face": {
      "description": "Model discovery for fine-tuned NLP (future)",
      "enabled": false
    }
  }
}
```

---

## 3. Environment Variables

### Required (Project-Specific)
```bash
GEMINI_API_KEY=<your-key>          # For SEO suggestion AI
```

### Optional (Global / Cross-Project)
```bash
ANTHROPIC_API_KEY=<your-key>       # Claude API access
OPENAI_API_KEY=<your-key>          # GPT integration (not used here)
LOCAL_LLM_ENDPOINT=http://localhost:8000  # Bonsai/local LLM
DEBUG=1                             # Verbose logging
```

---

## 4. Workflow Patterns

### Pattern A: Fast Feedback Loop (Gemini)
1. User provides input (URLs, metadata)
2. Parse and structure data
3. Call Gemini with focused prompt (healthcare context)
4. Display suggestions in real time
5. Export results

**Used in**: `app.py` → `call_gemini()` → Gemini Suggestions tab

### Pattern B: Deep Analysis (Claude)
1. Extract codebase context (CLAUDE.md, git history)
2. Formulate multi-turn conversation
3. Use prompt caching to avoid re-tokenizing large contexts
4. Iterative refinement of suggestions
5. Generate architectural docs or refactoring plan

**Use when**: Planning major features, reviewing PRs, debugging complex issues

### Pattern C: Batch Processing (Local LLM)
1. Queue up 100+ pages for analysis
2. Run local inference (no API calls)
3. Aggregate results into report
4. Zero latency, zero cloud costs

**Use when**: Scaling to 10k+ pages, healthcare privacy concerns

### Pattern D: Documentation Lookup (Context7 MCP)
1. User asks about a library (Scrapy, Pandas, Streamlit)
2. Context7 fetches latest docs
3. LLM synthesizes relevant examples
4. Return code snippet + best practices

**Used in**: Claude Code intelligent hints & code completion

---

## 5. Integration Checklist

- [ ] `GEMINI_API_KEY` set in `.env` or HF Secrets
- [ ] Claude API key available for cross-project work (if needed)
- [ ] Context7 MCP server enabled in Claude Code settings
- [ ] Ahrefs/Windsor.ai connectors authorized (optional, for future features)
- [ ] Local LLM endpoint configured (if using Bonsai)
- [ ] Project-specific model preference documented (e.g., Gemini for speed, Claude for depth)

---

## 6. Cost & Rate Limits

| Provider | Model | Input Cost | Output Cost | Rate Limit |
|----------|-------|-----------|-----------|-----------|
| **Gemini** | 2.5 Flash | $0.075/1M | $0.30/1M | 1000 req/min |
| **Claude** | Opus 4.6 | $15/1M | $75/1M | 40K req/min |
| **Claude** | Sonnet 4.6 | $3/1M | $15/1M | 40K req/min |
| **Claude** | Haiku 4.5 | $0.80/1M | $4/1M | 40K req/min |
| **Local LLM** | (self-hosted) | $0 | $0 | Unlimited |

**Recommendation**: Use Gemini for high-volume SEO suggestions (cheap), Claude Haiku for quick code reviews (fast), Claude Opus for complex architecture decisions (powerful).

---

## 7. Future Expansion Points

### Healthcare NLP
- Fine-tune local LLM on medical terminology
- Integrate MedLLaMA or BioBERT for domain-specific analysis
- Use Claude + RAG for clinical guideline lookup

### Competitive Intelligence
- Ahrefs MCP to pull competitor SEO data
- Clinical Trials MCP for market landscape analysis
- Auto-generate competitor analysis reports

### Automated Remediation
- Loop: detect issue → generate suggestion → apply fix → verify
- Integrate with GitHub Actions for continuous SEO audits
- Scheduled sitemap scans with email diffs

### Multi-LLM Routing
- Route simple tasks (SEO fixes) to Gemini (fast + cheap)
- Route complex tasks (architecture) to Claude (powerful)
- Fallback to Local LLM if API limits hit

---

## 8. Security & Privacy Notes

- **API Keys**: Store in `.env.local` (not version control) or HF Secrets
- **Data Handling**: 
  - Gemini: Healthcare metadata sent to Google (comply with HIPAA if needed)
  - Local LLM: All processing stays on-device
  - Claude: Anthropic has SOC 2 / enterprise agreements available
- **Rate Limiting**: Monitor Gemini usage to avoid quota exhaustion
- **Audit Trail**: Log all AI API calls for compliance

---

**Last Updated**: 2026-04-21  
**Maintainer**: Vibe Coder (Dan Weiman)  
**Version**: 1.0 (Beta)
