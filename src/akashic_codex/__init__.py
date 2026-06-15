"""AkashicCodex: a local, model-agnostic memory store for AI conversations.

The database is the product. Any model (Claude, Gemini, Ollama, ...) is just a
client that saves to and searches this store. No model-specific logic lives here.
"""

__version__ = "0.1.0"
