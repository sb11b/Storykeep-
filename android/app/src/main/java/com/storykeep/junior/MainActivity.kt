package com.storykeep.junior

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.ProcessLifecycleOwner
import com.storykeep.junior.data.JuniorSession
import com.storykeep.junior.ui.navigation.JuniorSessionFactory
import com.storykeep.junior.ui.navigation.StorykeepNav
import com.storykeep.junior.ui.theme.PaperCream
import com.storykeep.junior.ui.theme.StorykeepTheme

class MainActivity : ComponentActivity() {
    private val session: JuniorSession by viewModels {
        JuniorSessionFactory(application)
    }

    private val appLifecycleObserver = LifecycleEventObserver { _, event ->
        if (event == Lifecycle.Event.ON_STOP) {
            session.onAppBackgrounded()
        }
    }

    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        ProcessLifecycleOwner.get().lifecycle.addObserver(appLifecycleObserver)
        watchNetwork()
        enableEdgeToEdge()
        setContent {
            StorykeepTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = PaperCream) {
                    StorykeepNav(session)
                }
            }
        }
    }

    override fun onDestroy() {
        ProcessLifecycleOwner.get().lifecycle.removeObserver(appLifecycleObserver)
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        networkCallback?.let { cm.unregisterNetworkCallback(it) }
        networkCallback = null
        super.onDestroy()
    }

    private fun watchNetwork() {
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val request = NetworkRequest.Builder()
            .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .build()
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onLost(network: Network) {
                runOnUiThread { session.onNetworkLost() }
            }
        }
        networkCallback = callback
        cm.registerNetworkCallback(request, callback)
    }
}
