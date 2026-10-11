/**
 * Static offline fallback page. Precached by the service worker (public/sw.js)
 * and served for navigations when the network is down and no cached shell
 * exists for the requested route.
 */
export default function OfflinePage() {
  return (
    <main className="min-h-screen flex items-center justify-center px-6 bg-background text-foreground">
      <div className="max-w-md text-center">
        <h1 className="font-[family-name:var(--font-serif)] text-3xl">You&rsquo;re offline</h1>
        <p className="text-sm text-muted-foreground mt-3">
          StoryKeep needs a connection the first time it loads a page. Once a
          page is cached, reopen it from the installed app — it will keep
          working offline.
        </p>
        <a
          href="/"
          className="inline-block mt-5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
        >
          Back to the library
        </a>
      </div>
    </main>
  );
}
