"""Account storage: one offline profile plus saved Ely.by accounts.

Tokens live in ~/.mcl/accounts.json — a local file, same trust level as any
other launcher. Passwords are never stored.
"""

import uuid

from cactus_lite.core.paths import ACCOUNTS_PATH
from cactus_lite.core.storage import read_json, write_json

OFFLINE_ID = "offline"


def offline_account(nick):
    return {
        "id": OFFLINE_ID,
        "kind": "offline",
        "username": nick or "Steve",
        "uuid": str(uuid.uuid4()),
        "access_token": "",
        "client_token": "",
    }


class AccountStore:
    """Ordered list of Ely.by accounts with a selected id."""

    def __init__(self, path=ACCOUNTS_PATH):
        self.path = path
        data = read_json(path) or {}
        self.accounts = [a for a in data.get("accounts", []) if a.get("kind") == "elyby"]
        self.selected = data.get("selected") or OFFLINE_ID

    def save(self):
        return write_json(self.path, {"selected": self.selected, "accounts": self.accounts})

    def get(self, account_id):
        return next((a for a in self.accounts if a.get("id") == account_id), None)

    def selected_account(self):
        return self.get(self.selected)

    def select(self, account_id):
        self.selected = account_id if self.get(account_id) else OFFLINE_ID
        self.save()
        return self.selected

    def add(self, profile):
        """Insert or replace an Ely.by account keyed by its uuid, and select it."""
        account = dict(profile)
        account["id"] = account.get("uuid") or uuid.uuid4().hex
        account["kind"] = "elyby"
        self.accounts = [a for a in self.accounts if a.get("id") != account["id"]]
        self.accounts.append(account)
        self.selected = account["id"]
        self.save()
        return account

    def update(self, account):
        for i, existing in enumerate(self.accounts):
            if existing.get("id") == account.get("id"):
                self.accounts[i] = account
                self.save()
                return account
        return self.add(account)

    def remove(self, account_id):
        self.accounts = [a for a in self.accounts if a.get("id") != account_id]
        if self.selected == account_id:
            self.selected = OFFLINE_ID
        self.save()

    def labels(self):
        """UI values: the offline entry first, then every saved Ely.by account."""
        items = [(OFFLINE_ID, "Без аккаунта (оффлайн)")]
        items += [(a["id"], f"Ely.by: {a.get('username', '?')}") for a in self.accounts]
        return items
