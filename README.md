# Datacom Internal Employee Portal — Kudos System

A lightweight, spec-driven web application that enables employees to give public kudos to colleagues, complete with role-based content moderation for administrators.

Built with **Python 3 (standard library only — zero external dependencies)**, **SQLite**, and vanilla **HTML/CSS/JS**.

## Features

- **Give Kudos**: Select a colleague from the directory, write a message (max 500 characters), and submit.
- **Validation & Safety**: Prevents empty messages, self-kudos, duplicate submissions within 5 minutes, and sanitizes HTML input.
- **Public Dashboard Feed**: Paginated feed displaying recent visible kudos.
- **Admin Content Moderation**: Administrators can hide inappropriate kudos (recording `is_visible`, `moderated_by`, `moderated_at`, and `reason_for_moderation`), restore hidden items, or permanently delete them.

## Quick Start

1. **Run the application**:
   ```bash
   python3 app.py
   ```
2. Open **http://127.0.0.1:8000** in your browser.
3. Use the **Signed in as** dropdown in the top right to switch between regular employees and **Jordan Taylor (admin)** to test moderation controls.

## Running Tests

```bash
python3 -m unittest discover -s tests -v
```

## API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/users` | List all employees |
| `GET` | `/api/kudos?page=1&per_page=10&include_hidden=false` | Get paginated kudos feed (`include_hidden=true` requires admin) |
| `POST` | `/api/kudos` | Create a new kudos message (requires `X-User-Id` header) |
| `PATCH` | `/api/kudos/{id}/moderate` | Hide or restore a kudos message (admin only) |
| `DELETE` | `/api/kudos/{id}` | Permanently delete a kudos message (admin only) |

## Pushing to GitHub (Task 2 Step 4)

Copy your `SPECIFICATION.md` into this folder, then run:

```bash
git init
git add .
git commit -m "Initial commit: Kudos system with spec and moderation"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo-name>.git
git push -u origin main
```
