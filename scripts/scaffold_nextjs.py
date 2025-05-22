import os
import sys
import subprocess

project_name = sys.argv[1]
base_dir = os.path.expanduser("~") 
project_path = os.path.join(base_dir, project_name)

# Create the home directory if for some reason it doesn't exist
os.makedirs(base_dir, exist_ok=True)

# Step 1: Run Next.js scaffolding
subprocess.run([
    "npx", "create-next-app@latest", project_path,
    "--typescript", "--eslint", "--tailwind", "--src-dir", "--app",
    "--import-alias", "@/*"
])

print("📦 Installing common frontend packages...")
subprocess.run(["npm", "install", "clsx", "axios", "react-hook-form"])



# Step 2: Tailwind tweaks
tailwind_config_path = os.path.join(project_path, "tailwind.config.ts")
globals_css_path = os.path.join(project_path, "src", "app", "globals.css")

if os.path.exists(tailwind_config_path):
    with open(tailwind_config_path, "r+") as f:
        contents = f.read()
        if "'./src/**/*.{js,ts,jsx,tsx}'" not in contents:
            contents = contents.replace("content: [", "content: ['./src/**/*.{js,ts,jsx,tsx}', ")
            f.seek(0)
            f.write(contents)
            f.truncate()

if os.path.exists(globals_css_path):
    with open(globals_css_path, "a") as f:
        f.write("""

body {
  @apply bg-gray-100 text-gray-900;
}
""")

print(f"✅ Next.js + Tailwind project '{project_name}' created in {project_path}")
