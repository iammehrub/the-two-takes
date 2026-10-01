#!/usr/bin/env python3
"""Watch Daraz Bangladesh public deal pages for very-low-price deals.

This intentionally uses only publicly accessible pages and does not log in,
place orders, bypass rate limits, or attempt checkout automation.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "daraz_deals_state.json"
URLS = [
    "https://www.daraz.com.bd/tag/9-tk-all-products/",
    "https://www.daraz.com.bd/happy-hour/",
]
UA = "Mozilla/5.0 (compatible; TwoTakesDarazDealAlert/1.0)"
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
MAX_PRICE = 11
MIN_OLD_PRICE = 100


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"sent": []}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    state["sent"] = state.get("sent", [])[-500:]
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def money(text: str) -> float | None:
    if not text:
        return None
    m = re.search(r"(?:৳|Tk\.?|BDT\s*)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", text, re.I)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def products_from_html(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    found = {}

    # Product cards on Daraz pages commonly expose title, price and URL in
    # anchors/spans. JSON-LD is also checked when available.
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text())
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        for obj in stack:
            if not isinstance(obj, dict):
                continue
            if obj.get("@type") == "ItemList":
                for item in obj.get("itemListElement", []):
                    p = item.get("item", {}) if isinstance(item, dict) else {}
                    if isinstance(p, dict):
                        title = p.get("name")
                        url = p.get("url")
                        offers = p.get("offers", {})
                        price = money(str(offers.get("price", ""))) if isinstance(offers, dict) else None
                        if title and url and price is not None:
                            found[url] = {"title": title, "price": price, "old_price": None, "url": urljoin(base_url, url)}

    for a in soup.find_all("a", href=True):
        text = " ".join(a.stripped_strings)
        if not text:
            continue
        current = money(text)
        if current is None or current > MAX_PRICE:
            continue
        href = urljoin(base_url, a["href"])
        if "daraz.com.bd" not in href:
            continue
        title = text
        # Try nearby card text for an original/struck-through price.
        parent = a
        for _ in range(3):
            parent = parent.parent
            if not parent:
                break
            card_text = " ".join(parent.stripped_strings)
            prices = re.findall(r"(?:৳|Tk\.?|BDT\s*)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", card_text, re.I)
            vals = []
            for p in prices:
                try:
                    vals.append(float(p.replace(",", "")))
                except ValueError:
                    pass
            old = max(vals) if vals else None
            if old and old >= MIN_OLD_PRICE:
                found[href] = {"title": title[:180], "price": current, "old_price": old, "url": href}
                break
        found.setdefault(href, {"title": title[:180], "price": current, "old_price": None, "url": href})

    return list(found.values())


def send_discord(deals: list[dict]) -> None:
    webhook = os.environ.get("DISCORD_ALERTS_WEBHOOK", "").strip()
    if not webhook:
        raise RuntimeError("DISCORD_ALERTS_WEBHOOK is missing.")

    lines = ["🛒 **Daraz low-price deal alert**"]
    for d in deals[:10]:
        old = f" ~~৳{d['old_price']:.0f}~~" if d.get("old_price") else ""
        lines.append(f"• **{d['title']}** — **৳{d['price']:.0f}**{old}\n{d['url']}")
    payload = {"content": "\n".join(lines)}
    r = requests.post(webhook, json=payload, timeout=(10, 20))
    r.raise_for_status()


def main() -> None:
    state = load_state()
    sent = set(state.get("sent", []))
    deals = []

    for url in URLS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=(10, 30))
            r.raise_for_status()
            deals.extend(products_from_html(r.text, url))
        except Exception as exc:
            print(f"Could not read {url}: {exc}")

    unique = {}
    for d in deals:
        if d["price"] <= MAX_PRICE:
            unique[d["url"]] = d

    fresh = []
    for d in unique.values():
        key = f"{d['url']}|{d['price']:.2f}"
        if key not in sent:
            fresh.append(d)
            sent.add(key)

    if fresh:
        send_discord(fresh)
        print(f"Sent {len(fresh)} Daraz deal(s).")
    else:
        print("No new <= ৳11 Daraz deals found.")

    state["sent"] = list(sent)
    save_state(state)


if __name__ == "__main__":
    main()
