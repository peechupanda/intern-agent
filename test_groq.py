from langchain_groq import ChatGroq
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=r"C:\Users\ishaa\intern-agent\.env")
print("Key found:", bool(os.getenv("GROQ_API_KEY")))

llm = ChatGroq(model="llama-3.3-70b-versatile")
response = llm.invoke("Say hello in one sentence.")
print(response.content)