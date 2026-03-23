# MyProjectsManager 🚀

An open-source project and time management tool designed to track work hours, manage deadlines, and maintain a healthy balance between commercial and internal/pet projects.

## 🎯 Features (Planned)
* **Time Tracking:** Log hours spent on specific tasks and projects.
* **Deadline Management:** Keep track of upcoming project milestones.
* **Project Balancing:** Visualise the distribution of effort between commercial work and internal/pet projects.
* **PWA Data Integration:** Import and analyse data from Progressive Web Apps for extended productivity insights.

## 🛠️ Tech Stack
* **Language:** [Python 3.14](https://www.python.org/)
* **Framework:** [Django 6+](https://www.djangoproject.com/)
* **Database:** PostgreSQL (via Docker)
* **Environment & Package Management:** [uv](https://github.com/astral-sh/uv)

## 💻 Local Development Setup

To run this project locally, you will need Python 3.14+, `uv`, and Docker installed on your machine.

### 1. Clone the repository
```bash
git clone https://github.com/OleksanderShevchenko/MyProjectsManager.git
cd MyProjectsManager
```

### 2. Set up the environment and install dependencies
This project uses `uv` for lightning-fast dependency management.
```bash
uv sync
```

### 3. Start the Database
Copy the example environment file and update the variables if necessary:
```bash
cp .env.example .env
```
Generate new secret key for .env and put it to your .env
```bash
uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```
Update database settings:
 - If you use postgres database from docker - set parameters at start of .env
 - If you use cloud database - set its url.

To be able to import data from MS Project update PWA_URL in your .env

We use Docker to run PostgreSQL locally.
```bash
docker-compose up -d
```

### 4. Apply Migrations and Run the Server
```bash
uv run python manage.py migrate
uv run python manage.py runserver
```

## 🤝 Contributing
Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/OleksanderShevchenko/MyProjectsManager/issues).

## 📝 License
This project is open-source and available under the [MIT License](LICENSE).