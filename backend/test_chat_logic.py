import re

buffer = "承知したで！まずはシステム内蔵スキャナーを起動するで。\n\n<get_hot_stocks />\nおお、ちゃんとスキャンしたんやけど"
current_response = ""
in_xml_block = False
force_break = False

while '\n' in buffer:
    line, buffer = buffer.split('\n', 1)
    
    if bool(re.search(r'<(file|replace|run_command|read_url|read_file|list_dir|get_hot_stocks)', line)):
        in_xml_block = True
    
    if in_xml_block:
        current_response += line + '\n'
        print(f"HIDDEN: {line}")
    else:
        current_response += line + '\n'
        print(f"SENT TO UI: {line}")
        
    if bool(re.search(r'</(file|replace|run_command|read_url|read_file|list_dir|get_hot_stocks)>|/>', line)) and in_xml_block:
        in_xml_block = False
        force_break = True
        break

print(f"force_break: {force_break}")
print(f"buffer left: {buffer}")
