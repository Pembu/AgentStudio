"""The stack catalog shown in the UI, plus detection of which toolchains are installed."""
import functools
import subprocess

# "tools" are the commands an agent needs to build and test that stack on this machine.
BACKENDS = [
    {"id": "python-fastapi", "language": "Python", "label": "FastAPI", "tools": ["python3"]},
    {"id": "python-django", "language": "Python", "label": "Django", "tools": ["python3"]},
    {"id": "python-flask", "language": "Python", "label": "Flask", "tools": ["python3"]},
    {"id": "java-spring", "language": "Java", "label": "Spring Boot", "tools": ["java", "mvn"]},
    {"id": "java-quarkus", "language": "Java", "label": "Quarkus", "tools": ["java", "mvn"]},
    {"id": "node-express", "language": "JavaScript (Node.js)", "label": "Express", "tools": ["node"]},
    {"id": "node-nestjs", "language": "TypeScript (Node.js)", "label": "NestJS", "tools": ["node"]},
    {"id": "go-gin", "language": "Go", "label": "Gin", "tools": ["go"]},
    {"id": "csharp-aspnet", "language": "C#", "label": "ASP.NET Core", "tools": ["dotnet"]},
    {"id": "rust-axum", "language": "Rust", "label": "Axum", "tools": ["cargo"]},
    {"id": "ruby-rails", "language": "Ruby", "label": "Rails", "tools": ["ruby"]},
    {"id": "php-laravel", "language": "PHP", "label": "Laravel", "tools": ["php", "composer"]},
]

FRONTENDS = [
    {"id": "react-vite", "language": "JavaScript", "label": "React (Vite)", "tools": ["node"]},
    {"id": "react-vite-ts", "language": "TypeScript", "label": "React + TypeScript (Vite)", "tools": ["node"]},
    {"id": "angular", "language": "TypeScript", "label": "Angular", "tools": ["node"]},
    {"id": "vue-vite", "language": "JavaScript", "label": "Vue (Vite)", "tools": ["node"]},
    {"id": "svelte-vite", "language": "JavaScript", "label": "Svelte (Vite)", "tools": ["node"]},
    {"id": "nextjs", "language": "TypeScript", "label": "Next.js", "tools": ["node"]},
    {"id": "vanilla", "language": "HTML/CSS/JS", "label": "Plain HTML + JS", "tools": []},
]

DATABASES = [
    {"id": "sqlite", "label": "SQLite (file, no server)"},
    {"id": "postgres", "label": "PostgreSQL"},
    {"id": "mysql", "label": "MySQL"},
    {"id": "mongodb", "label": "MongoDB"},
    {"id": "memory", "label": "In-memory (no persistence)"},
]

MODELS = [
    {"id": "", "label": "Claude Code default"},
    {"id": "opus", "label": "Opus (most capable)"},
    {"id": "sonnet", "label": "Sonnet (balanced)"},
    {"id": "haiku", "label": "Haiku (fastest, cheapest)"},
]

# "custom" lets the user type any stack; "none" skips that layer entirely.
SPECIAL = {"custom", "none"}

# The command that proves a tool really works. On macOS /usr/bin/java exists even
# without a JDK, so finding it on PATH is not enough; we run it.
_VERSION_CMD = {
    "python3": ["python3", "--version"],
    "java": ["java", "-version"],
    "mvn": ["mvn", "-v"],
    "node": ["node", "--version"],
    "go": ["go", "version"],
    "dotnet": ["dotnet", "--version"],
    "cargo": ["cargo", "--version"],
    "ruby": ["ruby", "--version"],
    "php": ["php", "--version"],
    "composer": ["composer", "--version"],
}


@functools.cache
def toolchains() -> dict[str, bool]:
    """Which build tools work on this machine. Cached: checked once per server start."""
    found = {}
    for tool, cmd in _VERSION_CMD.items():
        try:
            found[tool] = subprocess.run(cmd, capture_output=True, timeout=10).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            found[tool] = False
    return found


def find(options: list[dict], option_id: str) -> dict | None:
    return next((o for o in options if o["id"] == option_id), None)


def catalog() -> dict:
    return {
        "backends": BACKENDS,
        "frontends": FRONTENDS,
        "databases": DATABASES,
        "models": MODELS,
        "toolchains": toolchains(),
    }
