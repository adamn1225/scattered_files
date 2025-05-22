import os
import sys
import subprocess
from pathlib import Path

project_name = sys.argv[1]
home = str(Path.home())
backend_path = os.path.join(home, f"{project_name}_backend")
frontend_path = os.path.join(home, f"{project_name}_frontend")

print(f"🔧 Creating fullstack project: {project_name}")
print(f"📁 Backend: {backend_path}")
print(f"📁 Frontend: {frontend_path}")

# Step 1: Scaffold backend
print("⚙️ Scaffolding Golang backend...")
subprocess.run(["python", "scripts/scaffold_golang.py", f"{project_name}_backend"])

# Step 2: Scaffold frontend
print("⚙️ Scaffolding Next.js frontend...")
subprocess.run(["python", "scripts/scaffold_nextjs.py", f"{project_name}_frontend"])

# Step 3: Create shared docker-compose.yml in ~/myproject/
project_root = os.path.join(home, project_name)
os.makedirs(project_root, exist_ok=True)

compose = f"""version: '3.8'

services:
  backend:
    build: ../{project_name}_backend
    container_name: {project_name}_backend
    ports:
      - "8080:8080"
    env_file:
      - ../{project_name}_backend/.env
    depends_on:
      - db

  frontend:
    image: node:18
    container_name: {project_name}_frontend
    working_dir: /app
    volumes:
      - ../{project_name}_frontend:/app
    ports:
      - "3000:3000"
    command: sh -c "npm install && npm run dev"

  db:
    image: postgres:15
    container_name: {project_name}_db
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: dbname
    ports:
      - "5432:5432"
"""

with open(os.path.join(project_root, "docker-compose.yml"), "w") as f:
    f.write(compose)

# Step 4: Optional .env link between frontend/backend
frontend_env_path = os.path.join(frontend_path, ".env.local")
with open(frontend_env_path, "w") as f:
    f.write(f"""\
NEXT_PUBLIC_API_BASE_URL=http://localhost:8080
""")

print(f"✅ Fullstack project '{project_name}' created.")
print(f"📦 Backend in: {backend_path}")
print(f"🎨 Frontend in: {frontend_path}")
print(f"🐳 Docker Compose in: {project_root}/docker-compose.yml")
