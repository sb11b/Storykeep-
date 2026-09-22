package com.storykeep.junior.ui.navigation

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.BookmarkBorder
import androidx.compose.material.icons.outlined.Forum
import androidx.compose.material.icons.outlined.MicNone
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import com.storykeep.junior.data.BottomTab
import com.storykeep.junior.ui.theme.Amber
import com.storykeep.junior.ui.theme.DeepInk
import com.storykeep.junior.ui.theme.InkSoft
import com.storykeep.junior.ui.theme.PaperCream
import com.storykeep.junior.ui.theme.PaperLine
import com.storykeep.junior.ui.theme.StorykeepTypography

@Composable
fun StorykeepBottomBar(
    selected: BottomTab,
    onTalk: () -> Unit,
    onStories: () -> Unit,
    onKeep: () -> Unit,
) {
    Column(Modifier.background(PaperCream)) {
        HorizontalDivider(color = PaperLine)
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.SpaceEvenly,
        ) {
            BarItem("Talk", Icons.Outlined.MicNone, selected == BottomTab.Talk, onTalk)
            BarItem("Stories", Icons.Outlined.Forum, selected == BottomTab.Stories, onStories)
            BarItem("Keep", Icons.Outlined.BookmarkBorder, selected == BottomTab.Keep, onKeep)
        }
    }
}

@Composable
private fun BarItem(
    label: String,
    icon: ImageVector,
    selected: Boolean,
    onClick: () -> Unit,
) {
    val color = if (selected) Amber else InkSoft
    Column(
        modifier = Modifier
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 4.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(icon, contentDescription = label, tint = color)
        Text(
            text = label,
            style = StorykeepTypography.labelSmall,
            color = if (selected) DeepInk else InkSoft,
        )
    }
}
