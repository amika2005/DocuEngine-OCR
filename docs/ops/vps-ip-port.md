# DocuEngine on the same Xserver VPS as Sonasu PM (IP:port, no domain)

Same idea as the first PM smoke: `http://<vps-ip>:8100` for PM, **`http://<vps-ip>:8200` for DocuEngine**.

Do **not** change `opervia.net` Caddy. Do **not** bind DocuEngine to 80/443. Do **not** use the `sonasu_pm` database. Do **not** `docker compose down -v`.

## What this stack is

| | Sonasu PM | DocuEngine VPS |
|---|---|---|
| Directory | `/opt/sonasu-pm` | `/opt/docuengine` |
| Compose project | `sonasu-pm` | `docuengine` |
| Database | `sonasu_pm` | `docuengine` |
| Public URL (test) | `:8100` or Caddy `opervia.net` | `:8200` HTTP |
| GPU worker | — | **off** (Xserver has no GPU) |
| OCR | — | `OCR_ENGINE=mock` until CPU models are installed |

Mock OCR is enough to log in, create a company, upload a file, and see the pipeline complete. Real Japanese OCR needs models + `ppocrv5-cpu` later (RAM-heavy).

## On the VPS

Firewall: allow **TCP 8200** (same place you opened 8100). Leave 80/443 for Caddy.

```bash
# CRLF from a Windows checkout breaks #!/bin/sh
sed -i 's/\r$//' /opt/docuengine/docker/vps-entrypoint.sh

cd /opt/docuengine
git pull   # this branch must contain docker/docker-compose.vps.yml

cp docker/.env.vps.example docker/.env.vps
nano docker/.env.vps   # SECRET_KEY, POSTGRES_PASSWORD, SUPERADMIN_PASSWORD

docker compose -f docker/docker-compose.vps.yml --env-file docker/.env.vps up -d --build
```

If the repo is not on the VPS yet:

```bash
git clone https://github.com/amika2005/DocuEngine-OCR.git /opt/docuengine
# checkout the branch that has docker-compose.vps.yml if it is not on main yet
```

Check:

```bash
docker compose -f docker/docker-compose.vps.yml --env-file docker/.env.vps ps
curl -sS http://127.0.0.1:8200/api/v1/health
# browser: http://<vps-public-ip>:8200/
```

Login: `SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD` from `docker/.env.vps`. Change the password after first login.

## Hard rules

- Never set `POSTGRES_DB=sonasu_pm` here.
- Never run DocuEngine `alembic` against the PM compose DB.
- Updates: `git pull` then `up -d --build`. Not `down -v`.
- PM Caddyfile (`opervia.net, www.opervia.net`) stays as-is.

## Connect PM later (optional)

On DocuEngine: company admin → issue integration token (`deint_...`), share a document.

On `/opt/sonasu-pm/deploy/docker/.env`:

```
DOCUENGINE_CONNECTOR_ENABLED=true
DOCUENGINE_BASE_URL=http://<vps-ip>:8200
DOCUENGINE_INTEGRATION_TOKEN=deint_...
```

Rebuild **only** the PM app container (`down -v` still forbidden). Prefer attaching the PM container to the `docuengine` Docker network and using `http://api:8000` so the token never goes via the public IP.
