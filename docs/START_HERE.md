# Start here (Windows, no Ubuntu)

You do not need Ubuntu, WSL, or Docker. Origin CLI is Linux/macOS/WSL only, so skip it.

Railway reads **GitHub**, not Origin. The GitHub repo `sb11b/Storykeep-` is empty until you push. The code already lives here:

https://cursor.com/codebase/steve-bitsko/Storykeep

Login after it is online with your own StoryKeep account (production: `angry.tune8751@fastmail.com`). The public demo login is closed.

---

## 1. Open the project in Cursor (Windows)

1. In the browser, open [cursor.com/codebase/steve-bitsko/Storykeep](https://cursor.com/codebase/steve-bitsko/Storykeep).
2. Click **Open in Cursor** (or Clone / Open).
3. When Cursor asks, pick a folder on this PC (for example `D:\Storykeep`).

You should see `README.md`, `backend\`, `frontend\`, and `Dockerfile` in the sidebar.

If Cursor will not open the Origin repo, install [Git for Windows](https://git-scm.com/download/win), then in Cursor’s terminal (PowerShell):

```powershell
git clone https://origin.cursor.com/steve-bitsko/Storykeep.git D:\Storykeep
```

Sign in if the browser pops up. Then **File → Open Folder → D:\Storykeep**.

---

## 2. Put the code on GitHub

In Cursor, open the terminal (PowerShell) in the Storykeep folder:

```powershell
git remote add github https://github.com/sb11b/Storykeep-.git
git push -u github main
```

If `remote github already exists`, skip the first line and only run `git push -u github main`.

GitHub will ask you to sign in in the browser. After the push, [github.com/sb11b/Storykeep-](https://github.com/sb11b/Storykeep-) should show the Storykeep files, not an empty repo.

---

## 3. Deploy on Railway

1. Open [railway.app](https://railway.app) and sign in (GitHub login is fine).
2. **New project → Deploy from GitHub repo → `sb11b/Storykeep-`**.
3. **New → Database → PostgreSQL**.
4. Click the **web/app service** (not Postgres) → **Variables** → add:

```
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

The Postgres plugin name might be `Postgres` or `PostgreSQL`. Railway’s variable picker can fill this in.

5. That same service → **Settings → Networking → Generate domain**.
6. Wait until the deploy is **Success**. Open the `*.up.railway.app` URL.
7. Sign in with your own account. The public demo login is closed.

The first deploy builds the Docker image and can take several minutes. Feeds keep importing for a minute after the site comes up.

---

## If something fails

| What you see | What to do |
| --- | --- |
| Cursor cannot open the Origin repo | Use the `git clone` line in step 1, or tell me the exact error text |
| `git push` asks for a password and fails | Use **Sign in with browser** / GitHub, not your GitHub account password |
| GitHub is still empty | You are not in the Storykeep folder, or push never finished |
| Railway build fails | Open the failed deploy log and send the last 40 lines |
| Railway site loads but login fails | Confirm `DATABASE_URL` is on the **app** service, not only on Postgres |

Do not install Ubuntu for this path.

---

## Overlay pack (the only thing that goes back to Obsidian)

StoryKeep never overwrites `Steve's Surface Vault\**`. Import is one-way. What you add in StoryKeep comes back as a zip you unzip at the **vault root**.

1. In StoryKeep, open an imported note. Highlight a passage (optional comment), save an **addition**, or **Save correction**.
2. Click **Download Obsidian pack** in the reader or on the Backup page.
3. On Windows, unzip `storykeep-obsidian-pack.zip` into the same folder that contains `Steve's Surface Vault` so you get:

```
Steve's Surface Vault\
  StoryKeep\
    Highlights\
    Additions\
    Corrections\
    Index.md
```

4. `Index.md` lists overlay files and article ids. It does not list original vault notes as modified.
5. Merge **Corrections** by hand if you want those edits in the source note. Do not replace the original file with a StoryKeep export of the article body.

To add a **new** complete note or paper, use Collect → Vault, type the title, subjects, and markdown, then **Save complete note**. That file only appears in `StoryKeep\Additions`. It never overwrites an original vault path.

To add a **PDF, Word, PowerPoint, or other document**, use Collect → File. StoryKeep extracts the text into the archive. It does not overwrite Steve's Surface Vault.

The orange Grok bubble (bottom-right, draggable) asks about the open article. **Add to notes** creates or updates a StoryKeep addition (`StoryKeep/Additions`), never a vault overwrite. Chat and dictation use `XAI_API_KEY` on Railway only.

uCertify is not integrated. There is no login, scrape, or stored password. If you already have a page open, use **Save URL**.

