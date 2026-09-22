package com.storykeep.junior.ui.navigation

import android.app.Application
import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.storykeep.junior.data.BottomTab
import com.storykeep.junior.data.EntryMode
import com.storykeep.junior.data.JuniorSession
import com.storykeep.junior.data.PrefsStoryStore
import com.storykeep.junior.ui.conversation.ConversationScreen
import com.storykeep.junior.ui.home.HomeScreen
import com.storykeep.junior.ui.stories.StoriesScreen

object Routes {
    const val Home = "home"
    const val Stories = "stories"
    const val Conversation = "conversation/{mode}"

    fun conversation(mode: EntryMode): String = "conversation/${mode.name}"
}

class JuniorSessionFactory(
    private val application: Application,
) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        val prefs = application.getSharedPreferences(
            PrefsStoryStore.PREFS_NAME,
            Context.MODE_PRIVATE,
        )
        return JuniorSession(PrefsStoryStore(prefs)) as T
    }
}

@Composable
fun rememberJuniorSession(): JuniorSession {
    val application = LocalContext.current.applicationContext as Application
    return viewModel(factory = JuniorSessionFactory(application))
}

@Composable
fun StorykeepNav(session: JuniorSession = rememberJuniorSession()) {
    val nav = rememberNavController()

    fun openConversation(mode: EntryMode) {
        session.openConversation(mode)
        nav.navigate(Routes.conversation(mode))
    }

    fun goHome(ended: Boolean) {
        if (ended) {
            session.endConversation()
        } else {
            session.leaveConversation()
        }
        session.selectTab(BottomTab.Talk)
        nav.popBackStack(Routes.Home, inclusive = false)
        if (nav.currentDestination?.route != Routes.Home) {
            nav.navigate(Routes.Home) {
                popUpTo(Routes.Home) { inclusive = true }
                launchSingleTop = true
            }
        }
    }

    fun goStories() {
        session.selectTab(BottomTab.Stories)
        nav.navigate(Routes.Stories) {
            popUpTo(Routes.Home) { inclusive = false }
            launchSingleTop = true
        }
    }

    NavHost(navController = nav, startDestination = Routes.Home) {
        composable(Routes.Home) {
            HomeScreen(
                session = session,
                onTalk = { openConversation(EntryMode.Talk) },
                onType = { openConversation(EntryMode.Type) },
                onStories = { goStories() },
                onKeep = {
                    session.selectTab(BottomTab.Keep)
                },
            )
        }
        composable(Routes.Stories) {
            StoriesScreen(
                session = session,
                onTalk = { openConversation(EntryMode.Talk) },
                onType = { openConversation(EntryMode.Type) },
                onHome = {
                    session.selectTab(BottomTab.Talk)
                    nav.popBackStack(Routes.Home, inclusive = false)
                },
                onKeep = {
                    session.selectTab(BottomTab.Keep)
                    nav.popBackStack(Routes.Home, inclusive = false)
                },
            )
        }
        composable(
            route = Routes.Conversation,
            arguments = listOf(navArgument("mode") { type = NavType.StringType }),
        ) {
            ConversationScreen(
                session = session,
                onBack = { goHome(ended = false) },
                onEnd = { goHome(ended = true) },
            )
        }
    }
}
