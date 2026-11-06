from docuflow.config import get_llm, get_embeddings

print(get_llm().invoke("in on sentence, what is the invoice meaning ?").content)