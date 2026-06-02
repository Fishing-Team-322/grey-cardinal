"""In-process планировщик reminders/digest.

Организован так, чтобы позже его можно было вынести в отдельный brain-worker
без изменения use cases (jobs лишь собирают UoW и вызывают use case'ы).
"""
