#!/usr/bin/env bash
# Заводит в Grafana Cloud contact point (Telegram владельца) и правила алертов
# через Alerting Provisioning API (free-тариф не поддерживает файловый provisioning).
#
# Требуемое окружение:
#   GRAFANA_URL            — https://<stack>.grafana.net
#   GRAFANA_SA_TOKEN       — Service Account token (роль Editor; если 403 — Admin)
#   TELEGRAM_API_TOKEN     — токен бота (для contact point)
#   OWNER_CHAT_ID          — chat_id владельца
#   METRICS_DS_UID         — uid datasource метрик (например, grafanacloud-prom)
#
# Идемпотентно: папка/contact point/группы правил создаются или обновляются.
# Запуск: uv run --with pyyaml -- bash deploy/grafana/provision.sh
set -euo pipefail

: "${GRAFANA_URL:?нужен GRAFANA_URL}"
: "${GRAFANA_SA_TOKEN:?нужен GRAFANA_SA_TOKEN}"
: "${TELEGRAM_API_TOKEN:?нужен TELEGRAM_API_TOKEN}"
: "${OWNER_CHAT_ID:?нужен OWNER_CHAT_ID}"
: "${METRICS_DS_UID:?нужен METRICS_DS_UID}"

DIR="$(cd "$(dirname "$0")" && pwd)"

python3 - "$DIR/alerts/rules.yaml" <<'PY'
import json
import os
import sys
import urllib.error
import urllib.request

import yaml

URL = os.environ["GRAFANA_URL"].rstrip("/")
TOKEN = os.environ["GRAFANA_SA_TOKEN"]
DS_UID = os.environ["METRICS_DS_UID"]
TG_TOKEN = os.environ["TELEGRAM_API_TOKEN"]
CHAT_ID = os.environ["OWNER_CHAT_ID"]

FOLDER_TITLE = "JobPilot"
FOLDER_UID = "jobpilot"
CP_NAME = "owner-telegram"


def req(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        URL + path,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw.decode(errors="replace")


def die(step: str, status: int, resp) -> None:
    print(f"❌ {step}: HTTP {status}: {resp}")
    if status == 403:
        print("   Подсказка: роли Editor может не хватать на Alerting Provisioning API —")
        print("   поднимите роль service account до Admin и повторите.")
    sys.exit(1)


# ── 1. Папка для правил ────────────────────────────────────────────────
status, folders = req("GET", "/api/folders")
if status != 200:
    die("чтение папок", status, folders)
folder_uid = next((f["uid"] for f in folders if f["title"] == FOLDER_TITLE), None)
if folder_uid is None:
    status, created = req("POST", "/api/folders", {"title": FOLDER_TITLE, "uid": FOLDER_UID})
    if status != 200:
        die("создание папки", status, created)
    folder_uid = created["uid"]
    print(f"→ Папка {FOLDER_TITLE}: создана (uid={folder_uid})")
else:
    print(f"→ Папка {FOLDER_TITLE}: уже есть (uid={folder_uid})")

# ── 2. Contact point: create-or-update ─────────────────────────────────
status, cps = req("GET", "/api/v1/provisioning/contact-points")
if status != 200:
    die("чтение contact points", status, cps)
existing = next((c for c in cps if c.get("name") == CP_NAME), None)
payload = {
    "name": CP_NAME,
    "type": "telegram",
    "settings": {"bottoken": TG_TOKEN, "chatid": str(CHAT_ID)},
    "disableResolveMessage": False,
}
if existing:
    status, resp = req("PUT", f"/api/v1/provisioning/contact-points/{existing['uid']}", payload)
    if status not in (200, 202):
        die("обновление contact point", status, resp)
    print(f"→ Contact point {CP_NAME}: обновлён")
else:
    status, resp = req("POST", "/api/v1/provisioning/contact-points", payload)
    if status not in (200, 201, 202):
        die("создание contact point", status, resp)
    print(f"→ Contact point {CP_NAME}: создан")

# ── 3. Правила алертов из rules.yaml ───────────────────────────────────
text = open(sys.argv[1]).read().replace("${METRICS_DS_UID}", DS_UID)
doc = yaml.safe_load(text)
for grp in doc["groups"]:
    rules = []
    for r in grp["rules"]:
        data = []
        for item in r["data"]:
            model = dict(item["model"])
            model.setdefault("refId", item["refId"])
            data.append(
                {
                    "refId": item["refId"],
                    "relativeTimeRange": item.get("relativeTimeRange", {"from": 600, "to": 0}),
                    "datasourceUid": item["datasourceUid"],
                    "model": model,
                }
            )
        rules.append(
            {
                "uid": r["uid"],
                "title": r["title"],
                "condition": r["condition"],
                "data": data,
                "for": str(r.get("for", "0s")).replace("0m", "0s"),
                "noDataState": r.get("noDataState", "OK"),
                "execErrState": r.get("execErrState", "Error"),
                "labels": r.get("labels", {}),
                "annotations": r.get("annotations", {}),
                "folderUID": folder_uid,
                "ruleGroup": grp["name"],
            }
        )
    body = {"title": grp["name"], "folderUid": folder_uid, "interval": 60, "rules": rules}
    status, resp = req(
        "PUT", f"/api/v1/provisioning/folder/{folder_uid}/rule-groups/{grp['name']}", body
    )
    if status not in (200, 202):
        die(f"группа правил {grp['name']}", status, resp)
    print(f"→ Группа правил {grp['name']}: ok ({len(rules)} правила)")

print("✅ Готово. Проверка: Grafana → Alerting → Contact points → owner-telegram → Test.")
PY
