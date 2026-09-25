package com.storykeep.junior.data

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
