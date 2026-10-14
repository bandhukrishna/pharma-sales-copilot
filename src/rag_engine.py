"""
Document Ingestion & RAG Retriever.
- Chunks markdown documents by section headers.
- Stores embeddings in ChromaDB (local, persistent).
- Returns relevant chunks with document + section citations.
"""

import os
import re
import hashlib
import chromadb
from typing import List, Dict
from src.config import DOCS_DIR

# --- ChromaDB storage path ---
CHROMA_DIR = "chroma_db"
COLLECTION_NAME = "pharma_docs"


def chunk_markdown_by_section(filepath: str) -> List[Dict[str, str]]:
    """
    Split a markdown file into chunks based on ## headers.
    Each chunk contains the section header + its content.
    The document title (# header) is prepended to every chunk for context.

    Returns:
        List of dicts with keys: 'text', 'source', 'section', 'chunk_id'
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    filename = os.path.basename(filepath)
    lines = content.split("\n")

    # Extract document title (first # header)
    doc_title = ""
    for line in lines:
        if line.strip().startswith("# ") and not line.strip().startswith("## "):
            doc_title = line.strip()
            break

    # Split by ## headers
    chunks = []
    current_section = "Introduction"
    current_lines = []

    for line in lines:
        if line.strip().startswith("## "):
            # Save previous section if it has content
            if current_lines:
                text = "\n".join(current_lines).strip()
                if text and len(text) > 20:  # skip near-empty chunks
                    chunk_id = hashlib.md5(
                        f"{filename}:{current_section}".encode()
                    ).hexdigest()[:12]
                    chunks.append(
                        {
                            "text": f"{doc_title}\n\n{text}" if doc_title else text,
                            "source": filename,
                            "section": current_section,
                            "chunk_id": chunk_id,
                        }
                    )
            # Start new section
            current_section = line.strip().lstrip("# ").strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    # Don't forget the last section
    if current_lines:
        text = "\n".join(current_lines).strip()
        if text and len(text) > 20:
            chunk_id = hashlib.md5(
                f"{filename}:{current_section}".encode()
            ).hexdigest()[:12]
            chunks.append(
                {
                    "text": f"{doc_title}\n\n{text}" if doc_title else text,
                    "source": filename,
                    "section": current_section,
                    "chunk_id": chunk_id,
                }
            )

    return chunks


def ingest_documents() -> chromadb.Collection:
    """
    Load all markdown docs, chunk them, and store in ChromaDB.
    Uses persistent storage so we don't re-embed on every run.

    Returns:
        ChromaDB collection
    """
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # Delete existing collection to ensure fresh data
    try:
        client.delete_collection(COLLECTION_NAME)
    except ValueError:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    # Process each markdown file
    all_chunks = []
    md_files = [f for f in os.listdir(DOCS_DIR) if f.endswith(".md")]

    for md_file in sorted(md_files):
        filepath = os.path.join(DOCS_DIR, md_file)
        chunks = chunk_markdown_by_section(filepath)
        all_chunks.extend(chunks)
        print(f"  Chunked {md_file}: {len(chunks)} sections")

    if not all_chunks:
        raise ValueError("No chunks created from documents!")

    # Add to ChromaDB
    collection.add(
        ids=[c["chunk_id"] for c in all_chunks],
        documents=[c["text"] for c in all_chunks],
        metadatas=[
            {"source": c["source"], "section": c["section"]} for c in all_chunks
        ],
    )

    print(f"\n  Total chunks ingested: {collection.count()}")
    return collection


def get_collection() -> chromadb.Collection:
    """Get the existing ChromaDB collection (assumes already ingested)."""
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    return client.get_collection(COLLECTION_NAME)


def retrieve(query: str, n_results: int = 3) -> List[Dict]:
    """
    Retrieve the most relevant document chunks for a query.

    Returns:
        List of dicts with keys: 'text', 'source', 'section', 'distance'
    """
    collection = get_collection()

    results = collection.query(
        query_texts=[query],
        n_results=min(n_results, collection.count()),
    )

    retrieved = []
    for i in range(len(results["ids"][0])):
        retrieved.append(
            {
                "text": results["documents"][0][i],
                "source": results["metadatas"][0][i]["source"],
                "section": results["metadatas"][0][i]["section"],
                "distance": results["distances"][0][i]
                if results["distances"]
                else None,
            }
        )

    return retrieved


def format_citations(chunks: List[Dict]) -> str:
    """Format retrieved chunks into a citation string for display."""
    citations = []
    for i, chunk in enumerate(chunks, 1):
        citations.append(f"[{i}] {chunk['source']} → {chunk['section']}")
    return "\n".join(citations)


# --- CLI Test ---
if __name__ == "__main__":
    print("=== RAG Engine: Document Ingestion & Retrieval Test ===\n")

    # Step 1: Ingest
    print("--- Ingesting Documents ---")
    collection = ingest_documents()

    # Step 2: Test retrieval queries
    test_queries = [
        "What is the incentive payout for achieving 95% quota?",
        "What are the approved messages for Respira?",
        "How is quota attainment calculated?",
        "What happened to Cardivex market share in Q1?",
    ]

    print("\n--- Retrieval Tests ---\n")
    for query in test_queries:
        print(f'Query: "{query}"')
        results = retrieve(query, n_results=2)
        for r in results:
            print(
                f"  📄 {r['source']} → {r['section']} (distance: {r['distance']:.4f})"
            )
            # Show first 100 chars of text
            preview = r["text"][:100].replace("\n", " ")
            print(f'     "{preview}..."')
        print()

    print("✅ RAG Engine tests complete!")
