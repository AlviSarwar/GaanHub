# GaanHub 🎵

A Spotify-inspired music streaming platform built with Django.
Supports premium subscriptions, artist profiles, song purchases, playlists,
play history, notifications, and a wallet system for artists.

---

## Quick Start

### 1. Clone & Set Up Environment

```bash
git clone <repo-url>
cd gaanhub_fixed

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
cp .env.example .env
# Edit .env and set your SECRET_KEY, payment credentials, etc.
```

### 3. Run Migrations & Seed Demo Data

```bash
python manage.py migrate
python manage.py seed_demo       # Creates admin user + demo artist + genres
```

### 4. Start the Server

```bash
python manage.py runserver
```

Visit [http://127.0.0.1:8000](http://127.0.0.1:8000) — admin login: `admin / admin1234`

---

## Project Structure

```
gaanhub_fixed/
├── gaanhub/                    # Project config
│   ├── settings.py             # Settings (loads .env via python-dotenv)
│   ├── urls.py                 # Root URL router
│   ├── context_processors.py  # Injects premium_status into all templates
│   ├── wsgi.py
│   └── asgi.py
├── music/                      # Main app
│   ├── models.py               # All models (Song, Artist, Playlist, etc.)
│   ├── views.py                # All views
│   ├── urls.py                 # App-level URL patterns
│   ├── forms.py                # Forms with validation
│   ├── admin.py                # Admin configuration
│   ├── utils.py                # Shared helper functions
│   ├── migrations/
│   └── management/commands/
│       └── seed_demo.py        # Dev seeding command
├── users/                      # Auth / registration app
│   ├── views.py                # Register view
│   ├── urls.py
│   ├── signals.py              # Auto-creates UserProfile on User creation
│   └── apps.py
├── templates/                  # All HTML templates
├── static/css/                 # CSS (style.css)
├── media/                      # Uploaded files (songs, images)
├── .env                        # Local environment variables (not in git)
├── .env.example                # Template for .env
├── requirements.txt
└── manage.py
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | insecure default | Django secret key — **change in production** |
| `DJANGO_DEBUG` | `True` | Set to `False` in production |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated list of allowed hosts |
| `SSLCOMMERZ_STORE_ID` | `your_store_id` | SSLCommerz payment gateway ID |
| `SSLCOMMERZ_STORE_PASS` | `your_store_pass` | SSLCommerz password |

---

## Key Features

- 🎵 **Music Streaming** — Free and premium songs with access control
- 🎙 **Artist Mode** — Upload songs, track plays/earnings, manage your profile
- 💰 **Artist Wallet** — Royalties credited per stream + 80% of song sales
- ⭐ **Premium Plans** — Individual (৳199), Student (৳99), Family (৳349)
- 💳 **Manual Payments** — bKash, Nagad, Rocket, Bank Transfer + SSLCommerz hook
- 📋 **Playlists** — Create and manage personal playlists
- 🔔 **Notifications** — Real-time unread badge + notification feed
- 🔍 **Search** — Instant AJAX search + full results page
- 📊 **Charts** — Top played and most-liked songs by genre

---

## Production Checklist

- [ ] Set `DJANGO_DEBUG=False` in `.env`
- [ ] Set a strong `DJANGO_SECRET_KEY`
- [ ] Set `DJANGO_ALLOWED_HOSTS` to your domain
- [ ] Run `python manage.py collectstatic`
- [ ] Configure a proper database (PostgreSQL recommended)
- [ ] Set up a reverse proxy (Nginx + Gunicorn)
- [ ] Enable HTTPS and uncomment security headers in `settings.py`
- [ ] Replace SSLCommerz sandbox credentials with live ones
