from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
root = Path(__file__).resolve().parent
(root/'assets').mkdir(exist_ok=True)
scale = 4
image = Image.new('RGBA', (256*scale,256*scale), (0,0,0,0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((8*scale,8*scale,248*scale,248*scale), radius=58*scale, fill='#4f46e5')
font = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',104*scale)
draw.text((128*scale,128*scale), 'PS', font=font, anchor='mm', fill='white')
draw.rounded_rectangle((64*scale,198*scale,192*scale,204*scale),radius=3*scale,fill='#a5b4fc')
image = image.resize((256,256), Image.Resampling.LANCZOS)
image.save(root/'assets/photosort.png')
image.save(root/'assets/photosort.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
