# runbooks/content.md — Opérations CONTENT_FACTORY

---

## VÉRIFIER L'ÉTAT DU SYSTÈME

```bash
# Poller content tourne ?
docker exec openclaw-openclaw-gateway-1 sh -c "
ps aux | grep 'CONTENT_FACTORY/poller' | grep -v grep \
  && echo '✅ Poller actif' || echo '❌ Poller arrêté'
"

# Dernier post publié
tail -3 ~/openclaw/workspace/state/content_publish_history.json \
  | python3 -c "
import json, sys
entries = json.load(sys.stdin) if sys.stdin.read(1) == '[' else []
" 2>/dev/null || \
cat ~/openclaw/workspace/state/content_publish_history.json \
  | python3 -m json.tool | tail -20

# Nombre de drafts disponibles
cat ~/openclaw/workspace/state/drafts.json \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'Drafts actifs : {len(d)}')
"

# Logs récents
docker exec openclaw-openclaw-gateway-1 sh -c "
tail -20 /home/node/.openclaw/workspace/state/content_poller.log
"
```

---

## REDÉMARRER LE CONTENT POLLER

```bash
# Arrêter
docker exec openclaw-openclaw-gateway-1 sh -c "
pkill -f 'CONTENT_FACTORY/poller.js' && echo 'Arrêté' || echo 'Déjà arrêté'
"

# Relancer
sleep 2
docker exec -d openclaw-openclaw-gateway-1 sh -c "
node /home/node/.openclaw/workspace/CONTENT_FACTORY/poller.js \
  >> /home/node/.openclaw/workspace/state/content_poller.log 2>&1
"

# Vérifier après 5s
sleep 5
docker exec openclaw-openclaw-gateway-1 sh -c "
ps aux | grep 'CONTENT_FACTORY/poller' | grep -v grep \
  && echo '✅ Poller relancé' || echo '❌ Échec relance'
"
```

---

## DIAGNOSTIQUER ARRÊT DES PUBLICATIONS

```bash
# 1. Poller tourne ?
docker exec openclaw-openclaw-gateway-1 sh -c "
ps aux | grep 'CONTENT_FACTORY/poller' | grep -v grep
"

# 2. Dernier log du poller
docker exec openclaw-openclaw-gateway-1 sh -c "
tail -30 /home/node/.openclaw/workspace/state/content_poller.log
"

# 3. Dernier log du scraper horaire
docker exec openclaw-openclaw-gateway-1 sh -c "
tail -20 /home/node/.openclaw/workspace/state/hourly_scraper.log
"

# 4. Des drafts sont disponibles ?
cat ~/openclaw/workspace/state/drafts.json \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'Drafts: {len(d)}')
for k, v in list(d.items())[:3]:
    print(f'  #{k}: {v.get(\"title\", \"\")[:50]}')
"

# 5. Articles en attente de sélection ?
cat ~/openclaw/workspace/state/waiting_selection.json \
  2>/dev/null | python3 -m json.tool | head -10 \
  || echo "Pas de sélection en attente"

# 6. Offset Telegram OK ?
cat ~/openclaw/workspace/state/poller_offset.json \
  2>/dev/null | python3 -m json.tool || echo "Offset absent"
```

---

## VÉRIFIER LES SOURCES RSS

```bash
# Tester une source RSS manuellement
docker exec openclaw-openclaw-gateway-1 node -e "
const https = require('https');
const url = 'https://cointelegraph.com/rss';
https.get(url, (res) => {
  console.log('Status:', res.statusCode, url);
}).on('error', (e) => console.error('Erreur:', e.message));
"
```

Sources à vérifier si le scraper ne trouve plus d'articles :
- CoinTelegraph : `https://cointelegraph.com/rss`
- CoinDesk : `https://coindesk.com/arc/outboundfeeds/rss/`
- The Block : `https://theblock.co/rss.xml`
- Decrypt : `https://decrypt.co/feed`
- Cryptoast : `https://cryptoast.fr/feed/`
- JournalDuCoin : `https://journalducoin.com/feed/`
