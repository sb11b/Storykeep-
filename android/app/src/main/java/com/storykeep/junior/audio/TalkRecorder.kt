package com.storykeep.junior.audio

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import java.io.ByteArrayOutputStream
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Mic capture for Talk. 16 kHz mono PCM-16, wrapped as WAV on [stop].
 *
 * The caller must hold RECORD_AUDIO before [start]; without it (or with a
 * busy mic) start fails cleanly with `false` instead of throwing. Capture
 * is bounded by [MAX_CLIP_BYTES] so a forgotten tap cannot record forever.
 *
 * The pump thread owns the AudioRecord: every way out of [pump] — the
 * [MAX_CLIP_BYTES] cap, a mic read error, or a [stop] / [halt] signal —
 * stops and releases the recorder on that thread, so no path can leave
 * the mic open. [stop] collects the buffered clip; [halt] only signals
 * and never blocks, so it is safe on lifecycle transitions.
 */
class TalkRecorder {

    private val pcm = ByteArrayOutputStream()

    /** Live while a session is recording; per-session, so sessions never cross-talk. */
    @Volatile
    private var live: AtomicBoolean? = null

    @Volatile
    private var reader: Thread? = null

    /** Opens the mic and starts capture. Returns false when the mic is unavailable. */
    fun start(): Boolean {
        if (live?.get() == true) return true
        val minBuffer = AudioRecord.getMinBufferSize(
            WavClip.SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        if (minBuffer <= 0) return false
        val recorder = try {
            AudioRecord(
                MediaRecorder.AudioSource.MIC,
                WavClip.SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                maxOf(minBuffer, BUFFER_BYTES),
            )
        } catch (e: SecurityException) {
            return false
        }
        if (recorder.state != AudioRecord.STATE_INITIALIZED) {
            recorder.release()
            return false
        }
        pcm.reset()
        val alive = AtomicBoolean(true)
        live = alive
        try {
            recorder.startRecording()
        } catch (e: IllegalStateException) {
            live = null
            recorder.release()
            return false
        }
        reader = Thread({ pump(recorder, alive) }, "junior-talk-mic").apply { start() }
        return true
    }

    /**
     * Signals capture to end without waiting for the pump thread. The pump
     * stops and releases the recorder as soon as its current read returns
     * (at most one ~128 ms chunk), so this never blocks the caller — for
     * kill paths that discard the clip.
     */
    fun halt() {
        live?.set(false)
    }

    /**
     * Stops capture and returns the clip as WAV bytes.
     * Returns an empty array when nothing usable was recorded.
     *
     * Signals the pump and waits for it to exit — it releases the recorder
     * on the way out — then returns the PCM it flushed. A clip cut short
     * by [MAX_CLIP_BYTES] is still returned in full.
     */
    fun stop(): ByteArray {
        live?.set(false)
        reader?.join(JOIN_TIMEOUT_MS)
        reader = null
        live = null
        val samples = pcm.toByteArray()
        pcm.reset()
        if (samples.size < MIN_CLIP_BYTES) return ByteArray(0)
        return WavClip.encode(samples)
    }

    private fun pump(recorder: AudioRecord, alive: AtomicBoolean) {
        val buffer = ByteArray(BUFFER_BYTES)
        var total = 0
        try {
            while (alive.get()) {
                val read = recorder.read(buffer, 0, buffer.size)
                if (!alive.get()) break // signalled mid-read: this session is over
                when {
                    read > 0 -> {
                        pcm.write(buffer, 0, read)
                        total += read
                        if (total >= MAX_CLIP_BYTES) {
                            // Clip is full: leave the loop. The recorder is
                            // released below and stop() still returns the
                            // buffered clip, so the 60 s cap loses no audio.
                            alive.set(false)
                        }
                    }
                    read < 0 -> alive.set(false)
                }
            }
        } finally {
            // Every exit path — size cap, mic error, or a stop()/halt()
            // signal — closes the mic here, on the thread that owns it.
            releaseRecorder(recorder)
        }
    }

    /** Stops and releases one recorder, guarding an already-closed mic. */
    private fun releaseRecorder(recorder: AudioRecord) {
        try {
            recorder.stop()
        } catch (e: IllegalStateException) {
            // Already stopped by the size cap or a mic error — releasing is still right.
        }
        try {
            recorder.release()
        } catch (e: IllegalStateException) {
            // Already released; nothing more to do.
        }
    }

    private companion object {
        const val BUFFER_BYTES = 4_096
        const val MIN_CLIP_BYTES = 3_200 // ~0.1 s at 16 kHz mono PCM-16
        const val MAX_CLIP_BYTES = 1_920_000 // ~60 s
        const val JOIN_TIMEOUT_MS = 1_000L
    }
}
