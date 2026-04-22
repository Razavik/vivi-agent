from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController

class Player(FirstPersonController):
    """
    Класс игрока, наследуется от FirstPersonController.
    Добавляет функционал для выбора типа блока и взаимодействия с миром.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.speed = 5  # Скорость перемещения
        self.jump_height = 2  # Высота прыжка
        self.gravity = 1  # Гравитация
        
        # Текущий выбранный блок (1-4)
        self.selected_block = 1
        
        # Текстуры для блоков
        self.block_types = [
            'grass',  # 1 - Трава
            'stone',  # 2 - Камень
            'dirt',   # 3 - Земля
            'wood'    # 4 - Дерево
        ]
        
        # Инициализация руки игрока (UI)
        self._setup_hand()
    
    @property
    def selected_block_type(self):
        """Возвращает название текущего выбранного блока по индексу."""
        return self.block_types[self.selected_block - 1]

    def _setup_hand(self):
        # Обновление UI для отображения выбранного блока
        self.hand = Entity(
            parent=camera.ui,
            model='cube',
            texture=self.block_types[0],
            scale=(0.2, 0.2),
            rotation=(150, -10, 0),
            position=(0.5, -0.6),
            color=color.white
        )

    def input(self, key):
        """
        Обработка ввода для переключения блоков (клавиши 1-4)
        """
        if key in ('1', '2', '3', '4'):
            self.selected_block = int(key)
            self.hand.texture = self.block_types[self.selected_block - 1]
            # Анимация выбора
            self.hand.scale = (0.3, 0.3)
            invoke(setattr, self.hand, 'scale', (0.2, 0.2), delay=0.1)

    def update(self):
        """
        Обновление состояния игрока каждый кадр
        """
        # Проверка на падение за пределы мира
        if self.y < -10:
            self.position = (0, 10, 0)
