# Pronostiqueurs All-Star

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![Django](https://img.shields.io/badge/Django-5.2-green?logo=django)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue?logo=postgresql)
![Deployed on Render](https://img.shields.io/badge/Deployed-Render-46E3B7?logo=render)

Plateforme web de **pronostics e-sport** développée avec Django et TailwindCSS.  
Les utilisateurs suivent les tournois, prédisent les résultats (vainqueur, score exact, MVP)
et se connectent via compte classique ou Google OAuth.

**[Voir la démo en ligne →](https://pronostiqueurs-all-star.onrender.com/)**

---

## Fonctionnalités

- Authentification classique + Google OAuth (django-allauth)
- Suivi des tournois et prédictions (vainqueur, score exact, MVP)
- Import automatique des données depuis Liquipedia (BeautifulSoup + mwparserfromhell)
- UI moderne : TailwindCSS, mode sombre, popups animés
- Administration Django personnalisée (Jazzmin)
- Déploiement Render + PostgreSQL 16

---

## Stack technique

| Couche | Technologies |
|--------|-------------|
| Backend | Django 5.2, django-allauth, Gunicorn |
| Frontend | TailwindCSS (django-tailwind), Whitenoise |
| Base de données | PostgreSQL 16 (prod), SQLite (dev) |
| Scraping | BeautifulSoup4, mwparserfromhell (Liquipedia) |
| DevOps | Docker Compose, Render, python-decouple |

---

## Architecture

```
pronostiqueurs/
├── esport/        # App principale : logique métier e-sport
├── tournaments/   # Gestion des tournois
├── teams/         # Équipes
├── champions/     # Joueurs / champions
├── users/         # Authentification & profils
├── roles/         # Gestion des rôles utilisateurs
└── myfirstsite/   # Configuration Django (settings, urls)
```

---

## Installation

**Prérequis :** Python 3.12+, PostgreSQL (ou Docker)

```bash
git clone https://github.com/hugowalledev/DjangoWebsite.git
cd DjangoWebsite
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Créer un fichier `.env` à la racine :

```env
SECRET_KEY=your-secret-key
DEBUG=True
DATABASE_URL=postgres://user:password@localhost:5432/pronostiqdb
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

```bash
python manage.py migrate
python manage.py runserver
```

**Avec Docker (base PostgreSQL uniquement) :**

```bash
docker compose up -d db
```

---

## Aperçu

<img width="1917" height="914" alt="image" src="https://github.com/user-attachments/assets/d0f48974-e5c5-4f72-b2e2-c685df41d23a" />
<img width="1917" height="913" alt="image" src="https://github.com/user-attachments/assets/746f3f71-710e-4d16-8034-fa6ccff63a77" />
<img width="1918" height="911" alt="image" src="https://github.com/user-attachments/assets/d9994627-bf2f-4f5c-b9ea-66cce38cac22" />
<img width="1918" height="908" alt="image" src="https://github.com/user-attachments/assets/b3f0fbf4-ce2e-4d32-a18b-40cd3f855c17" />

---

## Auteur

**Hugo Walle** — [github.com/hugowalledev](https://github.com/hugowalledev)
