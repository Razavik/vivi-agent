from ursina import Button, color

# Класс Voxel определяет один куб в мире
class Voxel(Button):
    def __init__(self, position=(0,0,0), block_type='grass'):
        # Определяем цвета/текстуры в зависимости от типа блока
        block_colors = {
            'grass': color.lime,
            'dirt': color.brown,
            'stone': color.gray,
            'wood': color.rgb(139, 69, 19)
        }
        
        super().__init__(
            parent=None, # Родитель будет установлен в World
            position=position,
            model='cube',
            origin_y=0.5,
            texture='white_cube',
            color=block_colors.get(block_type, color.white),
            highlight_color=color.light_gray,
        )
        
        self.block_type = block_type

    def input(self, key):
        if self.hovered:
            # Левая кнопка мыши - разрушение блока
            if key == 'left mouse down':
                destroy(self)
            
            # Правая кнопка мыши - установка блока
            if key == 'right mouse down':
                # Определяем позицию для нового блока на основе нормали грани
                # Нормаль указывает направление от поверхности блока
                new_pos = self.position + self.mouse.normal
                # Создаем новый блок выбранного типа
                Voxel(position=new_pos, block_type=scene.player.selected_block_type)
                # Добавляем в словарь мира для сохранения
                scene.world.voxels[tuple(new_pos)] = new_pos
