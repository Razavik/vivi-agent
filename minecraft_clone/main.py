from ursina import *
from player import Player
from world import World

class Minecraft(App):
    """
    Главный класс приложения Minecraft.
    Инициализирует движок, игрока и мир.
    """
    def __init__(self):
        super().__init__()
        self.title = 'Minecraft Clone'
        self.window.fullscreen = False
        self.window.borderless = False
        self.window.resolution = (1280, 720)
        self.world = World()
        self.player = Player()
        self.sky = Sky()
        
        # Привязываем объекты к глобальному scene для доступа из voxel.py
        scene.player = self.player
        scene.world = self.world
        
        # Генерация мира при старте
        self.world.generate_world()
        
        # Добавляем подсказки на экран
        self.tooltip = Text(
            text='WASD - Перемещение | ЛКМ - Ломать | ПКМ - Строить | 1-4 - Выбор блока',
            position=(-0.85, 0.45),
            scale=1.5,
            origin=(0, 0),
            color=color.black
        )

    def input(self, key):
        """
        Обработка глобального ввода
        """
        # Сохранение мира на S
        if key == 's':
            self.world.save_world()
        
        # Загрузка мира на L
        if key == 'l':
            self.world.load_world()
        
        # Выход на ESC
        if key == 'escape':
            quit()

if __name__ == '__main__':
    app = Minecraft()
    app.run()
