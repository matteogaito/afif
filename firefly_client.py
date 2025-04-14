import requests
import hashlib
import urllib


class FireflyClient:
    def __init__(self, cfg):
        self.base_url = cfg['firefly']['url'].rstrip('/')
        self.token = cfg['firefly']['api_token']
        self.source_id = cfg['account']['source_id']
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Content-Type": "application/vnd.api+json",
        }

    def _request(self, method, endpoint, **kwargs):
        url = f"{self.base_url}/api/v1/{endpoint}"
        resp = requests.request(method, url, headers=self.headers, **kwargs)
        resp.raise_for_status()
        return resp
    
    def generate_transaction_id(self,tx):
        base = f"{tx['date']}|{tx['amount']}|{tx['description']}"
        return hashlib.sha1(base.encode()).hexdigest()

    def already_exists(self, external_id):
        try:
            encoded = urllib.parse.quote(f"external_id_is:{external_id}")
            resp = self._request("GET", f"search/transactions?query={encoded}")
            journals = resp.json().get("data", [])

            print(journals)

            for entry in journals:
                for tx in entry["attributes"].get("transactions", []):
                    if tx.get("external_id") == external_id:
                        return True
            return False
        except Exception as e:
            print(f"Errore durante il check della transazione: {e}")
            return False

    def ensure_destination_account(self, payee_name):
        resp = self._request("GET", f"accounts?type=expense&search={payee_name}")
        accounts = resp.json().get("data", [])
        for acc in accounts:
            if acc["attributes"]["name"].lower() == payee_name.lower():
                return acc["id"]

        # Se non esiste, lo creo
        payload = {"name": payee_name, "type": "expense"}
        resp = self._request("POST", "accounts", json=payload)
        return resp.json()["data"]["id"]

    def get_categories(self):
        resp = self._request("GET", "categories")
        cats = resp.json().get("data", [])
        return {c["attributes"]["name"]: c["id"] for c in cats}

    def send_transaction(self, tx):
        payload = {
            "transactions": [{
                "type": tx['type'],
                "date": tx['date'],
                "amount": str(abs(tx['amount'])),
                "description": tx['description'],
                "category_name": tx['category'],
                "external_id": tx['external_id'], 
                "source_id": self.source_id if tx['type'] == 'withdrawal' else None,
                "payee_name": tx.get('creditor') or tx.get('place'),
            }]
        }

        if tx['type'] == "withdrawal":
            payload["transactions"][0]["destination_id"] = self.ensure_destination_account(tx["creditor"])

        print(payload)

        print(f"📤  Inviando: {tx['description']} ({tx['amount']} €) → {tx['category']}")
        resp = self._request("POST", "transactions", json=payload)
        print("✅  Successo:", resp.text)
        return resp.status_code, resp.json()
