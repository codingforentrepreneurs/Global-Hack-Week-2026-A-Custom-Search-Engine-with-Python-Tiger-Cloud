from django.conf import settings
from openai import OpenAI


def get_embeddings(texts):
    if not settings.OPENAI_API_KEY:
        raise NotImplementedError("Set OPENAI_API_KEY in .env to enable embeddings")
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [item.embedding for item in response.data]
