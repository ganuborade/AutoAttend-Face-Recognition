import os

def replace_in_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            content = file.read()
        
        if 'VisionAI' in content:
            new_content = content.replace('VisionAI', 'AutoAttend')
            with open(filepath, 'w', encoding='utf-8') as file:
                file.write(new_content)
            print(f"Replaced in {filepath}")
    except Exception as e:
        print(f"Error processing {filepath}: {e}")

for root, dirs, files in os.walk(r'd:\Face_Reconition_Based_Attendance_System'):
    if '.git' in root or '__pycache__' in root or 'venv' in root or '.venv' in root or '.gemini' in root:
        continue
    for file in files:
        if file.endswith('.py') or file.endswith('.html') or file.endswith('.css') or file.endswith('.js') or file.endswith('.md') or file.endswith('.txt'):
            filepath = os.path.join(root, file)
            replace_in_file(filepath)
