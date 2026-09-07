# Start here (Windows)

Three different places got mixed together. Use them in this order. Do not jump to Railway until step 4 works in a browser.

| Place | What it is | Use it for |
| --- | --- | --- |
| [Origin / Storykeep](https://cursor.com/codebase/steve-bitsko/Storykeep) | The real repo with the code | Opening or cloning the project |
| GitHub `sb11b/Storykeep-` | Empty (no code) | Ignore until local works |
| Railway | Hosting | Last step, after you can log in locally |

Login once the app is up:

- email: `steve@storykeep.local`
- password: `commonplace`

---

## 1. Get the code onto this PC

**Easiest:** open [cursor.com/codebase/steve-bitsko/Storykeep](https://cursor.com/codebase/steve-bitsko/Storykeep) and use **Open in Cursor**.

**If that is missing**, clone from **WSL** (Ubuntu). Origin CLI does not work in PowerShell.

In PowerShell (once, if you do not have Ubuntu yet):

```powershell
wsl --install
```

Restart Windows, then open **Ubuntu** and run:

```bash
# If `origin` is not found after install:
# echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc

curl -fsSL https://downloads.cursor.com/origin/install.sh | sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

origin auth login
origin repo clone steve-bitsko/Storykeep
cd Storykeep
```

Docs: https://cursor.com/docs/origin/cli

---

## 2. Install Docker Desktop

Download [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/). Install it, start it, and wait until it says it is running.

In Docker Desktop → Settings → Resources → WSL integration, enable your Ubuntu distro.

---

## 3. Start Storykeep

In the same Ubuntu terminal, from the `Storykeep` folder:

```bash
docker compose up --build
```

The first build takes several minutes. Leave the terminal open.

---

## 4. Open the library

In your Windows browser: [http://127.0.0.1:8080](http://127.0.0.1:8080)

Sign in with `steve@storykeep.local` / `commonplace`. Feeds keep importing for a minute after first boot.

If the page never loads, Docker Desktop is not running, or port 8080 is already in use. In Ubuntu:

```bash
docker compose logs --tail 80
```

---

## 5. Railway (only after step 4 works)

Railway deploys from **GitHub**, not Origin. Your GitHub repo is still empty, so Railway has nothing to build.

From WSL, inside `Storykeep`:

```bash
git remote add github https://github.com/sb11b/Storykeep-.git
git push -u github main
```

Sign in to GitHub in the browser if it asks.

Then on [railway.app](https://railway.app):

1. New project → Deploy from GitHub → `sb11b/Storykeep-`
2. New → Database → PostgreSQL
3. On the web service, add `DATABASE_URL=${{Postgres.DATABASE_URL}}`
4. Settings → Networking → Generate domain
5. Open that URL and use the same demo login

---

## If a command fails

Copy the **full terminal output** of the command that failed (Origin install, `origin auth login`, `docker compose`, or Railway). That one log is enough to pick the next fix.
