"use client";

import { toast } from "sonner";
import { api } from "@/lib/api";

type PendingChip = { id: string };

type AttachPane = {
  pendingAttachments?: PendingChip[] | null;
};

type UseFileAttachOptions = {
  pane: AttachPane;
  onUpdate: (updater: (current: AttachPane) => any) => void;
  locked: boolean;
  enabled: boolean;
  setUploadingFiles: (uploading: boolean) => void;
  snapshotFiles: (list: FileList | File[]) => File[];
  LARRY_ATTACH_MAX_FILES: number;
  rejectLarryFile: (file: File) => string | null;
  uploadLarryAttachment: (file: File) => Promise<PendingChip>;
  toastActionError: (error: unknown, action: string, fallback: string) => void;
};

export function useFileAttach({
  pane,
  onUpdate,
  locked,
  enabled,
  setUploadingFiles,
  snapshotFiles,
  LARRY_ATTACH_MAX_FILES,
  rejectLarryFile,
  uploadLarryAttachment,
  toastActionError,
}: UseFileAttachOptions) {
  async function attachFiles(fileList: FileList | File[]) {
    const incoming = snapshotFiles(fileList);
    if (!incoming.length) return;
    if (locked || !enabled) {
      toast.error("Chat is not available for attachments right now.");
      return;
    }
    const already = pane.pendingAttachments ?? [];
    const room = LARRY_ATTACH_MAX_FILES - already.length;
    if (room <= 0) {
      toast.error(`Attach up to ${LARRY_ATTACH_MAX_FILES} files.`);
      return;
    }
    const chosen = incoming.slice(0, room);
    if (incoming.length > room) {
      toast.error(`Attach up to ${LARRY_ATTACH_MAX_FILES} files.`);
    }
    setUploadingFiles(true);
    try {
      for (const file of chosen) {
        const reason = rejectLarryFile(file);
        if (reason) {
          toast.error(reason);
          continue;
        }
        const uploaded = await uploadLarryAttachment(file);
        if (!uploaded.id) {
          toast.error("No attach without a media id.");
          continue;
        }
        onUpdate((current) => {
          const pending = current.pendingAttachments ?? [];
          if (pending.some((item) => item.id === uploaded.id)) return current;
          if (pending.length >= LARRY_ATTACH_MAX_FILES) return current;
          return { ...current, pendingAttachments: [...pending, uploaded] };
        });
      }
    } catch (error) {
      toastActionError(error, "attach that file", "Could not attach that file");
    } finally {
      setUploadingFiles(false);
    }
  }

  function removePending(mediaId: string) {
    onUpdate((current) => ({
      ...current,
      pendingAttachments: (current.pendingAttachments ?? []).filter((item) => item.id !== mediaId),
    }));
    void api.deleteNoteMedia(mediaId).catch(() => {
      /* still drop the chip */
    });
  }

  return { attachFiles, removePending };
}
