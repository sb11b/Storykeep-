export function usePaneVoice({
  ttsEnabled,
  locked,
  panelOpen,
  busy,
  inFlightRef,
  onStopArticleListen,
  onActivateListen,
  paneMessages,
  defaultTtsVoiceId,
  ttsVoices,
  bodyElementsRef,
  messagesRef,
}: UsePaneVoiceOptions): UsePaneVoiceResult {
  // -- TTS state --
  const [voiceId, setVoiceId] = useState(() => readStoredTtsVoice(defaultTtsVoiceId));
  const [playbackSpeed, setPlaybackSpeed] = useState(() => readStoredTtsSpeed());
  const [listenTarget, setListenTarget] = useState<ListenTarget | null>(null);
  const [activeWord, setActiveWord] = useState<number | null>(null);
  const [autoReadReplies, setAutoReadReplies] = useState(() => readStoredTtsAutoRead());

  // -- STT/STS state --
  const [sttPhase, setSttPhase] = useState<"idle" | "listening" | "transcribing">("idle");
  const [micMode, setMicMode] = useState<"stt" | "sts" | null>(null);
  const [sttEmptyHint, setSttEmptyHint] = useState(false);
  const sttEmptyHintTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [stsModeOn, setStsModeOn] = useState(false);

  // -- refs --
  const ttsPausedRef = useRef(false);
  const userStoppedTtsRef = useRef(false);
  const clickedWordRef = useRef<{ messageId: string; index: number } | null>(null);
  const listenTargetRef = useRef<ListenTarget | null>(null);
  const pendingListenRef = useRef(false);
  const pendingFromHereRef = useRef<number | null>(null);
  const pendingAutoListenRef = useRef<{ id: string; markdown: string } | null>(null);
  const requestAutoListenRef = useRef<(messageId: string, markdown: string) => void>(() => {});
  const listenPhaseRef = useRef<"idle" | "loading" | "playing" | "paused">("idle");
  const stsModeOnRef = useRef(false);
  const stsRearmRef = useRef<(() => void) | null>(null);

  // keep refs in sync
  listenTargetRef.current = listenTarget;

  // -- voice init --
  useEffect(() => {
    let cancelled = false;
    api
      .getPreferences()
      .then((prefs) => {
        if (cancelled) return;
        const saved = typeof prefs.tts_voice_id === "string" ? prefs.tts_voice_id : null;
        const local = readStoredTtsVoice(defaultTtsVoiceId);
        const next = resolveTtsVoiceId(ttsVoices, defaultTtsVoiceId, saved || local);
        setVoiceId(next);
        writeStoredTtsVoice(next);
      })
      .catch(() => {
        if (cancelled) return;
        const next = resolveTtsVoiceId(
          ttsVoices,
          defaultTtsVoiceId,
          readStoredTtsVoice(defaultTtsVoiceId),
        );
        setVoiceId(next);
      });
    return () => {
      cancelled = true;
    };
  }, [defaultTtsVoiceId, ttsVoices]);

  // -- resolve listen script --
  const resolveListenScript = useCallback(() => {
    const target = listenTargetRef.current;
    if (!target) return "";
    if (target.script) return target.script;
    const resolved = readReplyText({
      trigger: target.trigger,
      body: bodyElementsRef.current.get(target.id) ?? null,
      markdown: messagesRef.current.find((item) => item.id === target.id)?.content ?? null,
    });
    logReplyText("resolve", resolved);
    return resolved.text;
  }, [bodyElementsRef, messagesRef]);

  // -- listen hook --
  const maybeRearmStsRef = useRef<() => void>(() => {});

  const listen = useGrokMessageListen({
    messageId: listenTarget?.id ?? "",
    resolveScript: resolveListenScript,
    voiceId,
    disabled: !listenTarget || !ttsEnabled || locked,
    onCue: setActiveWord,
    onPlayingChange: (active) => {
      if (active) {
        onStopArticleListen?.();
        onActivateListen(() => listen.stop());
      } else {
        onActivateListen(null);
        setActiveWord(null);
        if (!ttsPausedRef.current) maybeRearmStsRef.current();
      }
    },
  });

  const listenApiRef = useRef(listen);
  listenApiRef.current = listen;
  listenPhaseRef.current = listen.phase;

  // -- rearm STS --
  const maybeRearmSts = useCallback(() => {
    if (!stsModeOnRef.current) return;
    if (ttsPausedRef.current) return;
    if (sttPhase !== "idle") return;
    if (busy || inFlightRef.current) return;
    const lp = listenPhaseRef.current;
    if (lp === "loading" || lp === "playing" || lp === "paused") return;
    console.log("junior-sts", { action: "rearm-request" });
    stsRearmRef.current?.();
  }, [busy, inFlightRef, sttPhase]);

  maybeRearmStsRef.current = maybeRearmSts;

  // -- effects --
  useEffect(() => {
    if (pendingListenRef.current && listenTarget) {
      pendingListenRef.current = false;
      const fromHere = pendingFromHereRef.current;
      pendingFromHereRef.current = null;
      if (fromHere != null) void listenApiRef.current.listenFromWord(fromHere);
      else listenApiRef.current.listen();
    }
  }, [listenTarget]);

  useEffect(() => {
    if (!panelOpen) listenApiRef.current.stop();
  }, [panelOpen]);

  // -- TTS handlers --
  function handleVoiceChange(next: string) {
    if (listen.isActive) {
      listenApiRef.current.stop();
    }
    setVoiceId(next);
    writeStoredTtsVoice(next);
    void api.updatePreferences({ tts_voice_id: next }).catch(() => {});
  }

  function handleSpeedChange(next: number) {
    setPlaybackSpeed(next);
    writeStoredTtsSpeed(next);
    listen.changeSpeed(next);
  }

  function listenLatestReply() {
    if (listenTarget) {
      requestListen(listenTarget.id, listenTarget.trigger);
      return;
    }
    const latest = [...paneMessages]
      .reverse()
      .find((item) => item.role === "assistant" && item.content);
    if (!latest) {
      toast.error("Send a message first — there is no reply to read yet.");
      return;
    }
    requestListen(latest.id, null);
  }

  function requestListen(messageId: string, trigger: HTMLElement | null) {
    if (listen.isActive && listenTarget?.id !== messageId) {
      listen.stop();
    }
    if (listen.isActive && listenTarget?.id === messageId) {
      if (listen.phase === "playing") {
        userStoppedTtsRef.current = true;
        ttsPausedRef.current = true;
        listen.pause();
      } else {
        userStoppedTtsRef.current = false;
        ttsPausedRef.current = false;
        listen.listen();
      }
      return;
    }
    const resolved = readReplyText({
      trigger,
      body: bodyElementsRef.current.get(messageId) ?? null,
      markdown: paneMessages.find((item) => item.id === messageId)?.content ?? null,
    });
    logReplyText("click", resolved);
    if (!resolved.chars) {
      toast.error("That reply is still empty — nothing to read yet.");
      return;
    }
    userStoppedTtsRef.current = false;
    pendingListenRef.current = true;
    setListenTarget({ id: messageId, trigger, script: resolved.text });
  }

  function requestAutoListen(messageId: string, markdown: string) {
    if (!ttsEnabled || locked || !panelOpen) return;
    if (!autoReadReplies) {
      if (listen.isActive) {
        listen.stop();
      }
      return;
    }
    if (userStoppedTtsRef.current) return;
    if (sttPhase !== "idle") {
      pendingAutoListenRef.current = { id: messageId, markdown };
      return;
    }
    pendingAutoListenRef.current = null;
    const resolved = readReplyText({
      trigger: null,
      body: bodyElementsRef.current.get(messageId) ?? null,
      markdown,
    });
    logReplyText("auto", resolved);
    if (!resolved.chars) return;
    if (listen.isActive && listenTarget?.id !== messageId) {
      listen.stop();
    }
    pendingListenRef.current = true;
    setListenTarget({ id: messageId, trigger: null, script: resolved.text });
  }

  requestAutoListenRef.current = requestAutoListen;

  function handleListenPause() {
    userStoppedTtsRef.current = true;
    ttsPausedRef.current = true;
    listen.pause();
  }

  function handleListenStop() {
    userStoppedTtsRef.current = true;
    ttsPausedRef.current = false;
    listen.stop();
    maybeRearmSts();
  }

  function readableAssistant(messageId?: string | null) {
    if (messageId) {
      const match = paneMessages.find(
        (item) => item.id === messageId && item.role === "assistant" && item.content,
      );
      if (match) return match;
    }
    if (listenTarget) {
      const match = paneMessages.find(
        (item) => item.id === listenTarget.id && item.role === "assistant" && item.content,
      );
      if (match) return match;
    }
    return [...paneMessages].reverse().find((item) => item.role === "assistant" && item.content) ?? null;
  }

  function listenFromHere() {
    const target = readableAssistant(clickedWordRef.current?.messageId);
    if (!target) {
      toast.error("Send a message first — there is no reply to read yet.");
      return;
    }
    const body = bodyElementsRef.current.get(target.id) ?? null;
    const word = wordIndexFromSelection(body) ??
      (clickedWordRef.current?.messageId === target.id ? clickedWordRef.current.index : null);
    if (word == null || word < 0) {
      toast.error("Click or highlight a word in the reply first.");
      return;
    }
    const resolved = readReplyText({
      trigger: listenTarget?.id === target.id ? listenTarget.trigger : null,
      body,
      markdown: target.content,
    });
    logReplyText("from-here", resolved);
    if (!resolved.chars) {
      toast.error("That reply is still empty — nothing to read yet.");
      return;
    }
    if (listenTarget?.id === target.id && listen.isActive) {
      userStoppedTtsRef.current = false;
      void listen.listenFromWord(word);
      return;
    }
    userStoppedTtsRef.current = false;
    pendingFromHereRef.current = word;
    pendingListenRef.current = true;
    setListenTarget({ id: target.id, trigger: null, script: resolved.text });
  }

  // -- STT/STS handlers --
  const clearSttEmptyHint = useCallback(() => {
    if (sttEmptyHintTimerRef.current != null) {
      clearTimeout(sttEmptyHintTimerRef.current);
      sttEmptyHintTimerRef.current = null;
    }
    setSttEmptyHint(false);
  }, []);

  const showSttEmptyHint = useCallback(() => {
    if (sttEmptyHintTimerRef.current != null) clearTimeout(sttEmptyHintTimerRef.current);
    setSttEmptyHint(true);
    sttEmptyHintTimerRef.current = setTimeout(() => {
      sttEmptyHintTimerRef.current = null;
      setSttEmptyHint(false);
    }, 5000);
  }, []);

  const handleMicPhaseChange = useCallback(
    (phase: "idle" | "listening" | "transcribing", mode: "stt" | "sts" | null) => {
      if (phase === "listening") clearSttEmptyHint();
      setSttPhase(phase);
      setMicMode(mode);
      if (phase === "idle") {
        const pending = pendingAutoListenRef.current;
        if (pending) {
          pendingAutoListenRef.current = null;
          requestAutoListenRef.current(pending.id, pending.markdown);
        }
      }
    },
    [clearSttEmptyHint],
  );

  const handleStsModeChange = useCallback((active: boolean) => {
    stsModeOnRef.current = active;
    setStsModeOn(active);
  }, []);

  return {
    voiceId,
    playbackSpeed,
    listenTarget,
    activeWord,
    autoReadReplies,
    setAutoReadReplies,
    setActiveWord,
    clickedWordRef,
    listen,
    listenApiRef,
    listenPhaseRef,
    requestAutoListenRef,
    ttsPausedRef,
    userStoppedTtsRef,
    handleVoiceChange,
    handleSpeedChange,
    listenLatestReply,
    requestListen,
    requestAutoListen,
    handleListenPause,
    handleListenStop,
    listenFromHere,
    readableAssistant,
    sttPhase,
    micMode,
    sttEmptyHint,
    stsModeOn,
    handleMicPhaseChange,
    handleStsModeChange,
    clearSttEmptyHint,
    showSttEmptyHint,
  };
}
