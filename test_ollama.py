import ollama
import time

print("Testing embedding...")
start = time.time()
res = ollama.embeddings(model='nomic-embed-text', prompt='The commodification of education')
print(f"Embedding successful in {time.time()-start:.2f}s")
print("Testing LLM generation...")
start = time.time()
res = ollama.generate(model='llama3:8b', prompt='Write 50 words about education.')
print(f"Generation successful in {time.time()-start:.2f}s, length: {len(res['response'])}")
