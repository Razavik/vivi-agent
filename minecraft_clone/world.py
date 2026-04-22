import json
from voxel import Voxel
from ursina import entity

class World:
    """Класс для управления миром, генерации ландшафта и сохранения данных."""
    def __init__(self):
        self.voxels = {}
        self.chunk_size = 16

    def generate_world(self, seed=None):
        """
        Простая генерация ландшафта.
        В реальном проекте здесь использовался бы Perlin Noise из библиотеки noise.
        Для данного примера реализуем случайные высоты с плавным переходом.
        """
        import random
        
        # Создаем базовую поверхность 20x20
        for z in range(20):
            for x in range(20):
                # Случайная высота от 0 до 3 для имитации неровностей
                height = random.randint(0, 2)
                
                # Создаем блоки земли/травы
                for y in range(height + 1):
                    block_type = 'grass' if y == height else 'dirt'
                    Voxel(position=(x, y, z), block_type=block_type)

    def save_world(self, filename='world_save.json'):
        """Сохраняет позиции и типы всех блоков в JSON файл."""
        data = []
        # Ищем все объекты Voxel в сцене ursina
        for v in [e for e in entity.entities if isinstance(e, Voxel)]:
            data.append({
                'pos': list(v.position),
                'type': v.block_type
            })
        
        with open(filename, 'w') as f:
            json.dump(data, f)
        print(f"Мир сохранен в {filename}")

    def load_world(self, filename='world_save.json'):
        """Загружает блоки из JSON файла."""
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
                for item in data:
                    Voxel(position=tuple(item['pos']), block_type=item['type'])
            print(f"Мир загружен из {filename}")
        except FileNotFoundError:
            print("Файл сохранения не найден, генерирую новый мир...")
            self.generate_world()