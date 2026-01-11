# Deployment Guide

This guide describes how to run the **Multi-Agent Orchestrator Backend** using Docker Compose, both for local development and production server deployment.

## Prerequisites
- **Docker** and **Docker Compose** installed.
- **Git** installed.
- Valid `.env` file in the root directory (ensure `OPENAI_API_KEY` is set).

---

## 1. Local Development
Use `docker-compose.local.yml` to run the system on your local machine.

### Steps
1. **Configure Environment**:
   Ensure your `.env` file is set up.
   ```bash
   cp .env.example .env
   # Edit .env and set OPENAI_API_KEY
   ```

2. **Build and Run**:
   ```bash
   docker compose -f docker-compose.local.yml up --build -d
   ```

3. **Verify**:
   - The API will be available at `http://localhost:8000`.
   - Docs: `http://localhost:8000/docs`

4. **Logs**:
   ```bash
   docker compose -f docker-compose.local.yml logs -f backend
   ```

5. **Stop**:
   ```bash
   docker compose -f docker-compose.local.yml down
   ```

---

## 2. Server Deployment (Production)
Use `docker-compose.yml` for deploying to a VPS/Server. This configuration is designed to work behind a reverse proxy (like Nginx Proxy Manager).

### Network Configuration
The `docker-compose.yml` uses an external network named `npm_default` to communicate with the reverse proxy.

**Before running, ensure the network exists:**
```bash
docker network create npm_default || true
```

### Steps
1. **Clone & Setup**:
   ```bash
   git clone <repo-url>
   cd self-spawn-agents
   cp .env.example .env
   # Edit .env with production keys
   ```

2. **Build and Run**:
   ```bash
   docker compose -f docker-compose.yml up --build -d
   ```

3. **Reverse Proxy Setup (NPM)**:
   - Point your reverse proxy (e.g., Nginx Proxy Manager) to the container `selfspawnagents_backend` on port `8000`.
   - Ensure the proxy is also on the `npm_default` network.

4. **Verify**:
   - Access via your configured domain (e.g., `https://api.yourdomain.com/docs`).

5. **Logs**:
   ```bash
   docker compose -f docker-compose.yml logs -f backend
   ```

### Troubleshooting
- **Network Errors**: If the container fails to start due to network issues, verify `npm_default` exists (`docker network ls`).
- **Permissions**: Ensure the user running docker has permissions to access the directory.
