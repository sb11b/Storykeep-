package com.storykeep.junior.ui.stories

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Keyboard
import androidx.compose.material.icons.outlined.Mic
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.storykeep.junior.data.BottomTab
import com.storykeep.junior.data.JuniorSession
import com.storykeep.junior.network.ApiError
import com.storykeep.junior.network.JuniorDocumentDto
import com.storykeep.junior.ui.navigation.StorykeepBottomBar
import com.storykeep.junior.ui.theme.Amber
import com.storykeep.junior.ui.theme.DeepInk
import com.storykeep.junior.ui.theme.InkMuted
import com.storykeep.junior.ui.theme.OnAmber
import com.storykeep.junior.ui.theme.PaperCream
import com.storykeep.junior.ui.theme.PaperRaised
import com.storykeep.junior.ui.theme.StorykeepTypography

/**
 * The Stories screen: the owner's real saved stories from the shared-memory
 * documents API (`GET /junior/documents`).
 *
 * Honest states, same contract as the Conversation screen: a spinner while
 * the first load runs, a retry for Offline, an explicit 401 message for
 * Unauthorized, the HTTP status for Http, and an unreadable-body message for
 * Malformed. Nothing is fabricated — an empty list after a successful load
 * says so, and a failed load keeps the last known list rather than
 * inventing cards.
 */
@Composable
fun StoriesScreen(
    session: JuniorSession,
    onTalk: () -> Unit,
    onType: () -> Unit,
    onHome: () -> Unit,
    onKeep: () -> Unit,
) {
    // Real data: opening Stories loads the first page of documents.
    LaunchedEffect(Unit) {
        session.loadStories()
    }

    val error = session.storiesError
    val errorBanner: String? = when (error) {
        is ApiError.Unauthorized ->
            "The app's service token was rejected (401), so your stories could not load."
        is ApiError.Offline ->
            "You're offline. Your stories could not load — try again when you're back."
        is ApiError.Http ->
            "The stories service answered ${error.code}. Try again."
        is ApiError.Malformed ->
            "Your stories could not be read. Try again."
        null -> null
    }
    // A 401 will not fix itself on retry — hide the retry for it, show it
    // for every other failure (Offline, Http, Malformed).
    val errorIsRetryable = error != null && error !is ApiError.Unauthorized

    Scaffold(
        containerColor = PaperCream,
        floatingActionButton = {
            FloatingActionButton(
                onClick = onTalk,
                containerColor = Amber,
                contentColor = OnAmber,
                shape = RoundedCornerShape(18.dp),
            ) {
                Icon(Icons.Outlined.Add, contentDescription = "Record a story")
            }
        },
        bottomBar = {
            StorykeepBottomBar(
                selected = session.bottomTab,
                onTalk = onHome,
                onStories = { session.selectTab(BottomTab.Stories) },
                onKeep = onKeep,
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .background(PaperCream)
                .statusBarsPadding()
                .navigationBarsPadding()
                .padding(padding),
            contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            item {
                Text("Stories", style = StorykeepTypography.headlineMedium)
            }
            item {
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(18.dp),
                    color = PaperRaised,
                ) {
                    Column(Modifier.padding(18.dp)) {
                        Text("THIS WEEK’S QUESTION", style = StorykeepTypography.labelSmall)
                        Spacer(Modifier.height(8.dp))
                        Text(session.weeklyQuestion, style = StorykeepTypography.titleLarge)
                        Spacer(Modifier.height(16.dp))
                        Button(
                            onClick = onTalk,
                            modifier = Modifier.fillMaxWidth(),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = Amber,
                                contentColor = OnAmber,
                            ),
                            shape = RoundedCornerShape(14.dp),
                        ) {
                            Icon(Icons.Outlined.Mic, contentDescription = null)
                            Spacer(Modifier.size(8.dp))
                            Text("Answer by talking")
                        }
                        Spacer(Modifier.height(8.dp))
                        OutlinedButton(
                            onClick = onType,
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(14.dp),
                        ) {
                            Icon(Icons.Outlined.Keyboard, contentDescription = null)
                            Spacer(Modifier.size(8.dp))
                            Text("Answer by typing", color = DeepInk)
                        }
                    }
                }
            }
            if (session.storiesLoading && session.stories.isEmpty()) {
                item(key = "loading") {
                    Box(
                        modifier = Modifier.fillMaxWidth(),
                        contentAlignment = Alignment.Center,
                    ) {
                        CircularProgressIndicator(color = DeepInk)
                    }
                }
            }
            errorBanner?.let { banner ->
                item(key = "error") {
                    Surface(
                        color = PaperRaised,
                        shape = RoundedCornerShape(12.dp),
                    ) {
                        Column(Modifier.padding(horizontal = 14.dp, vertical = 10.dp)) {
                            Text(banner, style = StorykeepTypography.bodyMedium, color = DeepInk)
                            if (errorIsRetryable) {
                                TextButton(onClick = { session.retryStories() }) {
                                    Text("Try again")
                                }
                            }
                        }
                    }
                }
            }
            if (
                !session.storiesLoading &&
                session.stories.isEmpty() &&
                errorBanner == null
            ) {
                item(key = "empty") {
                    Text(
                        "No stories yet — answer this week's question and save it here.",
                        style = StorykeepTypography.bodyMedium,
                        color = InkMuted,
                    )
                }
            }
            items(session.stories, key = { it.id }) { story ->
                StoryCard(story)
            }
            item {
                OutlinedButton(
                    onClick = onTalk,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 72.dp),
                    shape = RoundedCornerShape(14.dp),
                ) {
                    Icon(Icons.Outlined.Add, contentDescription = null, tint = DeepInk)
                    Spacer(Modifier.size(8.dp))
                    Text("Record a story", color = DeepInk)
                }
            }
        }
    }
}

/**
 * One real story, straight from the documents API: [title], the backend's
 * updated timestamp, and [text]. Nothing here is fabricated — a document
 * the backend returned is a document you saved.
 */
@Composable
private fun StoryCard(story: JuniorDocumentDto) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = PaperRaised,
    ) {
        Column(Modifier.padding(16.dp)) {
            Text(story.title, style = StorykeepTypography.titleMedium)
            Spacer(Modifier.height(4.dp))
            Text("Updated ${story.updatedAt}", style = StorykeepTypography.labelSmall)
            Spacer(Modifier.height(8.dp))
            Text(story.text, style = StorykeepTypography.bodyMedium, maxLines = 4)
        }
    }
}
