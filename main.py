"""

A Bully Maguire-inspired AI that selects high-engagement tweets and responds
 with natural sarcasm — designed to behave like a personality, not automation.

"""
from fetch_tweets_from_mail import fetch_from_mail_and_quote

import random
import os
import tweepy
import json
import requests
import base64
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()  # Load environment variables from .env file

###-------------------------------------------setup file storage--------------------------------------------------------####

def load_processed_tweets() -> set:
    """Load processed tweet IDs from a file into a set."""
    file_path = "processed_tweets.json"
    if not os.path.exists(file_path):
        return set()
    with open(file_path, "r") as f:
        data = json.load(f)
        return set(data)

def save_processed_tweets(processed_tweets: set):
    """Save the set of processed tweet IDs to a file."""
    file_path = "processed_tweets.json"
    with open(file_path, "w") as f:
        json.dump(list(processed_tweets), f)

processed_tweets = load_processed_tweets()

####-------------------------------------------setup twitter api-------------------------------------------####

TWITTER_BEARER_TOKEN = os.getenv("BEARER_TOKEN")
TWITTER_API_KEY = os.getenv("CONSUMER_KEY")
TWITTER_API_SECRET = os.getenv("CONSUMER_KEY_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")

def get_twitter_client() -> tweepy.Client:
    """Initialize and return a Tweepy v2 client."""
    return tweepy.Client(
        bearer_token=TWITTER_BEARER_TOKEN,
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
        wait_on_rate_limit=True,
    )

####-------------------------------------------setup langchain-------------------------------------------######

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import MessagesState
from langgraph.graph import StateGraph, START, END

from typing import Annotated, List, Any, Literal, Optional
from typing_extensions import TypedDict
from operator import add
from pydantic import BaseModel, Field

###-------------------------------------------setup llm-------------------------------------------######

api_key = os.getenv("API_KEY_FIFTH")
if api_key is None:
    raise ValueError("API_KEY_SECOND environment variable is not set.")

def get_llm() -> ChatGoogleGenerativeAI:
    """Initialize and return a ChatGoogleGenerativeAI instance."""
    return ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", google_api_key=api_key, temperature=0.7)

###-------------------------------------------define the state-------------------------------------------######

from state import TweetState
# class TweetState(TypedDict):
#     tweet_id: str
#     author_username: str
#     content: str
#     twitter_profiles: list[str]
#     response: Optional[str]

###-------------------------------------------helper functions-------------------------------------------######

def calaulate_score(tweet) -> int:
    """Calculate an engagement score for a tweet based on its public metrics."""
    metrics = tweet.public_metrics
    likes = metrics.get("like_count", 0)
    retweets = metrics.get("retweet_count", 0)
    replies = metrics.get("reply_count", 0)
    quotes = metrics.get("quote_count", 0)
    score = likes + (retweets * 2) + (replies * 4) + (quotes * 6)
    return score


def get_best_tweet(tweets, tweet_media_index: dict, quoted_media_index: dict):
    """
    Select the highest-scoring tweet that hasn't been processed yet.
    Skips tweets where the main tweet OR the quoted tweet contains a video.
    """
    if not tweets:
        print("No tweets found for the query.")
        return None

    
    best_score = 100
    best_tweets = []
    for tweet in tweets:
        
        if len(tweet.text) < 20:
            print(f"Skipping low-content tweet: {tweet.id}")
            continue

        if tweet.id in processed_tweets:
            print(f"Skipping already processed tweet ID: {tweet.id}")
            continue

        # Check both main tweet and quoted tweet for videos
        main_media = tweet_media_index.get(tweet.id, [])
        quoted_media = quoted_media_index.get(tweet.id, [])
        all_media = main_media + quoted_media
        if any(getattr(m, "type", "") == "video" for m in all_media):
            print(f"Skipping tweet {tweet.id} — contains video (main or quoted)")
            continue

        score = calaulate_score(tweet)
        print(f"Tweet ID: {tweet.id}, Score: {score}")
        if score > best_score:
            best_tweets.append(tweet)
        

    print("==" * 50)
    return random.choice(best_tweets) if best_tweets else None


def _media_to_base64_block(media) -> dict | None:
    """Fetch a single Media object and return a base64 image_url block, or None on failure."""
    url = getattr(media, "url", None) or getattr(media, "preview_image_url", None)
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        b64 = base64.b64encode(resp.content).decode("utf-8")
        mime = resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
        return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
    except Exception as e:
        print(f"Failed to fetch image {url}: {e}")
        return None


def get_tweet_images_labeled(
    tweet,
    tweet_media_index: dict,
    quoted_media_index: dict,
) -> list[dict]:
    """
    Return a labeled list of LangChain content blocks:
      - a text label block before each group so the LLM knows the source
      - base64 image blocks for the main tweet
      - base64 image blocks for the quoted tweet (if any)

    Returns an empty list if neither tweet has images.
    """
    content_blocks = []

    # ── Main tweet images ──
    main_media = [m for m in tweet_media_index.get(tweet.id, []) if getattr(m, "type", "") == "photo"]
    if main_media:
        content_blocks.append({"type": "text", "text": "[Image(s) from the MAIN tweet above:]"})
        for media in main_media:
            block = _media_to_base64_block(media)
            if block:
                content_blocks.append(block)

    # ── Quoted tweet images ──
    quoted_media = [m for m in quoted_media_index.get(tweet.id, []) if getattr(m, "type", "") == "photo"]
    if quoted_media:
        content_blocks.append({"type": "text", "text": "[Image(s) from the QUOTED tweet being referenced:]"})
        for media in quoted_media:
            block = _media_to_base64_block(media)
            if block:
                content_blocks.append(block)

    return content_blocks


###-------------------------------------------nodes-------------------------------------------######

def fetch_tweets_and_quote(state: TweetState) -> TweetState:
    print("======================NODE: FETCH TWEETS======================")
    client = get_twitter_client()
    
    
    user_name = random.choice(state["twitter_profiles"])
    print(f"Selected profile: {user_name}")
    
    user = client.get_user(username="TrumpDailyPosts")
    username = user.data.username
    user_id = user.data.id

    try:
        tweets = client.get_users_tweets(
            id=user_id,
            max_results=5,
            tweet_fields=["public_metrics", "author_id", "attachments", "referenced_tweets", "text"],
            expansions=[
                "attachments.media_keys",
                "referenced_tweets.id",                        # pull quoted tweet objects
                "referenced_tweets.id.attachments.media_keys", # pull quoted tweet media
            ],
            media_fields=["type", "url", "preview_image_url"],
        )

        # ── media_key → Media object ──
        media_key_map: dict = {}
        if tweets.includes and "media" in tweets.includes:
            for m in tweets.includes["media"]:
                media_key_map[m.media_key] = m

        # ── referenced tweet id → tweet object ──
        ref_tweet_map: dict = {}
        if tweets.includes and "tweets" in tweets.includes:
            for ref in tweets.includes["tweets"]:
                ref_tweet_map[ref.id] = ref

        def extract_media_keys(obj) -> list:
            """Safely extract media_keys from an attachments dict or object."""
            attachments = getattr(obj, "attachments", None)
            if isinstance(attachments, dict):
                return attachments.get("media_keys", [])
            elif attachments is not None and hasattr(attachments, "media_keys"):
                return list(attachments.media_keys or [])
            return []

        # ── tweet_id → [Media] for main tweet attachments ──
        tweet_media_index: dict = {}
        # ── tweet_id → [Media] for its quoted tweet's attachments ──
        quoted_media_index: dict = {}
        # ── tweet_id → quoted tweet text ──
        quoted_text_map: dict = {}

        if tweets.data:
            for tweet in tweets.data:
                # Main tweet media
                keys = extract_media_keys(tweet)
                tweet_media_index[tweet.id] = [media_key_map[k] for k in keys if k in media_key_map]

                # Quoted tweet media + text
                referenced = getattr(tweet, "referenced_tweets", None) or []
                for ref in referenced:
                    if getattr(ref, "type", "") != "quoted":
                        continue
                    quoted = ref_tweet_map.get(ref.id)
                    if not quoted:
                        continue
                    q_keys = extract_media_keys(quoted)
                    quoted_media_index[tweet.id] = [media_key_map[k] for k in q_keys if k in media_key_map]
                    quoted_text_map[tweet.id] = getattr(quoted, "text", "")
                    break  # only one quoted tweet per tweet

        best_tweet = get_best_tweet(tweets.data, tweet_media_index, quoted_media_index)
        if not best_tweet:
            print("No suitable tweet found.")
            return state

        print("Best tweet:", best_tweet.text)

        # ── Build labeled LLM prompt ──
        quoted_text = quoted_text_map.get(best_tweet.id, "")
        image_blocks = get_tweet_images_labeled(best_tweet, tweet_media_index, quoted_media_index)

        # Compose the text description clearly for the LLM
        if quoted_text:
            prompt_text = (
                f"You are Bully Maguire. Respond with savage sarcasm in under 200 characters.\n\n"
                f"[MAIN TWEET by @{username}]:\n{best_tweet.text}\n\n"
                f"[QUOTED TWEET being mocked/referenced]:\n{quoted_text}"
            )
        else:
            prompt_text = (
                f"You are Bully Maguire. Respond with savage sarcasm in under 200 characters.\n\n"
                f"[TWEET by @{username}]:\n{best_tweet.text}"
            )

        if image_blocks:
            print(f"Including {len(image_blocks)} content block(s) (images + labels) in LLM prompt")
            content = [{"type": "text", "text": prompt_text}, *image_blocks]
            message = HumanMessage(content=content)
        else:
            message = HumanMessage(content=prompt_text)

        llm = get_llm()
        response = llm.invoke([message])
        print("Generated response:", response.content)

        # Post the reply tweet
        try:
            tweet_text = (
                f"{response.content[:240]}\n"
                f"https://twitter.com/{username}/status/{best_tweet.id}"
            )
            client.create_tweet(text=tweet_text)
            processed_tweets.add(best_tweet.id)
            save_processed_tweets(processed_tweets)
            print(f"Successfully posted reply to tweet {best_tweet.id}")

        except Exception as e:
            print("Error posting tweet:", e)
            return state

    except Exception as e:
        print("Error fetching tweets:", e)
        return state

    return state
####-------------------------------------------route node--------------------------------------------####

def route_node(state: TweetState) -> str:
    roll = random.random()
    if roll < 0.3:
        print(f"Roll {roll:.2f} → mail fetch (30%)")
        return "fetch_tweets_from_mail"
    else:
        print(f"Roll {roll:.2f} → auto fetch (70%)")
        return "fetch_tweets_and_quote"
    
###-------------------------------------------graph-------------------------------------------######

def build_twitter_bot_graph() -> StateGraph:
    builder = StateGraph(TweetState)
    builder.add_node("fetch_tweets_auto", fetch_tweets_and_quote,
                     description="Fetch recent tweets, score by engagement, generate and post a Bully Maguire reply.")
    builder.add_node("fetch_tweets_from_mail", fetch_from_mail_and_quote,
                     description="Fetch tweet links and context from email, generate and post a Bully Maguire")
    builder.add_conditional_edges(START,
                     route_node,
                     {
                            "fetch_tweets_from_mail": "fetch_tweets_from_mail",
                            "fetch_tweets_and_quote": "fetch_tweets_auto"

                     }
                )
    builder.add_edge("fetch_tweets_auto", END)
    builder.add_edge("fetch_tweets_from_mail", END)
    return builder.compile()

###-------------------------------------------runner-------------------------------------------######

def run_twitter_bot():
    graph = build_twitter_bot_graph()
    initial_state = TweetState(
        twitter_profiles=["elonmusk", "OoeTobeyM", "realDonaldTrump"]
    )
    final_state = graph.invoke(initial_state)
    return final_state

###-------------------------------------------entry point-------------------------------------------######

if __name__ == "__main__":
    # import schedule
    # import time

    def job():
        print(f"\n{'=='*30}")
        print(f"Running bot at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=='*30}")
        run_twitter_bot()

    # schedule.every(1).hours.do(job)
    print("Scheduler started — running every 1 hour")
    job()  # run immediately on start

    # while True:
    #     schedule.run_pending()
    #     time.sleep(60)