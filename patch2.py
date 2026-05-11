import re

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# We need to move <canvas id="synapse-canvas"></canvas> inside #rings-container

# Find the rings-container
rings_pattern = r'(<div id="rings-container">.*?<div class="ring ring-inner"></div>)'
replacement = r'\1\n        <canvas id="synapse-canvas"></canvas>'

content = re.sub(rings_pattern, replacement, content, flags=re.DOTALL)

# Remove the old one at the bottom
content = re.sub(r'\s*<canvas id="synapse-canvas"></canvas>(?=\s*</div>\s*<!-- Right: Chat -->)', '', content, flags=re.DOTALL)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Patch 2 applied!")
