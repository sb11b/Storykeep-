package com.storykeep.junior.audio

/**
 * Wraps raw PCM-16 mono into a RIFF/WAVE container — the exact shape the
 * backend STT clip route accepts (`audio/wav`).
 *
 * Pure JVM on purpose: no Android imports, so the header can be covered by
 * unit tests without a device.
 */
internal object WavClip {

    const val SAMPLE_RATE = 16_000
    const val CHANNELS = 1
    const val BITS_PER_SAMPLE = 16

    private const val HEADER_BYTES = 44

    /** Returns a complete WAV file wrapping [pcm]. */
    fun encode(pcm: ByteArray): ByteArray {
        val out = ByteArray(HEADER_BYTES + pcm.size)
        ascii("RIFF", out, 0)
        leInt(36 + pcm.size, out, 4)
        ascii("WAVE", out, 8)
        ascii("fmt ", out, 12)
        leInt(16, out, 16) // PCM fmt chunk size
        leShort(1, out, 20) // format = PCM
        leShort(CHANNELS, out, 22)
        leInt(SAMPLE_RATE, out, 24)
        leInt(SAMPLE_RATE * CHANNELS * BITS_PER_SAMPLE / 8, out, 28) // byte rate
        leShort(CHANNELS * BITS_PER_SAMPLE / 8, out, 32) // block align
        leShort(BITS_PER_SAMPLE, out, 34)
        ascii("data", out, 36)
        leInt(pcm.size, out, 40)
        pcm.copyInto(out, HEADER_BYTES)
        return out
    }

    private fun ascii(text: String, out: ByteArray, offset: Int) {
        for (i in text.indices) {
            out[offset + i] = text[i].code.toByte()
        }
    }

    private fun leInt(value: Int, out: ByteArray, offset: Int) {
        out[offset] = (value and 0xFF).toByte()
        out[offset + 1] = ((value shr 8) and 0xFF).toByte()
        out[offset + 2] = ((value shr 16) and 0xFF).toByte()
        out[offset + 3] = ((value shr 24) and 0xFF).toByte()
    }

    private fun leShort(value: Int, out: ByteArray, offset: Int) {
        out[offset] = (value and 0xFF).toByte()
        out[offset + 1] = ((value shr 8) and 0xFF).toByte()
    }
}
