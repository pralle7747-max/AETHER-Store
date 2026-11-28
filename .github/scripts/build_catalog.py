"""Erzeugt catalog.json für den AETHER Store.

Läuft als GitHub Action (mit GITHUB_TOKEN → 5.000 API-Abrufe/Std.) und sammelt
alle Repos, Releases, Assets (inkl. SHA256-Digest) und Screenshot-Listen des
Aether-Kontos ein. Der Store lädt dann nur diese eine Datei über
raw.githubusercontent.com – ohne API-Limit.

Bewusst nur Rohdaten: Versionen, Beta-Kanal und Runtergenommen-Erkennung
berechnet der Store selbst.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

USER = os.environ.get("CATALOG_USER", "AetherSoftwareInc")
STORE_REPO = f"{USER}/AETHER-Store"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
API = "https://api.github.com"


def get(path):
    req = urllib.request.Request(API + path, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "AETHER-Store-Catalog",
        **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def pick_release(r):
    keep = ("tag_name", "name", "body", "html_url", "published_at", "created_at", "prerelease", "draft")
    out = {k: r.get(k) for k in keep}
    out["assets"] = [{k: a.get(k) for k in ("name", "size", "browser_download_url", "digest", "download_count")}
                     for a in r.get("assets") or []]
    return out


def main():
    repos = []
    page = 1
    while True:
        batch = get(f"/users/{USER}/repos?per_page=100&page={page}&sort=pushed") or []
        repos += batch
        if len(batch) < 100:
            break
        page += 1

    out_repos, store_latest = [], None
    for repo in repos:
        if repo.get("private") or repo.get("archived"):
            continue
        full = repo["full_name"]
        releases = [pick_release(r) for r in (get(f"/repos/{full}/releases?per_page=10") or []) if not r.get("draft")]
        if full.lower() == STORE_REPO.lower():
            store_latest = next((r for r in releases if not r["prerelease"]), None)
            continue
        shots = get(f"/repos/{full}/contents/screenshots") or []
        out_repos.append({
            **{k: repo.get(k) for k in ("name", "full_name", "description", "html_url", "homepage", "language",
                                        "topics", "stargazers_count", "pushed_at")},
            "releases": releases,
            "screenshots": [{"name": s["name"], "sha": s["sha"], "download_url": s["download_url"]}
                            for s in shots if isinstance(s, dict) and s.get("type") == "file"
                            and s["name"].lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm"))],
        })

    ann = {}
    try:
        ann = json.load(open("announcements.json", encoding="utf-8"))
    except (OSError, ValueError):
        pass
    catalog = {
        "schema": 1,
        "coming_soon": [c for c in ann.get("coming_soon", []) if isinstance(c, dict) and c.get("id")],
        "news": [n for n in ann.get("news", []) if isinstance(n, dict) and n.get("title")],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "user": USER,
        "repos": out_repos,
        "store_latest": store_latest,
    }
    new = json.dumps(catalog, ensure_ascii=False, indent=1)
    # Nur schreiben, wenn sich inhaltlich etwas geändert hat (Zeitstempel ignorieren)
    try:
        old = json.load(open("catalog.json", encoding="utf-8"))
        old.pop("generated_at", None)
        cmp = dict(catalog); cmp.pop("generated_at")
        if old == cmp:
            print("Keine Änderungen.")
            return 0
    except (OSError, ValueError):
        pass
    with open("catalog.json", "w", encoding="utf-8") as fh:
        fh.write(new + "\n")
    print(f"catalog.json geschrieben: {len(out_repos)} Repos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
