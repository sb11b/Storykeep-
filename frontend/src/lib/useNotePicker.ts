"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

export interface NoteChoice {
  id: string;
  title: string;
}

export function useNotePicker(onSelect: (noteId: string, noteTitle: string) => void) {
  const [notePickerOpen, setNotePickerOpen] = useState(false);
  const [noteQuery, setNoteQuery] = useState("");
  const [noteChoices, setNoteChoices] = useState<NoteChoice[]>([]);
  const [loadingNotes, setLoadingNotes] = useState(false);

  useEffect(() => {
    if (!notePickerOpen) return;
    let cancelled = false;
    setLoadingNotes(true);
    void api
      .noteTitles(noteQuery, 20)
      .then((payload) => {
        if (!cancelled) setNoteChoices(payload.items || []);
      })
      .catch(() => {
        if (!cancelled) setNoteChoices([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingNotes(false);
      });
    return () => {
      cancelled = true;
    };
  }, [notePickerOpen, noteQuery]);

  const openPicker = useCallback(() => {
    setNotePickerOpen(true);
  }, []);

  const closePicker = useCallback(() => {
    setNotePickerOpen(false);
    setNoteQuery("");
  }, []);

  const selectNote = useCallback(
    (noteId: string, noteTitle: string) => {
      onSelect(noteId, noteTitle);
      setNotePickerOpen(false);
      setNoteQuery("");
    },
    [onSelect],
  );

  return {
    notePickerOpen,
    noteQuery,
    noteChoices,
    loadingNotes,
    openPicker,
    closePicker,
    selectNote,
    setNoteQuery,
  };
}
