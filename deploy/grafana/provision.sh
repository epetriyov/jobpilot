#!/usr/bin/env bash
# Заводит в Grafana Cloud contact point (Telegram владельца) и правила алертов
# через Alerting Provisioning API (free-тариф не поддерживает файловый provisioning).
#
# Требуемое окружение:
#   GRAFANA_URL            — https://<stack>.grafana.net
#   GRAFANA_SA_TOKEN       — Service Account token с ролью Editor/Admin
#   TELEGRAM_API_TOKEN     — токен бота (для contact point)
#   OWNER_CHAT_ID          — chat_id владельца
#   METRICS_DS_UID         — uid datasource метрик (Mimir/Prometheus) в стеке
#
# Идемпотентно: повторный прогон обновляет существующие объекты (PUT по uid).
set -euo pipefail

: "${GRAFANA_URL:?нужен GRAFANA_URL}"
: "${GRAFANA_SA_TOKEN:?нужен GRAFANA_SA_TOKEN}"
: "${TELEGRAM_API_TOKEN:?нужен TELEGRAM_API_TOKEN}"
: "${OWNER_CHAT_ID:?нужен OWNER_CHAT_ID}"
: "${METRICS_DS_UID:?нужен METRICS_DS_UID}"

DIR="$(cd "$(dirname "$0")" && pwd)"
AUTH=(-H "Authorization: Bearer ${GRAFANA_SA_TOKEN}" -H "Content-Type: application/json")

echo "→ Contact point owner-telegram"
curl -sS -X PUT "${GRAFANA_URL}/api/v1/provisioning/contact-points/owner-telegram" "${AUTH[@]}" -d @- <<JSON
{
  "uid": "owner-telegram",
  "name": "owner-telegram",
  "type": "telegram",
  "settings": { "bottoken": "${TELEGRAM_API_TOKEN}", "chatid": "${OWNER_CHAT_ID}" }
}
JSON

echo "→ Правила алертов (rules.yaml с подстановкой METRICS_DS_UID)"
# rules.yaml — в формате provisioning-файла; отправляем как import через API групп.
python3 - "$DIR/alerts/rules.yaml" <<'PY'
import os, sys, json, urllib.request, yaml  # noqa
path = sys.argv[1]
text = open(path).read().replace("${METRICS_DS_UID}", os.environ["METRICS_DS_UID"])
doc = yaml.safe_load(text)
url = os.environ["GRAFANA_URL"]
tok = os.environ["GRAFANA_SA_TOKEN"]
for grp in doc["groups"]:
    folder = grp["folder"]
    body = json.dumps({"interval": 60, "name": grp["name"], "rules": grp["rules"]}).encode()
    req = urllib.request.Request(
        f"{url}/api/v1/provisioning/folder/{folder}/rule-groups/{grp['name']}",
        data=body, method="PUT",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req)
        print(f"  ok: {grp['name']}")
    except Exception as e:  # noqa
        print(f"  warn: {grp['name']}: {e} (проверьте folder/датасорс вручную)")
PY

echo "✅ Готово. Проверка: Grafana → Alerting → Contact points → owner-telegram → Test."
