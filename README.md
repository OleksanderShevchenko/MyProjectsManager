# MyProjectsManager 🚀

A modern, high-performance web application for weekly timesheet reporting, project tracking, and work-life balance management built with **Django 6**, **HTMX**, **Tailwind CSS**, and **PostgreSQL**.

---

## 🎯 Core Features

* **⚡ Weekly Timesheet Dashboard:**
  * Interactive weekly grid displaying assigned tasks grouped by project.
  * Real-time daily and weekly total calculation with instant feedback.
  * Work detail notes per cell with visual comment indicators and modal dialogs.
  * Per-week task visibility toggling (hide/collapse tasks not relevant for the current week).
  * Unsaved changes warning to prevent accidental data loss.
  * Complete timesheet lifecycle: `Draft` ➔ `Submitted for Approval` ➔ `Approved` (with `Recall to Draft` capabilities).

* **🔄 Reactive HTMX Interactions:**
  * Dynamic, server-driven UI updates using `django-htmx` without full-page reloads.
  * In-place timesheet approvals and rejections with inline live status alerts.
  * Single-click calendar day status updates with automatic outer-HTML swapping and HTMX indicators.

* **👥 Team Approvals & Management:**
  * Dedicated manager view grouping pending timesheets by engineer.
  * One-click approval and modal rejection workflow with feedback notes returned to the engineer.
  * Read-only timesheet inspection view for managers.

* **📅 Interactive Company Calendar:**
  * 12-month visual calendar grid managing corporate holidays, short days (7 hours), and free Mondays.
  * Weekday-aware rotation logic:
    * **Weekends:** `Standard Weekend ➔ Holiday ➔ Clear` (short days and free Mondays are strictly prohibited).
    * **Mondays:** `Standard Day ➔ Holiday ➔ Short Day ➔ Free Monday ➔ Clear`.
    * **Weekdays (Tue–Fri):** `Standard Day ➔ Holiday ➔ Short Day ➔ Clear`.
  * Comprehensive server-side validation preventing invalid day statuses.

* **📊 Yearly Overview & Metrics:**
  * 52-week status matrix with color-coded submission states.
  * Dynamic Chart.js doughnut chart allocating commercial vs. non-commercial working hours.

* **📈 Yearly Progress Board:**
  * Integral project health tracking (budget utilization percentage, timeline progress, over-budget highlights).
  * Task-level deadline monitoring with visual progress bars and "today" markers.

* **🌍 Internationalization (i18n):**
  * Multilingual support for English (`en`) and Ukrainian (`uk`).
  * One-click language switcher in both desktop and mobile navigation bars.
  * Fully compiled binary message catalogs (`.po` / `.mo`) translating all models, choices, and templates.

* **♿ Accessibility & WCAG AA Compliance:**
  * Semantic HTML landmarks, ARIA dialog roles, live regions, progressbar attributes, and screen-reader utilities (`sr-only`).
  * "Skip to main content" skip link and high-contrast visible keyboard focus rings across all interactive controls.

* **📱 Responsive Design:**
  * Fully responsive layouts crafted with a standalone Tailwind CSS build system.
  * Mobile drawer navigation with animated hamburger toggle and backdrop blur.

---

## 🛠️ Tech Stack & Architecture

* **Backend Framework:** [Django 6+](https://www.djangoproject.com/)
* **Runtime Language:** [Python 3.14](https://www.python.org/)
* **Reactivity:** [HTMX](https://htmx.org/) via [`django-htmx`](https://django-htmx.readthedocs.io/)
* **Frontend Styling:** [Tailwind CSS](https://tailwindcss.com/) (compiled via Node.js CLI)
* **Client-Side Scripts:** Vanilla modular ES6+ JavaScript (`totals.js`, `modal.js`, `task-hiding.js`, `unsaved-changes.js`, `navigation.js`, `yearly-chart.js`)
* **Charts:** [Chart.js](https://www.chartjs.org/) + `chartjs-plugin-datalabels`
* **Database:** [PostgreSQL](https://www.postgresql.org/) (running locally via Docker or cloud via `dj-database-url`)
* **Package & Environment Manager:** [uv](https://github.com/astral-sh/uv) (ultra-fast Python tooling)
* **Testing & Quality:** [pytest](https://docs.pytest.org/), [pytest-django](https://pytest-django.readthedocs.io/), [Ruff](https://astral.sh/ruff)

---

## 💻 Local Development Setup

### Prerequisites
* **Python 3.14+**
* **[uv](https://docs.astral.sh/uv/getting-started/installation/)**
* **[Docker](https://www.docker.com/)** and Docker Compose
* **Node.js v20+** and npm (for building Tailwind CSS)

---

### 1. Clone the Repository
```bash
git clone https://github.com/OleksanderShevchenko/MyProjectsManager.git
cd MyProjectsManager
```

---

### 2. Install Python Dependencies
```bash
uv sync
```

---

### 3. Install Node Dependencies (Tailwind CSS)
```bash
npm install
```

---

### 4. Configure Environment Variables
Copy the example configuration file:
```bash
cp .env.example .env
```
Generate a fresh Django secret key:
```bash
uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```
Open `.env` and set:
* `SECRET_KEY`: paste the generated key.
* `DB_SOURCE`: `local` to use the local Docker PostgreSQL database, or `cloud` to use `DATABASE_URL`.
* `POSTGRES_*`: credentials matching `docker-compose.yml`.

---

### 5. Start the PostgreSQL Container
```bash
docker-compose up -d
```

---

### 6. Apply Migrations & Initialize Groups
```bash
uv run python manage.py migrate
uv run python manage.py create_default_groups
```

---

### 7. Build Frontend Styles
You can compile Tailwind CSS once or run the watcher during development:
```bash
# One-time production build (minified)
npm run css:build

# Active development watch mode
npm run css:watch
```

---

### 8. Run the Development Server
```bash
uv run python manage.py runserver
```
Visit `http://127.0.0.1:8000/` in your browser.

---

## 🧪 Testing & Code Quality

The project includes an extensive test suite covering models, service layers, views, access control, HTMX partials, and business logic.

```bash
# Run all 87 tests with pytest
uv run pytest

# Run linter and formatting checks
uv run ruff check .
```

---

## 🌐 Localization (i18n)

The application supports English and Ukrainian out of the box.

* Translation files are located in `locale/<lang>/LC_MESSAGES/`.
* When adding new translated strings, update `locale/uk/LC_MESSAGES/django.po` and compile the binary catalog:
```bash
uv run python manage.py compilemessages
```

---

## 💾 Database Backup & Restore

### Method 1: Full PostgreSQL Dump (via Docker)
Creates a complete SQL dump of the container database (`myprojectsmanager_db`).

> **Note for Windows PowerShell users:** Wrap the command in `cmd /c` to prevent PowerShell from corrupting the `.sql` file encoding.

* **Backup:**
  ```bash
  cmd /c "docker exec -t myprojectsmanager_db pg_dump -U postgres projects_db > backup.sql"
  ```
* **Restore:**
  ```bash
  psql -U postgres -d projects_db -f backup.sql
  ```

### Method 2: Django Data Export (JSON)
Database-agnostic export ideal for testing and environment migration.

* **Backup:**
  ```bash
  uv run python -X utf8 manage.py dumpdata -o datadump.json
  ```
* **Restore:**
  ```bash
  uv run python manage.py loaddata datadump.json
  ```

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [Issues page](https://github.com/OleksanderShevchenko/MyProjectsManager/issues).

---

## 📝 License

This project is open-source and available under the [MIT License](LICENSE).