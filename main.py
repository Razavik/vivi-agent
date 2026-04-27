from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import random

app = Ursina()

window.borderless = False
window.title = 'Ursina Minecraft Clone'

# текстуры блоков (используются встроенные в Ursina)
textures = {
    'grass': 'grass_block',
    'dirt': 'dirt',
    'stone': 'stone',
}

# текущий выбранный тип блока
current_block = 'grass'

class Voxel(Button):
    def __init__(self, position=(0,0,0), texture='grass'):
        super().__init__(
            parent=scene,
            position=position,
            model='cube',
            origin_y=0.5,
            texture=texture,
            color=color.color(0, 0, random.uniform(0.9, 1)),
            scale=0.5,
            highlight_color=color.lime,
        )

    def input(self, key):
        if self.hovered:
            if key == 'left mouse down':
                Voxel(position=self.position + mouse.normal, texture=current_block)
            if key == 'right mouse down':
                destroy(self)

def input(key):
    global current_block
    if key == '1':
        current_block = 'grass'
    elif key == '2':
        current_block = 'dirt'
    elif key == '3':
        current_block = 'stone'

# генерация простого пола из блоков
for x in range(10):
    for z in range(10):
        Voxel(position=(x, 0, z), texture='grass')

# управление игроком
player = FirstPersonController()
player.cursor.visible = False

app.run()
