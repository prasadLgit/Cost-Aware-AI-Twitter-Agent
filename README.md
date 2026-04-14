# Cost-Aware-AI-Twitter-Agent
An AI-driven Twitter bot that generates context-aware replies using LangGraph, with a cost-optimized pipeline and email-based control system.

🧠 Features
📩 Email-based input for tweet links and instructions
🐦 Fetches tweets and referenced tweets via Twitter API
🖼️ Extracts images and includes them in LLM input
🎯 Scores tweets based on engagement (likes, replies, quotes)
🔁 Prevents duplicate processing of tweets
⚡ Cost-aware design to reduce unnecessary API usage

                        START
  │
  ▼
route_node (30% / 70%)
  │
  ├───────────────--------------┐
  │                             │
  ▼                             ▼
fetch_tweets_from_mail    fetch_tweets_auto
  │                             │
  ▼                             ▼
llm_generate               llm_generate
  │                             │
  ▼                             ▼
post_tweet                   post_tweet
  │                              │
  └───────┬───────---------------┘
          ▼
         END


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
