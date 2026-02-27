# AI Intake Steward – Teamsters Local 795

Steward-first AI intake tool designed for Teamsters Local 795 (Wichita Transit).

## Purpose
This application performs neutral fact-gathering only for potential grievances.
It makes no determinations, findings, or violations.

## Core Principles
- Intake-only (no decisions)
- Uses "possible misapplication" language exclusively
- Steward remains the sole gatekeeper and decision-maker
- No accounts, no records, no workflow
- KB-first deterministic routing (no embeddings)
- Hard token budget per session

## File Structure

```
app.py                          # Streamlit orchestration layer
contract.txt                    # Plain-text CBA reference (2025–2028)
kb.json                         # Knowledge-base items (keyword routing)
deadlines.json                  # Configurable deadline rules
requirements.txt
.streamlit/
    secrets.toml.example        # Copy to secrets.toml and fill in values
intake/
    __init__.py
    auth.py                     # Passcode-based access gate
    kb.py                       # KB-first deterministic router
    deadlines.py                # Calendar-day deadline calculator
    llm.py                      # OpenAI Responses API client
    packet.py                   # Steward review packet builder
    emailer.py                  # Optional SendGrid email-out
```

## Setup

1. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
2. Fill in `OPENAI_API_KEY`, `PASSCODES_JSON`, and other values
3. Install dependencies: `pip install -r requirements.txt`
4. Run: `streamlit run app.py`

## Configuration (secrets.toml)

| Key | Description |
|-----|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `PASSCODES_JSON` | JSON array of valid passcodes, e.g. `'["code1","code2"]'` |
| `ALLOWED_MODELS_JSON` | JSON array of allowed model names |
| `DEFAULT_MODEL` | Default model (e.g. `gpt-4.1-mini`) |
| `TEMPERATURE` | LLM temperature (0.0–1.0) |
| `MAX_OUTPUT_TOKENS` | Max tokens per LLM response |
| `HARD_TOKEN_BUDGET` | Approximate session token ceiling |
| `EMAIL_ENABLED` | `true` to enable SendGrid email-out |
| `SENDGRID_API_KEY` | SendGrid API key (if email enabled) |
| `FROM_EMAIL` | Sender email address |
| `TO_EMAIL` | Steward recipient email address |

## Status
Private steward tool. Not a system of record.
