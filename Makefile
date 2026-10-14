.PHONY: run test eval setup clean

# Launch the Streamlit web app
run:
	streamlit run app.py

# Run unit tests
test:
	pytest tests/ -v

# Run automated evaluation on all 10 Golden Questions
eval:
	python eval.py

# Full setup: create venv, install deps, ingest docs
setup:
	py -3.11 -m venv venv
	.\venv\Scripts\pip install --upgrade pip
	.\venv\Scripts\pip install -r requirements.txt
	.\venv\Scripts\python -c "from src.rag_engine import ingest_documents; ingest_documents()"

# Clean generated artifacts
clean:
	if exist chroma_db rmdir /s /q chroma_db
	if exist .pytest_cache rmdir /s /q .pytest_cache
	if exist eval_results.md del eval_results.md
	for /d %%d in (src\__pycache__ tests\__pycache__) do if exist %%d rmdir /s /q %%d
