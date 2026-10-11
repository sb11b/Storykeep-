# Storykeep Android (Talk session core)

Kotlin + Jetpack Compose app. Three screens only: Home, Conversation, Stories.

No Grok Voice / Speech-to-Speech APIs yet — the **Talk turn is real**: the mic clip goes to the backend STT endpoint and the real transcript replaces the local fake, and Junior's reply is spoken through the backend TTS endpoint. Type stays the text model with a local reply until slice 3 wires the chat endpoint. The session core already enforces the product lock: Talk dies on Type, End, leave, lock / background, and network loss. Saved stories persist on device (transcript text only).

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
- **Type**, or focusing / typing in the field, kills Talk. Mic and Listen stay off.
- **Lock / leave the app** or **lose network** kills Talk and keeps the transcript so you can still save it.
- **Save as story** appends the current transcript (text only) to Stories and keeps it after restart. **End** and **Back** return Home and clear the turn.
- **Stories:** pinned week’s question, Answer by talking / typing, cards, Record a story.

Keep is not a fourth screen; it returns to Home.

## Network layer (service-token auth)

The app talks to the Storykeep backend with Retrofit + OkHttp
(`com.storykeep.junior.network`). Every request carries a static bearer token
and a 401 becomes `UnauthorizedException` plus a flag on `AuthEvents` — no
silent retries. Talk / Conversation / Stories endpoints arrive in later slices.

The token is **never committed**. Put it in `android/local.properties`
(gitignored), which Gradle reads into `BuildConfig`:

```
STORYKEEP_SERVICE_TOKEN=<the Railway SERVICE_TOKEN>
# optional:
STORYKEEP_BASE_URL=https://storykeep-production.up.railway.app/api/v1/
```

Build with a missing token and the app still runs — it just 401s on every
authenticated call until the property is set.
