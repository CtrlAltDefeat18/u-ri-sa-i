# us — deploy

The free stack, all from your GitHub Student Pack:

- **App + database:** DigitalOcean App Platform + an attached Dev Postgres, paid from your **$200 / 1-year** student credit. Push to GitHub → it redeploys itself. Free HTTPS.
- **Photos:** Cloudinary, free tier (25 GB). No reason to spend credit on image storage.
- **Domain:** a subdomain off `lurniqhub.tech`, or claim the free Namecheap `.me` in the pack.
- **Dev environment (optional but handy):** GitHub Codespaces — a full browser IDE, so you're not stuck on lab-machine limits. Copilot Pro is free too.

Claim the pack first at **education.github.com/pack** (student card or fee statement if your university email doesn't auto-verify).

---

## 1. Cloudinary (photo files) — 2 minutes
1. cloudinary.com → note your **Cloud name**.
2. **Settings → Upload → Add upload preset.** Signing mode **Unsigned**, name it `us_unsigned`. Save.
3. Open `templates/index.html`, find the `cloudinary` block in CONFIG, set `cloudName` and `uploadPreset`.

(Photos now live in *your* database behind the login; Cloudinary only stores the image file. No public list endpoint, unlike the early static version.)

## 2. Put the code on GitHub
From Cloud Shell or Codespaces, in the project folder:
```bash
git init && git add . && git commit -m "us"
# create an EMPTY repo on github.com first, then:
git remote add origin https://github.com/<you>/us.git
git branch -M main && git push -u origin main
```
The included `.gitignore` keeps your `.env` and the local `us.db` out of the repo — never commit those.

## 3. DigitalOcean App Platform
1. Claim the DO credit from your Student Pack page (links to a fresh DO account — you add a card for identity only, you won't be charged inside the credit).
2. DO dashboard → **Create → Apps** → connect GitHub → pick the `us` repo → branch `main`, autodeploy on.
3. It detects Python automatically. Confirm the **run command** is:
   `gunicorn --bind 0.0.0.0:8080 --worker-tmp-dir /dev/shm app:app`
   (the `Procfile` already sets this).
4. **Add the database:** in the app, **Create/Attach Database → Dev Database → Create and Attach.** This injects a `DATABASE_URL` env var on its own and redeploys — the app reads it directly, so Postgres just works.
5. **Environment variables** (App → Settings → your service → Environment Variables) — mark each *encrypted*:
   - `SECRET_KEY` — long random string: `python3 -c "import secrets; print(secrets.token_hex(32))"`
   - `USER1_NAME`, `USER1_PASS` — you
   - `USER2_NAME`, `USER2_PASS` — her
   - leave `FLASK_ENV` unset (production → secure cookies on)
6. Deploy. Open the `*.ondigitalocean.app` URL, log in with one of the names/passwords above.

## 4. Your domain
App → **Settings → Domains → Add Domain** → `us.lurniqhub.tech`. DO shows a CNAME target; add that CNAME in Cloudflare DNS (set it **DNS only**, grey cloud, so DO manages the certificate). A few minutes later it's live with HTTPS. Send her that link.

---

## Running it locally first (Cloud Shell / Codespaces)
```bash
pip install -r requirements.txt
cp .env.example .env        # then edit the values
python app.py               # → port 8080, open the Web Preview
```
Locally it uses a SQLite file (`us.db`); production uses the attached Postgres. Same code.

## Day to day
- **Songs:** paste any Spotify link (track, album, or playlist) into the box on the site — either of you, no code.
- **Photos:** the upload button; they're stored on Cloudinary, listed from your DB.
- **The busy cards, names, dates, time zones:** edit the CONFIG block in `templates/index.html`, commit, push — it redeploys.

## A straight note on privacy
This is a real private app now: login-gated, two accounts, server-side sessions. The one soft spot is that Cloudinary image *files* are reachable by URL if someone has the exact link (unsigned upload). For a couple's wall that's a fair trade for free + simple. If you ever want the images themselves sealed, that's Cloudinary signed/authenticated delivery — a later step, not needed for v1.
