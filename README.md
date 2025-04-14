# AFIF — Another Fuck Importer for Firefly

AFIF is a flexible and unapologetic importer for [Firefly III](https://firefly-iii.org), written in Python. It lets you write your own parsers for any statement format — PDF, CSV, JSON, or raw text — and takes care of the rest:

- Categorization (with Redis-backed memory)
- Deduplication via `external_id`
- Posting to Firefly III via API

## 💡 Why AFIF?

Because manual imports are boring. Because all the other tools are too rigid. Because you just want to write a function and be done with it.

## 🚀 Features

- 🔌 **Pluggable parsers**: write your own `parse(line)` function in a file, point AFIF to it, done.
- 🔁 **Category caching**: automatic reuse of categories based on prior imports (via Redis)
- 🔍 **Duplicate detection**: based on consistent `external_id` hashing
- ✅ **Firefly III compatible**: works with Firefly's JSON:API
- 🧪 **Dry-run mode** coming soon

## 🛠 Requirements

- Python 3.9+
- Redis (local or remote)
- A working Firefly III instance with API token

## ⚙️ Usage

```bash
python run.py import statements/2024-ING.pdf \
  --parser parsers/parser_ing.py \
  --config config.yaml
