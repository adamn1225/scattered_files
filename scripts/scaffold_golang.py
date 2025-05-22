import os
import sys
import subprocess

project_name = sys.argv[1]
base_dir = os.path.expanduser("~")  # Change this as needed
project_path = os.path.join(base_dir, project_name)

os.makedirs(project_path, exist_ok=True)

# Create subdirectories
os.makedirs(os.path.join(project_path, "handlers"), exist_ok=True)
os.makedirs(os.path.join(project_path, "models"), exist_ok=True)
os.makedirs(os.path.join(project_path, "routes"), exist_ok=True)
os.makedirs(os.path.join(project_path, "migrations"), exist_ok=True)
os.makedirs(os.path.join(project_path, "utils"), exist_ok=True)
os.makedirs(os.path.join(project_path, "tests"), exist_ok=True)
os.makedirs(os.path.join(project_path, "middlewares"), exist_ok=True)
os.makedirs(os.path.join(project_path, "scripts"), exist_ok=True)
os.makedirs(os.path.join(project_path, "config"), exist_ok=True)

# Write main.go
main_go = f"""package main

import (
    "{project_name}/middlewares"
    "github.com/gin-gonic/gin"
    "github.com/joho/godotenv"
    "log"
    "os"
)

func main() {{
    err := godotenv.Load()
    if err != nil {{
        log.Fatal("Error loading .env file")
    }}
    r := gin.Default()
    r.Use(middlewares.CORSMiddleware())

    r.GET("/ping", func(c *gin.Context) {{
        c.JSON(200, gin.H{{"message": "pong"}})
    }})

    r.Run()
}}
"""

with open(os.path.join(project_path, "main.go"), "w") as f:
    f.write(main_go)

cors_middleware = """package middlewares

import (
    "github.com/gin-contrib/cors"
    "github.com/gin-gonic/gin"
    "time"
)

func CORSMiddleware() gin.HandlerFunc {
    config := cors.Config{
        AllowOrigins:     []string{"*"},
        AllowMethods:     []string{"GET", "POST", "PUT", "DELETE"},
        AllowHeaders:     []string{"Origin", "Content-Type", "Authorization"},
        AllowCredentials: true,
        MaxAge:           12 * time.Hour,
    }

    return cors.New(config)
}
"""

with open(os.path.join(project_path, "middlewares", "cors.go"), "w") as f:
    f.write(cors_middleware)

test_file = """package handlers

import (
    "net/http"
    "net/http/httptest"
    "testing"
    "github.com/gin-gonic/gin"
)

func TestPing(t *testing.T) {
    router := gin.Default()
    router.GET("/ping", func(c *gin.Context) {
        c.JSON(200, gin.H{"message": "pong"})
    })

    w := httptest.NewRecorder()
    req, _ := http.NewRequest("GET", "/ping", nil)
    router.ServeHTTP(w, req)

    if w.Code != 200 {
        t.Fatalf("Expected 200, got %d", w.Code)
    }
}
"""
with open(os.path.join(project_path, "handlers", "ping_test.go"), "w") as f:
    f.write(test_file)

compose = f"""version: '3.8'

services:
  backend:
    build: .
    container_name: {project_name}_backend
    ports:
      - "8080:8080"
    env_file:
      - .env
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
with open(os.path.join(project_path, "docker-compose.yml"), "w") as f:
    f.write(compose)

# Write Dockerfile
dockerfile = """\
FROM golang:1.21-alpine
WORKDIR /{project_name}
COPY . .
RUN go install github.com/joho/godotenv/cmd/godotenv@latest
RUN go mod init {project_name} && go mod tidy
RUN go build -o main .
CMD ["./main"]
"""

with open(os.path.join(project_path, "Dockerfile"), "w") as f:
    f.write(dockerfile)

with open(os.path.join(project_path, ".env"), "w") as f:
    f.write("""\
PORT=8080
DB_URL=postgres://user:pass@localhost:5432/dbname?sslmode=disable
API_KEY=changeme
""")

print("🔧 Initializing Git...")
subprocess.run(["git", "init"], cwd=project_path)
subprocess.run(["git", "add", "."], cwd=project_path)
subprocess.run(["git", "commit", "-m", "Initial scaffold"], cwd=project_path)

print(f"✅ Golang project '{project_name}' created in {project_path} with Dockerfile and starter folders.")

