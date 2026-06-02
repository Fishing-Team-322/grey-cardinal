"""Доменные ошибки brain-api."""

from __future__ import annotations


class DomainError(Exception):
    """Базовая доменная ошибка."""


class EntityNotFoundError(DomainError):
    """Сущность не найдена (задача, confirmation, чат и т.п.)."""


class TaskNotFoundError(EntityNotFoundError):
    pass


class ConfirmationNotFoundError(EntityNotFoundError):
    pass


class InvalidStatusTransitionError(DomainError):
    """Недопустимый переход статуса задачи."""


class BoardError(DomainError):
    """Ошибка внешней доски. Не должна терять локальную задачу — только логируется."""
