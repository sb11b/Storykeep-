package com.storykeep.junior.audio

import android.content.Context
import android.media.MediaPlayer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/** Plays Junior's spoken replies. */
interface TalkPlayer {
    suspend fun play(audio: ByteArray)

    fun stop()
}

/** Silent player — previews and tests where audio output is not wanted. */
class NoopTalkPlayer : TalkPlayer {
    override suspend fun play(audio: ByteArray) = Unit

    override fun stop() = Unit
}

/**
 * MediaPlayer-backed playback of the encoded audio the TTS endpoint returns.
 *
 * The bytes land in the cache dir (the backend answers base64, not a URL),
 * then play and clean up. One reply at a time: [play] stops whatever was
 * still sounding.
 */
class MediaTalkPlayer(private val context: Context) : TalkPlayer {

    // Written from the IO dispatcher in play(), read from the main thread in
    // stop(); @Volatile keeps the handoff visible across both.
    @Volatile
    private var player: MediaPlayer? = null

    @Volatile
    private var file: File? = null

    override suspend fun play(audio: ByteArray) {
        withContext(Dispatchers.IO) {
            stop()
            val target = File(context.cacheDir, "junior-reply-${System.nanoTime()}.audio")
            target.writeBytes(audio)
            val media = MediaPlayer()
            try {
                media.setDataSource(target.absolutePath)
                media.prepare()
                media.start()
                player = media
                file = target
            } catch (e: Exception) {
                media.release()
                target.delete()
            }
        }
    }

    override fun stop() {
        val media = player
        player = null
        media?.let {
            if (it.isPlaying) {
                it.stop()
            }
            it.release()
        }
        file?.delete()
        file = null
    }
}
