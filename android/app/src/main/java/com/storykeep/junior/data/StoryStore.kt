package com.storykeep.junior.data

import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

data class SavedStory(
    val id: String = UUID.randomUUID().toString(),
    val title: String,
    val body: String,
    val whenLabel: String,
)

interface StoryStore {
    fun load(): List<SavedStory>
    fun save(stories: List<SavedStory>)
}

class MemoryStoryStore(
    initial: List<SavedStory> = seedStories(),
) : StoryStore {
    private var stories: List<SavedStory> = initial

    override fun load(): List<SavedStory> = stories

    override fun save(stories: List<SavedStory>) {
        this.stories = stories
    }
}

class PrefsStoryStore(
    private val prefs: SharedPreferences,
) : StoryStore {
    override fun load(): List<SavedStory> {
        val raw = prefs.getString(KEY, null) ?: return seedStories()
        return runCatching { decode(raw) }.getOrElse { seedStories() }
    }

    override fun save(stories: List<SavedStory>) {
        prefs.edit().putString(KEY, encode(stories)).apply()
    }

    private fun encode(stories: List<SavedStory>): String {
        val array = JSONArray()
        stories.forEach { story ->
            array.put(
                JSONObject()
                    .put("id", story.id)
                    .put("title", story.title)
                    .put("body", story.body)
                    .put("whenLabel", story.whenLabel),
            )
        }
        return array.toString()
    }

    private fun decode(raw: String): List<SavedStory> {
        val array = JSONArray(raw)
        return buildList {
            for (i in 0 until array.length()) {
                val obj = array.getJSONObject(i)
                add(
                    SavedStory(
                        id = obj.getString("id"),
                        title = obj.getString("title"),
                        body = obj.getString("body"),
                        whenLabel = obj.getString("whenLabel"),
                    ),
                )
            }
        }
    }

    companion object {
        const val PREFS_NAME = "junior_stories"
        private const val KEY = "stories_json"
    }
}

fun seedStories(): List<SavedStory> = listOf(
    SavedStory(
        title = "River path",
        body = "A placeholder card. Real saves will be transcript text only in v1.",
        whenLabel = "Earlier this month",
    ),
    SavedStory(
        title = "Kitchen light",
        body = "Another local stub so the Stories list can be walked on a device.",
        whenLabel = "Last week",
    ),
)
