# 🎮 Pronostiqueurs All-Star

Plateforme web de **pronostics e-sport** développée avec **Django** et **TailwindCSS**.  
Les utilisateurs peuvent suivre les tournois, prédire les résultats et se connecter via un compte classique ou Google.  
Déployée sur **Render** avec base **PostgreSQL**.

---

## 🚀 Fonctionnalités
- 🔐 Authentification (classique + Google OAuth via Allauth)  
- 🏆 Suivi des tournois & prédictions (vainqueur, score exact, MVP)  
- 🎨 UI moderne (Tailwind, mode sombre, popups stylisés)  
- ☁️ Déploiement Render + PostgreSQL  

---

## 🛠️ Stack
- **Backend** : Django 5, Allauth  
- **Frontend** : TailwindCSS  
- **DB** : PostgreSQL (Render)  
- **Autres** : BeautifulSoup (import Liquipedia), Docker (dev)  

---

## ⚡ Installation
```bash
git clone https://github.com/tonpseudo/pronostiqueurs-all-star.git
cd pronostiqueurs-all-star
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Configurer un fichier .env avec :

SECRET_KEY=...
DATABASE_URL=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

📸 Aperçu

<img width="1917" height="914" alt="image" src="https://github.com/user-attachments/assets/d0f48974-e5c5-4f72-b2e2-c685df41d23a" />
<img width="1917" height="913" alt="image" src="https://github.com/user-attachments/assets/746f3f71-710e-4d16-8034-fa6ccff63a77" />
<img width="1918" height="911" alt="image" src="https://github.com/user-attachments/assets/d9994627-bf2f-4f5c-b9ea-66cce38cac22" />
<img width="1918" height="908" alt="image" src="https://github.com/user-attachments/assets/b3f0fbf4-ce2e-4d32-a18b-40cd3f855c17" />

👤 Auteur

Projet personnel réalisé par Hugo Walle




