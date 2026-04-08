import sys
import os
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

if __name__ == '__main__':
    # Load .env
    load_dotenv('.env')

    from app.services.api_clients import get_llm_client

    provider = os.getenv('TITLE_GENERATION_LLM_PROVIDER', 'GEMINI')
    # Use the default we set in config.py
    model = os.getenv('TITLE_GENERATION_LLM_MODEL', 'gemma-4-26b-a4b-it')
    api_key = os.getenv('GEMINI_API_KEY')

    print(f"Testing title generation with provider: {provider}, model: {model}")

    if not api_key:
        print("No GEMINI_API_KEY found in .env")
        sys.exit(1)

    # Dummy config just to pass to client
    dummy_config = {'LLM_MODEL': model, 'TITLE_GENERATION_LLM_MODEL': model}

    try:
        client = get_llm_client(provider, api_key, dummy_config)

        prompt = """
You are a specialized title generation system for audio transcriptions.
Your task is to analyze transcription content and create concise, relevant titles.

Guidelines:
- Titles must be 5 words or fewer
- Match the exact language of the transcription (e.g., English, Spanish, etc.)
- Capture the main topic or theme
- Maintain the style/tone of the original content
- Avoid generic titles like "Meeting Discussion" or "Audio Recording"
- Do not include metadata or file information in the title

Only respond with the title in the language of the transcription. No explanations or additional text.

Transcription Content:
---
In today's meeting we discussed the new Q3 marketing goals and how the team needs to align on performance metrics.
---

Generated Title:"""

        print("Calling generate_text...")
        result = client.generate_text(prompt, model=model)
        print(f"\nSUCCESS!\nGenerated Title: {result}")
    except Exception as e:
        print(f"\nERROR occurred: {e}")
        sys.exit(1)
