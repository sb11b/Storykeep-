package com.storykeep.junior.ui.stories

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.storykeep.junior.data.BottomTab
import com.storykeep.junior.data.JuniorSession
import com.storykeep.junior.data.SavedStory
import com.storykeep.junior.ui.navigation.StorykeepBottomBar
import com.storykeep.junior.ui.theme.Amber
import com.storykeep.junior.ui.theme.DeepInk
import com.storykeep.junior.ui.theme.OnAmber
import com.storykeep.junior.ui.theme.PaperCream
import com.storykeep.junior.ui.theme.PaperRaised
import com.storykeep.junior.ui.theme.StorykeepTypography

@Composable
fun StoriesScreen(
    session: JuniorSession,
    onTalk: () -> Unit,
    onType: () -> Unit,
    onHome: () -> Unit,
    onKeep: () -> Unit,
) {
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

@Composable
private fun StoryCard(story: SavedStory) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = PaperRaised,
    ) {
        Column(Modifier.padding(16.dp)) {
            Text(story.title, style = StorykeepTypography.titleMedium)
            Spacer(Modifier.height(4.dp))
            Text(story.whenLabel, style = StorykeepTypography.labelSmall)
            Spacer(Modifier.height(8.dp))
            Text(story.body, style = StorykeepTypography.bodyMedium, maxLines = 4)
        }
    }
}
