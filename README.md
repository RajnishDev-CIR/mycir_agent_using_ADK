# Run the ADK web UI
uv run adk web

# Run a specific agent in terminal
uv run adk run capex_agent

# If you add new packages later
uv add google-cloud-bigquery

# Remove a package
uv remove some-package

# Sync environment (when pulling from git or after pyproject.toml changes)
uv sync
```

---

## Complete folder structure with uv files
```
mycir_agent_ADK_v1/
├── .venv/                        ← created by uv venv
├── capex_agent/
│   ├── __init__.py
│   ├── .env                      ← your GCP credentials
│   ├── agent.py
│   ├── data/
│   │   └── system_price.csv
│   └── sub_agents/
│       ├── __init__.py
│       ├── capex_estimation/
│       │   ├── __init__.py
│       │   ├── agent.py
│       │   └── tools.py
│       └── market_research/
│           ├── __init__.py
│           └── agent.py
├── pyproject.toml                ← uv manages this
├── uv.lock                       ← auto-generated, commit this to git
└── README.md