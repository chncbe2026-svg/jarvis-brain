import os
import requests
import argparse
from pathlib import Path

def ingest_directory(directory_path, collection, vendor, severity):
    base_url = "http://localhost:3001"
    ingest_url = f"{base_url}/ingest"
    
    docs_path = Path(directory_path)
    if not docs_path.exists():
        print(f"❌ Directory not found: {directory_path}")
        return

    files = list(docs_path.glob("**/*.md")) + list(docs_path.glob("**/*.txt"))
    
    if not files:
        print(f"❓ No .md or .txt files found in {directory_path}")
        return

    print(f"🚀 Starting ingestion of {len(files)} files into collection: {collection}")
    
    for file_path in files:
        print(f"📤 Ingesting: {file_path.name}...", end="", flush=True)
        try:
            with open(file_path, "rb") as f:
                files_payload = {"file": (file_path.name, f, "text/plain")}
                data_payload = {
                    "collection": collection,
                    "vendor": vendor,
                    "severity": severity
                }
                
                response = requests.post(ingest_url, files=files_payload, data=data_payload)
                
                if response.status_code == 200:
                    result = response.json()
                    print(f" ✅ Success ({result.get('chunks')} chunks)")
                else:
                    print(f" ❌ Failed ({response.status_code}): {response.text}")
        except Exception as e:
            print(f" ❌ Error: {str(e)}")

    print("\n✨ Ingestion complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest documentation into JARVIS Qdrant backend")
    parser.add_argument("--dir", default="../documentation", help="Directory containing .md or .txt files")
    parser.add_argument("--collection", default="network_knowledge", help="Qdrant collection name")
    parser.add_argument("--vendor", default="Internal", help="Metadata: Vendor name")
    parser.add_argument("--severity", default="Informational", help="Metadata: Severity level")
    
    args = parser.parse_args()
    
    # Ensure absolute path if relative
    dir_path = os.path.abspath(args.dir)
    
    ingest_directory(dir_path, args.collection, args.vendor, args.severity)
