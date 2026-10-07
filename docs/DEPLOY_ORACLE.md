# Deploy on Oracle Always Free (5–6 reviewers, $0)

Your Mac only needs **browser + one upload** (~200 MB streamed). Models and npm install happen **on the VM**.

## 1. Create the VM (browser only)

1. Sign up at [Oracle Cloud](https://www.oracle.com/cloud/free/) (Always Free tier).
2. Create an **Ampere A1** VM: Ubuntu 22.04 or 24.04, **2 OCPUs, 12 GB RAM** (or max free shape).
3. Add an **ingress rule**: TCP **22** (SSH) and **3000** (UI) from your reviewers’ IPs or `0.0.0.0/0` (use basic auth).
4. Note the **public IP** and SSH user (`ubuntu`).

## 2. Upload snapshot (from Mac, one stream — no extra tar file if you use upload script)

```bash
cd "AI Discovery Engine - Google Photos"
chmod +x scripts/upload-review-bundle.sh
./scripts/upload-review-bundle.sh 4ad39133-1e6c-4146-99a0-7d68dfe72020 ubuntu@YOUR_VM_IP
```

Or pack then scp:

```bash
./scripts/pack-review-bundle.sh
scp review-bundle-*.tar.gz ubuntu@YOUR_VM_IP:~/
# On VM: mkdir -p ~/review-bundle && tar -xzf review-bundle-*.tar.gz -C ~/review-bundle
```

## 3. Bootstrap on the VM (SSH once)

```bash
ssh ubuntu@YOUR_VM_IP
git clone https://github.com/smitshah769-lang/google-photos-discovery-engine.git
cd google-photos-discovery-engine
chmod +x scripts/vm-bootstrap.sh
export DISCOVERY_BASIC_PASSWORD='pick-a-strong-password'
./scripts/vm-bootstrap.sh
```

Save the printed **basic auth** password. UI uses same-origin API proxy (no port 8765 exposed to browsers).

## 4. HTTPS (recommended)

Install [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) on the VM:

```bash
cloudflared tunnel --url http://127.0.0.1:3000
```

Share the `https://*.trycloudflare.com` URL (or your custom domain). Reviewers enter basic auth when the app prompts (configure `NEXT_PUBLIC_DISCOVERY_BASIC_AUTH` in `.env` before `npm run build` if you change secrets).

## 5. Optional env on VM

| Variable | Purpose |
|----------|---------|
| `GROQ_API_KEY` / `HF_TOKEN` / `GEMINI_API_KEY` | LLM summaries in `.env` before restart |
| `DISCOVERY_BASIC_USER` / `DISCOVERY_BASIC_PASSWORD` | Protect API + UI |

Restart: `sudo systemctl restart discovery-api discovery-ui`

## Troubleshooting

- **First search slow**: reranker + embed models loading on VM (normal).
- **No data**: ensure `~/review-bundle/snapshot.db` and `data/rag/<run-id>.json` exist before bootstrap.
- **Dashboard empty**: check `sudo journalctl -u discovery-api -n 50`.

Run id for this snapshot: `4ad39133-1e6c-4146-99a0-7d68dfe72020`
