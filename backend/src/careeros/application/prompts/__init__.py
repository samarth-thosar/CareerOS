"""Prompt construction -- what CareerOS asks a model, independent of how any model is addressed.

These modules build model-agnostic `PromptSpec`s. Chat templating, thinking-mode handling, and other
backend-specific concerns belong to the concrete `LLMProvider` adapter, never here.
"""
