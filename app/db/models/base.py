from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """
    Базовый класс для всех моделей.
    Все будущие таблицы будут наследоваться от него.
    """
    pass