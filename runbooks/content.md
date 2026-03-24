# runbooks/content.md

## ÉTAT DU SYSTÈME

```bash
# Poller actif ?
docker exec openclaw-openclaw-gateway-1 sh -c "ps aux | grep 'CONTENT_FACTORY/poller' | grep -v grep"

# Dernière publication
tail -5 ~/openclaw/workspace/state/content_poller.log | grep -iE 'publié|published|✅'

# Drafts disponibles
cat ~/openclaw/workspace/state/drafts.json | python3 -c "import json,sys; print(f'Drafts: {len(json.load(sys.stdin))}')"

# Logs
docker exec openclaw-openclaw-gateway-1 sh -c "tail -20 /home/node/.openclaw/workspace/state/content_poller.log"
```

## RELANCER LE POLLER

```bash
docker exec openclaw-openclaw-gateway-1 sh -c "pkill -f 'CONTENT_FACTORY/poller.js'"
sleep 2
docker exec -d openclaw-openclaw-gateway-1 sh -c "
node /home/node/.openclaw/workspace/CONTENT_FACTORY/poller.js \
  >> /home/node/.openclaw/workspace/state/content_poller.log 2>&1"
```

## DIAGNOSTIQUER ARRÊT PUBLICATIONS

```bash
# 1. Poller tourne ?
docker exec openclaw-openclaw-gateway-1 sh -c "ps aux | grep 'CONTENT_FACTORY/poller' | grep -v grep"
# 2. Logs poller
docker exec openclaw-openclaw-gateway-1 sh -c "tail -20 /home/node/.openclaw/workspace/state/content_poller.log"
# 3. Logs scraper horaire
docker exec openclaw-openclaw-gateway-1 sh -c "tail -10 /home/node/.openclaw/workspace/state/hourly_scraper.log"
# 4. Drafts disponibles ?
cat ~/openclaw/workspace/state/drafts.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Drafts: {len(d)}')"
```
