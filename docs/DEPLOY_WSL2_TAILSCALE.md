# Deploy on WSL2 Ubuntu + Tailscale

This guide targets Ubuntu running inside WSL2 and exposes Home-Cloud-Server through Tailscale.

## 1) Prerequisites

- Windows 11 or recent Windows 10 with WSL2 enabled
- Ubuntu installed in WSL2
- A Tailscale account
- Repository already cloned in WSL2

## 2) Enable systemd in WSL2

Edit `/etc/wsl.conf` inside Ubuntu:

```ini
[boot]
systemd=true
```

Then restart WSL from PowerShell:

```powershell
wsl --shutdown
```

Start Ubuntu again and verify:

```bash
systemctl is-system-running
```

## 3) Run one-shot deployment script

From repository root:

```bash
sudo ./scripts/setup_wsl2_tailscale.sh
```

The script will:

- install Python/nginx/Tailscale dependencies
- create `.venv` and install Python packages
- prepare `/srv/home-cloud-storage`
- create `/etc/home-cloud/home-cloud.env`
- install and start `home-cloud` (systemd)
- install and start nginx

## 4) Join the tailnet

```bash
sudo tailscale up
tailscale ip -4
```

Use the printed Tailnet IPv4 address to access the service from other Tailnet devices:

```text
http://<tailscale-ip>/
```

## 5) Important paths

- App directory: repository root
- Runtime env file: `/etc/home-cloud/home-cloud.env`
- Storage root: `/srv/home-cloud-storage`
- systemd unit: `/etc/systemd/system/home-cloud.service`
- nginx config: `/etc/nginx/sites-available/home-cloud`

## 6) Service operations

```bash
sudo systemctl status home-cloud --no-pager
sudo systemctl restart home-cloud
sudo journalctl -u home-cloud -f

sudo systemctl status nginx --no-pager
sudo nginx -t
```

## 6.1) Optional: Load balancing (multi-instance)

If you want real load balancing, run multiple Gunicorn instances on different ports
and switch nginx to the load‑balancing template.

### Step A: Install the template unit

```bash
sudo cp /path/to/repo/deploy/systemd/home-cloud@.service.template /etc/systemd/system/home-cloud@.service
sudo systemctl daemon-reload
```

### Step B: Start multiple instances

```bash
sudo systemctl disable --now home-cloud
sudo systemctl enable --now home-cloud@5000 home-cloud@5001 home-cloud@5002 home-cloud@5003
```

### Step C: Switch nginx to the LB config

```bash
sudo cp /path/to/repo/deploy/nginx/home-cloud-lb.conf.template /etc/nginx/sites-available/home-cloud
sudo nginx -t
sudo systemctl restart nginx
```

Adjust the port list to match your instance count, and edit the upstream list in
`home-cloud-lb.conf.template` accordingly.

### Quick auto-setup

If you want the script to pick an instance count based on CPU cores:

```bash
sudo ./scripts/enable_lb.sh
```

Health checks and rolling restarts:

```bash
sudo ./scripts/healthcheck_instances.sh
sudo ./scripts/rolling_restart.sh
```

## 7) First-login security checklist

- change default admin password immediately
- set a strong `SECRET_KEY` in `/etc/home-cloud/home-cloud.env`
- optionally limit nginx access to Tailnet range (`100.64.0.0/10`)
- back up `/srv/home-cloud-storage/home-cloud/production.db`

## 8) If systemd is not available in WSL2

If your environment cannot run systemd, run with Gunicorn manually:

```bash
source .venv/bin/activate
export APP_CONFIG=production
export SECRET_KEY="replace_me"
export USE_HTTPS=false
export BASE_STORAGE_PATH="/srv/home-cloud-storage"
gunicorn --workers 2 --threads 4 --bind 127.0.0.1:5000 wsgi:app
```

nginx config can still be reused from `deploy/nginx/home-cloud.conf.template`.
