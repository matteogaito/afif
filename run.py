# run.py
import os
#import importlib
import argparse
import yaml
import redis
import requests
#from parser_ing import parse_pdf_with_config
from datetime import datetime
from urllib.parse import quote
import requests
import re
import importlib.util
from pathlib import Path
from firefly_client import FireflyClient
import subprocess

def ensure_redis_container_running(container_name="redis-firefly"):
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
            capture_output=True, text=True
        )

        print(f"[DEBUG] docker inspect returncode: {result.returncode}")
        print(f"[DEBUG] docker inspect stdout: {result.stdout.strip()}")
        print(f"[DEBUG] docker inspect stderr: {result.stderr.strip()}")

        if result.returncode != 0:
            print(f"❌ Redis container '{container_name}' not found.")
            return False

        running = result.stdout.strip()
        if running == "true":
            print(f"✅ Redis container '{container_name}' is already running.")
            return True
        else:
            print(f"⏳ Starting Redis container '{container_name}'...")
            start_result = subprocess.run(["docker", "start", container_name], capture_output=True, text=True)
            print(f"[DEBUG] docker start stdout: {start_result.stdout.strip()}")
            print(f"[DEBUG] docker start stderr: {start_result.stderr.strip()}")

            if start_result.returncode == 0:
                print(f"✅ Redis container '{container_name}' started.")
                return True
            else:
                print(f"❌ Failed to start Redis container '{container_name}'.")
                return False
    except Exception as e:
        print(f"⚠️ Error checking Redis container: {e}")
        return False

def load_builtin_parser(name):
    parser_path = Path(__file__).parent / "parsers" / f"{name}"
    spec = importlib.util.spec_from_file_location("custom_parser", str(parser_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def normalize_description(desc):
    return re.sub(r"\s+", " ", desc.strip().lower())

# --- Categorization via Redis ---
def categorize(description, r):
    for key in r.scan_iter("match:*"):
        if key[6:].lower() in description.lower():
            return r.hget(key, "category")
    return None

def prompt_category(description, amount, categories, previous=None):
    print(f"\nTransazione: {description} ({amount} €)")
    
    cat_list = list(categories.keys())

    if previous:
        print(f"Categoria suggerita: '{previous}'")
        print("Premi [Invio] per confermare, [n] per scegliere un'altra, [s] per saltare.")
        choice = input("> ").strip().lower()
        if choice == "":
            return previous
        if choice == "s":
            return None
        if choice != "n":
            print("⚠️ Scelta non valida, mostro le categorie.")
    
    print("Scegli una categoria tra le seguenti:")
    for i, name in enumerate(cat_list):
        print(f"  [{i+1}] {name}")
    print("  [s] Salta questa transazione")

    while True:
        choice = input("Numero categoria (o 's'): ").strip().lower()
        if choice == 's':
            return None
        elif choice.isdigit() and 1 <= int(choice) <= len(cat_list):
            return cat_list[int(choice)-1]
        print("⚠️ Scelta non valida, riprova.")

# --- Main CLI ---
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', required=True, help='File to import')
    parser.add_argument('--parser', required=True, help='YAML file with parsing rules')
    parser.add_argument('--config', required=True, help='YAML config file with Firefly and account info')
    args = parser.parse_args()

    #parser_path = os.path.abspath(args.parser)

    with open(args.config, 'r') as f:
        cfg = yaml.safe_load(f)

    #spec = importlib.util.spec_from_file_location("parser_module", parser_path)
    #parser_module = importlib.util.module_from_spec(spec)
    #spec.loader.exec_module(parser_module)

    if not ensure_redis_container_running:
        print(f"❌ Unable to start Redis container")
    else:
        print("ciao")

    # Get custom parser
    parser = load_builtin_parser(args.parser)
    transactions = parser.parse_transaction_file(args.file)

    # Get Firefly Categories
    fc = FireflyClient(cfg)
    categories = fc.get_categories()

    redis_client = redis.Redis(host=cfg['redis']['host'], port=cfg['redis']['port'], decode_responses=True)

    for tx in transactions:
        try:
            norm_desc = normalize_description(tx['description'])
        except Exception as e:
            print("Failed to get description with error: {}".format(e))
            print(tx)
            raise

        previous_cat = redis_client.get(f"category:{norm_desc}")

        tx['category'] = prompt_category(tx['description'], tx['amount'], categories, previous=previous_cat)

        if tx['category']:
            tx_id = fc.generate_transaction_id(tx)
            tx['external_id'] = tx_id
            if not fc.already_exists(tx_id):
                fc.send_transaction(tx)
            else:
                print(f"⚠️  Transazione già presente: {tx['description']} ({tx['amount']} €)")

            if tx['category'] != previous_cat:
                redis_client.set(f"category:{norm_desc}", tx['category'])

if __name__ == "__main__":
    main()
