package com.example.hello

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import com.example.hello.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.textViewHello.text = getString(R.string.hello_world)
        binding.buttonClickMe.setOnClickListener {
            binding.textViewHello.text = getString(R.string.button_clicked)
        }
    }
}
