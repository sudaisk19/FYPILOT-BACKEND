def call_llm(prompt: str, document: str):
    # Combine prompt and doc content
    context = f"Document:\n{document}\n\nUser Prompt:\n{prompt}\n\n"
    # Placeholder response - replace with actual LLM call
    return f"(Mock AI response based on doc) You asked: {prompt}"
