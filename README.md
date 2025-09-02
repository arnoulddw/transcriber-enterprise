# Transcriber Platform

**A powerful, self-hostable transcription solution designed for small to medium-sized businesses (SMBs), teams and individuals who need full control over their data and transcription workflow.**

Transcriber Platform turns audio into accurate organized text through a user-friendly web interface. Upload audio files and get transcriptions from top-tier APIs like **AssemblyAI**, **OpenAI Whisper** and **OpenAI GPT-4o Transcribe**. It intelligently handles large files, supports single and multi-user modes and includes powerful administrative tools for managing users, costs and custom AI workflows.

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen)](https://github.com/arnoulddw/transcriber-platform)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

![Screenshot of the Transcriber Platform App](transcriber-platform-screenshot.png)

## Table of Contents

-   [✨ Key Features](#-key-features)
-   [🚀 Quick Start (Docker)](#-quick-start-docker)
-   [🔧 Installation & Configuration](#-installation--configuration)
-   [💻 Usage Guide](#-usage-guide)
-   [🛠️ For Developers](#️-for-developers)
-   [🤔 Troubleshooting](#-troubleshooting)
-   [📜 License](#-license)

## ✨ Key Features

### Core Functionality
-   **Multiple Transcription APIs:** Choose from AssemblyAI, OpenAI Whisper or OpenAI GPT-4o Transcribe.
-   **Large File Handling:** Automatically splits files over 25MB into chunks for seamless processing.
-   **AI-Powered Title Generation:** Automatically generates a concise title for each transcription.
-   **Custom AI Workflows:** Execute custom prompts (ex. summarize, extract action items) on transcribed text using LLMs like Google Gemini or OpenAI models.
-   **Flexible Language Options:** Select the audio language manually or use automatic detection.
-   **Context Prompting:** Improve accuracy for jargon or specific names by providing context hints to OpenAI models.

### User Experience
-   **Intuitive Web Interface:** Clean and simple UI for uploading files, managing history and running workflows.
-   **Comprehensive History:** View, copy, download (.txt) and delete past transcriptions.
-   **Asynchronous Processing:** Long tasks run in the background, keeping the UI fast and responsive.
-   **Internationalization (i1n):** Multi-language support (English, Spanish, French, Dutch).

### Multi-User & Admin Features
-   **Dual Deployment Modes:**
    -   `single`: Simple, no-login mode using global API keys. Perfect for personal use.
    -   `multi`: Full-featured user mode with registration, login and individual API key management.
-   **Secure User Authentication:** Supports username/password, Google Sign-In and password resets.
-   **Role-Based Access Control (RBAC):** Granularly control permissions for features, API usage and more.
-   **Smart API Key Handling:** If a user has permission to manage keys, their personal key is used. Otherwise, the system seamlessly falls back to the global API key, ensuring uninterrupted service.
-   **Comprehensive Admin Panel:**
    -   **User Management:** View and manage all users and their usage.
    -   **Cost & Usage Analytics:** Detailed dashboards to track transcription minutes, workflow costs and API expenses by user and role.
    -   **System-wide Templates:** Create and manage workflow templates available to all users.
    
    

## 🚀 Quick Start (Docker)

Get the platform running in under 5 minutes. This is the recommended method.

**Prerequisites:** [Docker](https://www.docker.com/get-started) and [Docker Compose](https://docs.docker.com/compose/install/).

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/arnoulddw/transcriber-platform.git
    cd transcriber-platform
    ```

2.  **Configure Your Environment**
    Copy the example environment file and edit it with your details.
    ```bash
    cp .env.example .env
    nano .env 
    ```
    -   **Crucially, you must set:** `SECRET_KEY`, your API keys (`OPENAI_API_KEY`, etc.) and `MYSQL_PASSWORD`, `MYSQL_USER`, `MYSQL_DB`.
    -   For multi-user mode, also set `ADMIN_USERNAME` and `ADMIN_PASSWORD` to create your admin account.

3.  **Build and Run**
    ```bash
    docker-compose up -d --build
    ```

4.  **Access the App**
    Open your browser and go to `http://localhost:5004` (or the `APP_PORT` you set in `.env`). The database will be initialized automatically on the first run.

## 🔧 Installation & Configuration

This section provides more detailed setup instructions.

### Prerequisites

-   **API Keys:** You need API keys for the services you plan to use:
    -   [AssemblyAI](https://www.assemblyai.com/)
    -   [OpenAI](https://platform.openai.com/) (for Whisper, GPT-4o Transcribe and LLM workflows)
    -   [Google Gemini](https://ai.google.dev/) (for title generation and LLM workflows)
-   **Docker & Docker Compose:** Required for the recommended installation method.
-   **Google Client ID (Optional):** Required for Google Sign-In in `multi` user mode.
-   **Python 3.9+:** Required for local development without Docker.

### Environment Variables

The application is configured using environment variables in a `.env` file. The table below lists all available options.

<details>
<summary><strong>Click to expand all environment variables</strong></summary>

| Variable | Description | Default |
|---|---|---|
| **Core Application** | | |
| `SECRET_KEY` | **CRITICAL:** A strong, random key for session security. **Must be set.** | (none) |
| `DEPLOYMENT_MODE` | `single` (no login) or `multi` (user accounts). | `multi` |
| `TZ` | Timezone for the application (ex. `UTC`, `Europe/Paris`). | `UTC` |
| `APP_PORT` | Port on which the app is accessible on the host machine. | `5004` |
| `LOG_LEVEL` | Application logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). | `INFO` |
| **API Keys (Global Fallback)** | | |
| `ASSEMBLYAI_API_KEY` | Your API key for AssemblyAI. | (none) |
| `OPENAI_API_KEY` | Your API key for OpenAI (Whisper, GPT-4o Transcribe, LLMs). | (none) |
| `GEMINI_API_KEY` | Your API key for Google Gemini (Title Generation, LLMs). | (none) |
| **Default Settings** | | |
| `DEFAULT_TRANSCRIPTION_PROVIDER` | Default transcription API on load (`assemblyai`, `whisper`, `gpt-4o-transcribe`). | `gpt-4o-transcribe` |
| `DEFAULT_LLM_PROVIDER` | Default LLM for tasks like title generation (`gemini`, `openai`). | `gemini` |
| `DEFAULT_LANGUAGE` | Default transcription language on load (`auto`, `en`, `es`, etc.). | `auto` |
| `SUPPORTED_LANGUAGE_CODES` | Comma-separated language codes to show in the UI (ex. `en,nl,fr,es`). | `en,nl,fr,es` |
| **Database (MySQL)** | | |
| `MYSQL_HOST` | Hostname for the MySQL server. Use `mysql` for Docker Compose. | `localhost` |
| `MYSQL_PORT` | Port for the MySQL server. | `3306` |
| `MYSQL_USER` | Username for MySQL connection. **Must be set.** | (none) |
| `MYSQL_PASSWORD` | Password for MySQL connection. **Must be set.** | (none) |
| `MYSQL_DB` | Name of the MySQL database. **Must be set.** | (none) |
| `MYSQL_ROOT_PASSWORD` | Root password for the MySQL service (used by Docker Compose). | (none) |
| `MYSQL_HOST_PORT` | Host port to map to MySQL's internal port (for external access). | `3307` |
| `MYSQL_POOL_SIZE` | Number of connections in the MySQL connection pool. | `10` |
| **Multi-User Mode** | | |
| `ADMIN_USERNAME` | Username for the initial admin account (created on first run). | `admin` |
| `ADMIN_PASSWORD` | Password for the initial admin account. **Must be set for admin creation.** | (none) |
| `ADMIN_EMAIL` | Email for the initial admin account. | (none) |
| `GOOGLE_CLIENT_ID` | Your Google OAuth 2.0 Client ID for Google Sign-In. | (none) |
| **Email (for Password Resets)** | | |
| `MAIL_SERVER` | SMTP server for sending emails. | (none) |
| `MAIL_PORT` | SMTP server port. | `587` |
| `MAIL_USE_TLS` | Whether to use TLS for SMTP (`true`, `false`). | `true` |
| `MAIL_USERNAME` | Username for SMTP authentication. | (none) |
| `MAIL_PASSWORD` | Password or App Password for SMTP authentication. | (none) |
| `MAIL_DEFAULT_SENDER` | Default sender email address (ex. `noreply@example.com`). | `noreply@example.com` |
| **Advanced Configuration** | | |
| `TRANSCRIPTION_WORKERS` | Number of parallel workers for chunked transcription. | `4` |
| `WORKFLOW_RATE_LIMIT` | Rate limit for workflow API calls per user (ex. `10 per hour`). | `10 per hour` |
| `PHYSICAL_DELETION_DAYS` | Days after soft-deletion before a transcription is permanently removed. | `120` |

</details>

### Other Installation Options

<details>
<summary><strong>Click to see alternative installation methods (Docker Hub, Local Development)</strong></summary>

#### Option 2: Using a Pre-built Docker Hub Image

1.  **Create a `.env` file** on your host machine with all necessary variables. Ensure `MYSQL_HOST` points to your accessible MySQL server.
2.  **Pull the Docker Image:**
    ```bash
    docker pull yourusername/transcriber-platform:latest
    ```
3.  **Run the Docker Container:**
    ```bash
    docker run -d -p 5004:5004 \
      --env-file ./.env \
      --name transcriber-platform-app \
      yourusername/transcriber-platform:latest
    ```

#### Option 3: Local Development (Without Docker)

1.  **Clone the repository** and `cd` into it.
2.  **Create and activate a Python virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On macOS/Linux
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Set up MySQL:** Ensure you have a running MySQL server. Create a database and user.
5.  **Configure `.env`:** Create the file and add your `SECRET_KEY`, API keys and local MySQL connection details (`MYSQL_HOST=localhost`, etc.).
6.  **Initialize the Database:**
    ```bash
    export FLASK_APP=app
    flask init-db
    flask create-roles
    flask create-admin # If in multi-mode
    ```
7.  **Run the App:**
    ```bash
    flask run --host=0.0.0.0 --port=5004
    ```
</details>

## 💻 Usage Guide

1.  **Access the Application:** Open the application in your web browser.
2.  **Authentication (Multi-User Mode):**
    *   Register for an account or log in.
    *   Navigate to "Manage API Keys" to add your personal API keys for OpenAI, AssemblyAI, etc. This is required for most features.
3.  **Upload Audio:** Click the "File" button to select an audio file.
4.  **Configure Transcription:**
    *   Select your preferred API (Whisper, GPT-4o Transcribe, etc.).
    *   Choose the audio language or leave it on "Automatic Detection."
    *   (Optional) Provide a context prompt to improve accuracy.
5.  **Transcribe:** Click the "Transcribe" button.
6.  **Manage History:** Your completed transcriptions will appear in the history panel. From there you can:
    *   View, copy or download the text.
    *   Delete old transcriptions.
    *   Run an AI workflow (ex. summarize) on the text.

## 🛠️ For Developers

### Database Migrations

After changing a database model in `app/models/`, you must apply the changes.

**Do not use `flask init-db` after the initial setup.**

1.  **Connect to the running app container (if using Docker):**
    ```bash
    docker exec -it transcriber-platform bash
    ```
2.  **Run the migration command:**
    ```bash
    flask db-migrate
    ```
    For local development, run this command with your virtual environment activated.

### Translation Workflow

To add or update UI translations:

1.  **Extract strings** from the code to a template file:
    ```bash
    pybabel extract -F babel.cfg -k lazy_gettext -o messages.pot .
    ```
2.  **Update language files** with the new strings:
    ```bash
    pybabel update -i messages.pot -d app/translations
    ```
3.  **Edit the `.po` files** (ex. `app/translations/es/LC_MESSAGES/messages.po`) to add the new translations.
4.  **Compile the translations** into binary files the app can use:
    ```bash
    pybabel compile -d app/translations
    ```

## 🤔 Troubleshooting

-   **Port in use:** Change `APP_PORT` in `.env` and restart. If using Docker Compose, you can also change the host port in `docker-compose.yml` (ex. `"5005:5004"`).
-   **MySQL Connection Issues (Docker):** Ensure the `mysql` service is running (`docker-compose ps`). Check logs with `docker-compose logs mysql`. Verify `MYSQL_HOST` is set to `mysql` in your `.env` file.
-   **API Key Issues:** In `single` mode, double-check the global API keys in `.env`. In `multi` mode, ensure the logged-in user has added their keys correctly in the UI.
-   **Google Sign-In Errors:** Verify your `GOOGLE_CLIENT_ID` is correct and that your Google Cloud Project has the correct "Authorized JavaScript origins" (ex. `http://localhost:5004`) and "Redirect URIs".

## 📜 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.