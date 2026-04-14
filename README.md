# Cost-Aware-AI-Twitter-Agent
An AI-driven Twitter bot that generates context-aware replies using LangGraph, with a cost-optimized pipeline and email-based control system.

🧠 Features
📩 Email-based input for tweet links and instructions
🐦 Fetches tweets and referenced tweets via Twitter API
🖼️ Extracts images and includes them in LLM input
🎯 Scores tweets based on engagement (likes, replies, quotes)
🔁 Prevents duplicate processing of tweets
⚡ Cost-aware design to reduce unnecessary API usage


Email → Fetch Tweet → Extract Media → LLM → Generate Reply → Post to Twitter


⚙️ Tech Stack
Python
LangGraph
LangChain
Twitter API (Tweepy)
Gemini (Google Generative AI)
IMAP (Email parsing)


📌 Notes
Supports both manual (email-triggered) and automated tweet selection
Uses a personality-based response style (sarcastic tone)
Designed with simplicity and efficiency in mind
