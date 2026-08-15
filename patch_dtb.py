import subprocess
import re
import sys
import os

def run_cmd(cmd):
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error executing {' '.join(cmd)}:\n{result.stderr}")
        sys.exit(1)
    return result.stdout

def decompile(dtb_file, dts_file):
    run_cmd(['dtc', '-I', 'dtb', '-O', 'dts', '-o', dts_file, dtb_file])

def compile(dts_file, dtb_file):
    run_cmd(['dtc', '-I', 'dts', '-O', 'dtb', '-o', dtb_file, dts_file])

def extract_node(dts_text, node_names):
    """Sucht nach spezifischen Joystick-Knoten unter Beachtung der geschweiften Klammern."""
    for node_name in node_names:
        # Sucht nach dem Knoten-Namen, optional mit Label und Adresse (z.B. adc-joystick@ff...)
        pattern = re.compile(r'([a-zA-Z0-9_-]+:\s*)?' + node_name + r'(@[0-9a-fA-F]+)?\s*\{')
        match = pattern.search(dts_text)
        if match:
            start_idx = match.start()
            open_braces = 0
            in_block = False
            for i in range(match.end() - 1, len(dts_text)):
                if dts_text[i] == '{':
                    open_braces += 1
                    in_block = True
                elif dts_text[i] == '}':
                    open_braces -= 1
                
                if in_block and open_braces == 0:
                    end_idx = i + 1
                    if end_idx < len(dts_text) and dts_text[end_idx] == ';':
                        end_idx += 1
                    return dts_text[start_idx:end_idx], start_idx, end_idx, node_name
    return None, -1, -1, None

def main():
    r36t_dtb = 'rk3326-r36tmax-linux.dtb'
    k36s_dtb = 'rk3326-k36s-linux.dtb'
    patched_dts = 'rk3326-k36s-linux-patched.dts'
    patched_dtb = 'rk3326-k36s-linux-patched.dtb'

    if not os.path.exists(r36t_dtb) or not os.path.exists(k36s_dtb):
        print("DTB-Dateien nicht gefunden. Bitte stelle sicher, dass sie im Repo liegen.")
        sys.exit(1)

    print("Dekompiliere DTB-Dateien zu DTS...")
    decompile(r36t_dtb, 'r36t.dts')
    decompile(k36s_dtb, 'k36s.dts')

    with open('r36t.dts', 'r') as f:
        r36t_text = f.read()
    with open('k36s.dts', 'r') as f:
        k36s_text = f.read()

    print("Suche nach Analogstick/Joystick-Knoten...")
    # Häufige Knotenbezeichnungen für Gamepads bei RK3326-Boards
    target_nodes = ['adc-joystick', 'joystick', 'gamepad']
    
    node_text, _, _, found_name = extract_node(r36t_text, target_nodes)
    if not node_text:
        print("Konnte keinen Standard-Joystick-Knoten in der R36T Max DTS finden.")
        sys.exit(1)
        
    print(f"Joystick-Knoten '{found_name}' in der R36T Max DTS gefunden.")

    _, k36s_start, k36s_end, _ = extract_node(k36s_text, [found_name])
    
    if k36s_start != -1:
        print(f"Ersetze den bestehenden '{found_name}' Knoten in der K36S DTS...")
        new_k36s_text = k36s_text[:k36s_start] + node_text + k36s_text[k36s_end:]
    else:
        print(f"Knoten '{found_name}' in der K36S DTS nicht gefunden. Füge ihn hinzu...")
        last_brace = k36s_text.rfind('}')
        if last_brace != -1:
            new_k36s_text = k36s_text[:last_brace] + '\n\t' + node_text + '\n' + k36s_text[last_brace:]
        else:
            new_k36s_text = k36s_text + '\n' + node_text + '\n'

    with open(patched_dts, 'w') as f:
        f.write(new_k36s_text)

    print("Kompiliere neu gepatchte K36S DTB...")
    compile(patched_dts, patched_dtb)
    
    print("Erfolg! Die angepasste DTB-Datei wurde erstellt.")

if __name__ == '__main__':
    main()