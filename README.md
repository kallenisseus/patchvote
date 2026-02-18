# patchvote

## Run locally (dev)

### 1) Clone + enter repo
```bash
git clone https://github.com/kallenisseus/patchvote.git
cd patchvote

python -m venv .venv
.venv\Scripts\Activate

python -m pip install --upgrade pip
pip install -r requirements.txt


"DJANGO_DEBUG=1" | Out-File -Encoding utf8 .env
"DJANGO_SECRET_KEY=dev-only-change-me" | Out-File -Encoding utf8 -Append .env

python manage.py makemigrations
python manage.py migrate


python manage.py tailwind install
python manage.py tailwind start

# (activate venv again if needed)
python manage.py runserver

python manage.py fetch_tft_patches

Notes: `DJANGO_DEBUG`/`DJANGO_SECRET_KEY` from `.env`, and Tailwind is configured via the `theme` app. :contentReference[oaicite:0]{index=0}
::contentReference[oaicite:1]{index=1}
