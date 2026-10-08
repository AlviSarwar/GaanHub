# GaanHub

A Spotify-inspired music streaming platform built with Django, with artist
accounts, subscriptions, a wallet system and payment gateway support.

## Features

- User registration, login, profile editing and password change
- Browse songs by genre, search, and view charts
- Playlists: create, edit, and add songs
- Listening history and play history
- Artist pages, an artists directory, and "become an artist" upgrade
- Artist panel for managing uploaded music
- Premium subscriptions with a subscription dashboard
- Payment gateway selection and checkout
- Wallet dashboard and withdrawal requests for artists
- Notifications

## Tech Stack

- Python and Django
- HTML, CSS and Django templates
- SQLite (development)

## Project Structure

```
gaanhub/
  gaanhub/     project settings, urls, context processors
  music/       songs, playlists, artists, payments, wallet
  users/       authentication and profile views
  templates/   HTML templates
  static/      CSS
```

## Getting Started

```bash
git clone https://github.com/AlviSarwar/GaanHub.git
cd GaanHub/gaanhub

python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate

pip install -r requirements.txt

copy .env.example .env         # macOS/Linux: cp .env.example .env
# edit .env and fill in your own values

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000

## Configuration

Secrets are read from `.env`, which is never committed. See `.env.example` for
the variables you need. Use sandbox or test credentials for payment gateways
during development.

## Screenshots

Add screenshots to a `docs/` folder and link them here.

## Roadmap

- [ ] Automated tests and CI
- [ ] Recommendations
- [ ] Production deployment guide

## Contributors

- Alvi Sarwar
- Sabbeer60 ([@Sabbeer60](https://github.com/Sabbeer60))
- Al Shahriar Hossain Piyal

## License

MIT. See [LICENSE](LICENSE).

## Author

Alvi Sarwar - [Portfolio](https://alvisarwar.github.io/myportfolio/) - [LinkedIn](https://www.linkedin.com/in/mdalvisarwar)