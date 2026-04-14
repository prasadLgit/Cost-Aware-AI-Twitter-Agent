import os
import re
from dotenv import load_dotenv
load_dotenv() 
from state import TweetState

from mail_reader import get_tweets_from_mail  
  
from langchain_core.messages import HumanMessage, AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
import tweepy
###-------------------------------------------setup twitter api-------------------------------------------####


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
####-------------------------------------------model setup-------------------------------------------######

api_key = os.getenv("API_KEY_NINTH")
if api_key is None:
    raise ValueError("API_KEY_SECOND environment variable is not set.")

def get_llm() -> ChatGoogleGenerativeAI:
    """Initialize and return a ChatGoogleGenerativeAI instance."""
    return ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", google_api_key=api_key, temperature=0.7)

####-------------------------------------------setup langgraph node -------------------------------------------######
def extract_tweet_id(url: str) -> str | None:
    match = re.search(r'/status/(\d+)', url)
    return match.group(1) if match else None


def extract_media_keys(obj) -> list:
    attachments = getattr(obj, "attachments", None)
    if isinstance(attachments, dict):
        return attachments.get("media_keys", [])
    elif attachments is not None and hasattr(attachments, "media_keys"):
        return list(attachments.media_keys or [])
    return []


def fetch_from_mail_and_quote(state: TweetState) -> TweetState:
    print("======================NODE: FETCH FROM MAIL======================")

    # 1. Get link + context from email
    mail_tweets = get_tweets_from_mail()

    if not mail_tweets:
        print("No mail data in state.")
        return state
    
    for mail_data in mail_tweets:
        tweet_url = mail_data["link"]
        context   = mail_data["context"]
        tweet_id  = extract_tweet_id(tweet_url)

        if not tweet_id:
            print("Could not extract tweet ID from link.")
            continue

        print(f"Tweet ID : {tweet_id}")
        print(f"Context  : {context}")

        # 2. Fetch the tweet from Twitter API
        client = get_twitter_client()
        try:
            result = client.get_tweet(
                id=tweet_id,
                tweet_fields=["text", "author_id", "attachments", "referenced_tweets"],
                expansions=[
                    "attachments.media_keys",
                    "referenced_tweets.id",
                    "referenced_tweets.id.attachments.media_keys",
                    "author_id",
                ],
                media_fields=["type", "url", "preview_image_url"],
                user_fields=["username"],
            )
        except Exception as e:
            print(f"Error fetching tweet: {e}")
            continue

        tweet = result.data
        if not tweet:
            print("Tweet not found.")
            continue

        # 3. Build media + ref tweet maps
        media_key_map = {}
        if result.includes and "media" in result.includes:
            for m in result.includes["media"]:
                media_key_map[m.media_key] = m

        ref_tweet_map = {}
        if result.includes and "tweets" in result.includes:
            for ref in result.includes["tweets"]:
                ref_tweet_map[ref.id] = ref

        username = "unknown"
        if result.includes and "users" in result.includes:
            username = result.includes["users"][0].username

        # 4. Main tweet media — skip if video
        main_keys  = extract_media_keys(tweet)
        main_media = [media_key_map[k] for k in main_keys if k in media_key_map]
        if any(getattr(m, "type", "") == "video" for m in main_media):
            print("Main tweet has video — using text only.")
            main_media = []

        # 5. Ref (quoted) tweet text + media — skip media if video
        quoted_text  = ""
        quoted_media = []
        for ref in (getattr(tweet, "referenced_tweets", None) or []):
            if getattr(ref, "type", "") != "quoted":
                continue
            quoted = ref_tweet_map.get(ref.id)
            if not quoted:
                continue
            q_keys  = extract_media_keys(quoted)
            q_media = [media_key_map[k] for k in q_keys if k in media_key_map]
            quoted_text  = getattr(quoted, "text", "")
            quoted_media = [] if any(getattr(m, "type", "") == "video" for m in q_media) else q_media
            break

        # 6. Build image blocks
        # 6. Build image blocks
        image_blocks = []
        for m in main_media + quoted_media:
            img_url = getattr(m, "url", None) or getattr(m, "preview_image_url", None)
            if img_url:
                image_blocks.append({
                    "type": "image_url",
                    "image_url": {"url": img_url}
                })

        # 7. Build prompt — inject context from email as the instruction
        if quoted_text:
            prompt_text = (
                f"You are Bully Maguire. Respond with savage sarcasm in under 200 characters.\n\n"
                f"Instruction: {context}\n\n"
                f"[MAIN TWEET by @{username}]:\n{tweet.text}\n\n"
                f"[QUOTED TWEET]:\n{quoted_text}"
            )
        else:
            prompt_text = (
                f"You are Bully Maguire. Respond with savage sarcasm in under 200 characters.\n\n"
                f"Instruction: {context}\n\n"
                f"[TWEET by @{username}]:\n{tweet.text}"
            )

        if image_blocks:
            print(f"Including {len(image_blocks)} image(s) in prompt")
            message = HumanMessage(content=[{"type": "text", "text": prompt_text}, *image_blocks])
        else:
            message = HumanMessage(content=prompt_text)

        # 8. LLM generates reply
        llm      = get_llm()
        response = llm.invoke([message])
        print("Generated response:", response.content)

        # 9. Post reply
        try:
            client.create_tweet(text=f"{response.content[:240]}\n{tweet_url}")
            print(f"Successfully posted reply to {tweet_url}")
        except Exception as e:
            print(f"Error posting tweet: {e}")

    return state


###------------------------------------------Testing Node Individually-----------------------------------------------------####
# builder = StateGraph(TweetState)

# builder.add_node(
#     "fetch_from_mail_and_quote",
#     fetch_from_mail_and_quote
# )
# builder.set_entry_point("fetch_from_mail_and_quote")
# builder.add_edge("fetch_from_mail_and_quote", END)

# graph = builder.compile()

# if __name__ == "__main__":
#     # Initialize state with tweets from mail
#     initial_state = TweetState(twitter_profiles=[])  # mail_tweets will be fetched inside the node
#     graph.invoke(initial_state)
