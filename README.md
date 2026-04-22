# grants-opportunity-research-assistant

Generate opportunity research briefs and pursuit queues for grant/funding opportunities.

## Quick start (CSV input)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.run --input examples/opportunities.csv --focus "ai,automation,small business" --output out
```

## Optional API discovery (experimental)
```bash
python -m src.run --keyword "small business ai" --focus "ai,automation" --output out
```
