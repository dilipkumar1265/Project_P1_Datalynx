import ollama

prompt = """
You are a SQL generator.
Just reply 'OK if model works'.
"""

response = ollama.chat(
    model="mistral",
    messages=[{"role": "user", "content": prompt}]
)

print(response["message"]["content"])
