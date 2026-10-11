package com.storykeep.junior.audio

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import java.io.ByteArrayOutputStream

/**
 * Mic capture for Talk. 16 kHz mono PCM-16, wrapped as WAV on [stop].
 *
 * The caller must hold RECORD_AUDIO before [start]; without it (or with a
 * busy mic) start fails cleanly with `false` instead of throwing. Capture
 * is bounded by [MAX_CLIP_BYTES] so a forgotten tap cannot record forever.
 */
class TalkRecorder {

    private var record: AudioRecord? = null
    private var reader: Thread? = null
    private val pcm = ByteArrayOutputStream()

    @Volatile
    private var capturing = false

    /** Opens the mic and starts capture. Returns false when the mic is unavailable. */
    fun start(): Boolean {
        if (capturing) return true
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
        capturing = true
        try {
            recorder.startRecording()
        } catch (e: IllegalStateException) {
            capturing = false
            recorder.release()
            return false
        }
        record = recorder
        reader = Thread({ pump(recorder) }, "junior-talk-mic").apply { start() }
        return true
    }

    /**
     * Stops capture and returns the clip as WAV bytes.
     * Returns an empty array when nothing usable was recorded.
     */
    fun stop(): ByteArray {
        if (!capturing) return ByteArray(0)
        capturing = false
        val recorder = record
        record = null
        reader?.join(JOIN_TIMEOUT_MS)
        reader = null
        try {
            recorder?.stop()
        } catch (e: IllegalStateException) {
            // Already stopped by the size cap — the buffered PCM is still good.
        }
        recorder?.release()
        val samples = pcm.toByteArray()
        pcm.reset()
        if (samples.size < MIN_CLIP_BYTES) return ByteArray(0)
        return WavClip.encode(samples)
    }

    private fun pump(recorder: AudioRecord) {
        val buffer = ByteArray(BUFFER_BYTES)
        var total = 0
        while (capturing) {
            val read = recorder.read(buffer, 0, buffer.size)
            when {
                read > 0 -> {
                    pcm.write(buffer, 0, read)
                    total += read
                    if (total >= MAX_CLIP_BYTES) {
                        capturing = false
                    }
                }
                read < 0 -> capturing = false
            }
        }
    }

    private companion object {
        const val BUFFER_BYTES = 4_096
        const val MIN_CLIP_BYTES = 3_200 // ~0.1 s at 16 kHz mono PCM-16
        const val MAX_CLIP_BYTES = 1_920_000 // ~60 s
        const val JOIN_TIMEOUT_MS = 1_000L
    }
}
