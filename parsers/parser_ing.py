# parser_ing.py
import pdfplumber
from datetime import datetime
import re
import sys

LINE_TO_EXCLUDE = [ 
    [ 'NON', 'CONTABILIZZATA' ], 
    ["LISTA", "MOVIMENTI", "CONTO", "CORRENTE"]
]

# Converts Italian month names to English for parsing
mesi = {
    "gennaio": "January", "febbraio": "February", "marzo": "March",
    "aprile": "April", "maggio": "May", "giugno": "June",
    "luglio": "July", "agosto": "August", "settembre": "September",
    "ottobre": "October", "novembre": "November", "dicembre": "December"
}

def normalize_date_it(date_str):
    for it, en in mesi.items():
        if it in date_str.lower():
            return date_str.lower().replace(it, en).capitalize()
    return date_str

def parse(line):
    result = {
        "date": None,
        "description": None,
        "amount": None,
        "card": None,
        "type": None,
        "creditor": None
    }

    # Match Mastercard operation
    mastercard_match = re.search(r"Operazione Mastercard del (\d{2}/\d{2}/\d{4}) alle ore (\d{2}:\d{2})", line)
    if mastercard_match:
        op_date = mastercard_match.group(1)
        op_time = mastercard_match.group(2)
        dt = datetime.strptime(f"{op_date} {op_time}", "%d/%m/%Y %H:%M")
        result["date"] = dt.isoformat()

        amount_match = re.search(r"(-?[0-9]+,[0-9]{2})\s+(?:Carta|Saldo)", line)
        if amount_match:
            result["amount"] = float(amount_match.group(1).replace(",", "."))
            result["type"] = "withdrawal"

        card_match = re.search(r"Carta\s+(x+\d+)", line)
        if card_match:
            result["card"] = card_match.group(1)

        place_match = re.search(r"presso\s+(.*?)\s+Saldo Disponibile", line)
        if place_match:
            result["creditor"] = place_match.group(1).strip()

        result["description"] = f"Spesa presso {result['creditor']} con carta {result['card']}"

    # Match Bonifico
    elif "BONIFICO" in line.upper():
        bonifico_date = re.match(r"^(\d{2} \w+ \d{4})", line)
        if bonifico_date:
            try:
                fixed_date = normalize_date_it(bonifico_date.group(1))
                dt = datetime.strptime(fixed_date, "%d %B %Y")
                result["date"] = dt.isoformat()
            except ValueError as e:
                pass

        amount_match = re.search(r"(?:^|\s)([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})(?:\s+Ordinante|\s+Data|$)", line)
        if amount_match:
            result["amount"] = float(amount_match.group(1).replace(".", "").replace(",", "."))
            result["type"] = "deposit"
        else:
            print(line)
            sys.exit(2)

    # Match Addebito SDD CORE
    elif "ADDEBITO SDD CORE" in line.upper():
        addebito_date = re.match(r"^(\d{2} \w+ \d{4})", line)
        if addebito_date:
            try:
                fixed_date = normalize_date_it(addebito_date.group(1))
                dt = datetime.strptime(fixed_date, "%d %B %Y")
                result["date"] = dt.isoformat()
            except ValueError:
                pass

        amount_match = re.search(r"Creditor ADDEBITI\s+-?([0-9]+,[0-9]{2})", line)
        if not amount_match:
            amount_match = re.search(r"ADDEBITI\s+-?([0-9]+,[0-9]{2})", line)
        if amount_match:
            result["amount"] = float("-" + amount_match.group(1).replace(",", "."))
            result["type"] = "expense"

        creditor_match = re.search(r"ADDEBITI\s+-?[0-9]+,[0-9]{2}\s+([A-Z0-9 ]+?)\s+Id Mandato", line)
        if creditor_match:
            result["creditor"] = creditor_match.group(1).strip()
            result["description"] = f"Addebito diretto a {result['creditor']}"
        else:
            result["description"] = "Addebito diretto SDD"

        ref_match = re.search(r"Rif\. Finanziamento\s+(.*?)\s+rata", line)
        if ref_match:
            result["description"] = f"Addebito diretto: Finanziamento {ref_match.group(1).strip()}"
        else:
            result["description"] = "Addebito diretto SDD"

        # Try to match creditor name
        creditor_match = re.search(r"ADDEBITI\s+-?[0-9]+,[0-9]{2}\s+([A-Z0-9 ]+?)\s+Id Mandato", line)
        if creditor_match:
            result["creditor"] = creditor_match.group(1).strip()
            result["description"] = f"Addebito diretto a {result['creditor']}"

        # Match creditor name for financing references
        ref_match = re.search(r"Rif\. Finanziamento\s+(.*?)\s+rata", line)
        if ref_match:
            result["description"] = f"Addebito diretto: Finanziamento {ref_match.group(1).strip()}"
            if not result["creditor"]:
                creditor_name = re.search(r"([A-Z ]+)\s+Id Mandato", line)
                if creditor_name:
                    result["creditor"] = creditor_name.group(1).strip()

    # Match bollo recovery
    elif "imposta di bollo del rapporto" in line.lower():
        bollo_date = re.match(r"^(\d{2} \w+ \d{4})", line)
        if bollo_date:
            try:
                fixed_date = normalize_date_it(bollo_date.group(1))
                dt = datetime.strptime(fixed_date, "%d %B %Y")
                result["date"] = dt.isoformat()
            except ValueError:
                pass

        amount_match = re.search(r"ALTRI\s+-?([0-9]+,[0-9]{2})", line)
        if amount_match:
            amount = float(amount_match.group(1).replace(",", "."))
            result["amount"] = amount

        result["description"] = "Recupero imposta di bollo"
        result["type"] = "expense"
        result["creditor"] = "Bank"

    if not result["date"] or not result["amount"]:
        print("Failed to parse line, {}".format(line))
        sys.exit(2)

    return result

def parse_transaction_file(transactions_file):
    results = []
    combined_lines = []  # Persist across pages
    buffer = ""

    with pdfplumber.open(transactions_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            lines = text.split('\n')

            # Combine lines that belong to the same transaction, starting with a date
            for line in lines:
                if re.match(r"^\d{2} \w+ \d{4}", line):  # Starts with a date (e.g., 05 aprile 2025)
                    if buffer:
                        combined_lines.append(buffer.strip())
                    buffer = line
                else:
                    buffer += " " + line

    if buffer:
        combined_lines.append(buffer.strip())

    filtered_lines = []
    for line in combined_lines:
        upper_line = line.upper()
        if not any(all(word in upper_line for word in pattern) for pattern in LINE_TO_EXCLUDE):
            filtered_lines.append(line)

    # Debug output for each combined line
    for line in filtered_lines:
        line = line.replace("- Transazio ne C-less", "").replace("- Trans azione C-less","").replace("- Transaz ione C-less","").replace("- Tra nsazione C-less","")
        print(line)
        result = parse(line)
        results.append(result)

    return results  # Currently only returns combined lines without parsing
