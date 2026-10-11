# Storykeep Android (Talk session core)

Kotlin + Jetpack Compose app. Three screens only: Home, Conversation, Stories.

No Grok Voice / Speech-to-Speech APIs yet — the **Talk turn is real**: the mic clip goes to the backend STT endpoint and the real transcript replaces the local fake, and Junior's reply is spoken through the backend TTS endpoint. The **Conversation venue is real too (slice 3)**: opening it loads the first Junior project, its first thread, and the real message history from the shared-memory API (`/api/v1/junior/projects`, `/junior/projects/{slug}/threads`, `/junior/projects/{slug}/threads/{id}/messages`), and a typed send posts to `POST /junior/projects/{slug}/threads/{id}/messages` — the stored user + Junior messages replace the placeholder transcript. The **Stories venue is real (slice 4)**: the Stories screen lists the owner's real saved stories from the shared-memory documents API (`GET /junior/documents`), and **Save as story** posts the transcript to `POST /junior/documents` (create-or-update, upsert by slug) — the backend is the source of truth; the old on-device story store is gone. Loading shows a spinner; Offline shows a retry; Unauthorized flags the service token; Http shows the status; Malformed shows unreadable. The session core still enforces the product lock: Talk dies on Type, End, leave, lock / background, and network loss.

This folder is a separate Gradle project. It is not part of the Railway web image (`Dockerfile` / `railway.toml` still build backend + Next.js only).

## Open and run in Android Studio

1. Install [Android Studio](https://developer.android.com/studio) (Ladybug / 2024.2 or newer is fine).
2. **File → Open** and choose the `android` directory in this repo (not the repo root).
3. Let Gradle sync. If asked, use the embedded JDK 17+ and install SDK 35.
4. Plug in a phone (USB debugging) or start an emulator with **API 26 or higher**.
5. Select the `app` run configuration and press **Run**.

Command line, after the Android SDK is installed and `ANDROID_HOME` is set:

```bash
cd android
./gradlew :app:installDebug
```

On Windows: `gradlew.bat :app:installDebug`.

## What you can walk

- **Home:** mark, “Junior is here”, presence orb, Talk / Type, last-spoke placeholder, bottom nav Talk / Stories / Keep.
- **Talk** opens Conversation. Grant the mic permission when asked. Tap the amber control: Idle → Listening records, tap again sends the clip to STT and Junior's reply plays through TTS.
- The conversation itself is real (slice 3): the first project, its threads, and the thread's message history load from the shared-memory API. Pick a thread from the row under the header. A spinner shows while loading; an offline load offers a retry; a 401 flags the service token; any other status shows the code.
- **Type**, or focusing / typing in the field, kills Talk. Sending a typed message posts to the backend thread — the stored user + Junior messages replace the placeholder reply, and a failed post stays on the device with the reason shown.
- **Lock / leave the app** or **lose network** kills Talk and keeps the transcript so you can still save it.
- **Save as story** posts the current transcript (text only) to the backend documents API — the Stories list shows real saved stories from that API. **End** and **Back** return Home and clear the turn.
- **Stories:** pinned week’s question, Answer by talking / typing, real story cards from `GET /junior/documents`, Record a story. A spinner shows while loading; an offline load offers a retry; a 401 flags the service token; any other status shows the code.

Keep is not a fourth screen; it returns to Home.

## Network layer (service-token auth)

The app talks to the Storykeep backend with Retrofit + OkHttp
(`com.storykeep.junior.network`). Every request carries a static bearer token
and a 401 becomes `UnauthorizedException` plus a flag on `AuthEvents` — no
silent retries. Talk (STT/TTS), the Conversation surface
(`junior/projects`, project threads, thread messages, message posts), and the
Stories surface (`junior/documents`: list, get by slug, create-or-update)
are all wired.

The token is **never committed**. Put it in `android/local.properties`
(gitignored), which Gradle reads into `BuildConfig`:

```
STORYKEEP_SERVICE_TOKEN=<the Railway SERVICE_TOKEN>
# optional:
STORYKEEP_BASE_URL=https://storykeep-production.up.railway.app/api/v1/
```

Build with a missing token and the app still runs — it just 401s on every
authenticated call until the property is set.

## Release build and signing

The release variant is shrunk with R8 (`isMinifyEnabled` +
`isShrinkResources`; keep rules live in `app/proguard-rules.pro`) and signed
from `android/keystore.properties` — a **gitignored** file, never committed:

```properties
storeFile=storykeep-release.jks
storePassword=<store password>
keyAlias=<key alias>
keyPassword=<key password>
```

`storeFile` is a path relative to the `android/` directory (e.g.
`storykeep-release.jks` sitting next to `keystore.properties`).

Generate your keystore **once, locally** (and back it up — losing it means you
can never update the published app under the same signing identity):

```bash
keytool -genkeypair -v -keystore storykeep-release.jks \
  -alias storykeep -keyalg RSA -keysize 4096 -validity 10000
```

Then create `android/keystore.properties` with the four keys above (same
passwords you just chose). **Never commit the `.jks` file or
`keystore.properties`** — both are gitignored (`android/.gitignore`).

Without `keystore.properties` the release build still succeeds — it just
produces an **unsigned** APK (`app/build/outputs/apk/release/`), so a fresh
clone can always run `./gradlew :app:assembleRelease`. Build a publishable,
signed APK with:

```bash
cd android
./gradlew :app:assembleRelease
```

Current version: `versionCode 2`, `versionName 0.1.0` — all three venues
(Talk, Conversation, Stories) are real, so the old `-shell` suffix is gone.
